"""Tests for the raw payload archive transport."""

from __future__ import annotations

import asyncio
import gzip
import json
import threading
from datetime import datetime

import httpx2
import pytest

from omni_weather_forecast_apis.http_cache import CachingTransport
from omni_weather_forecast_apis.http_recorder import RawArchiveTransport


def _read_lines(path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


class _FailingStream(httpx2.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self):
        raise httpx2.ReadError("stream interrupted")
        yield b""  # pragma: no cover

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_read_failure_closes_original_response(tmp_path) -> None:
    stream = _FailingStream()

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, request=request, stream=stream)

    transport = RawArchiveTransport(
        httpx2.MockTransport(handler),
        tmp_path / "run.jsonl.gz",
    )

    with pytest.raises(httpx2.ReadError, match="stream interrupted"):
        await transport.handle_async_request(
            httpx2.Request("GET", "https://example.com")
        )

    assert stream.closed is True
    await transport.aclose()


@pytest.mark.asyncio
async def test_records_each_network_response(tmp_path) -> None:
    archive = tmp_path / "raw" / "run.jsonl.gz"

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"path": request.url.path})

    transport = RawArchiveTransport(httpx2.MockTransport(handler), archive)
    async with httpx2.AsyncClient(transport=transport) as client:
        first = await client.get("https://api.example.com/a?units=si&key=k")
        second = await client.get("https://api.example.com/b")
        posted = await client.post("https://api.example.com/c")

    assert first.json() == {"path": "/a"}
    assert second.json() == {"path": "/b"}
    assert posted.status_code == 200

    lines = _read_lines(archive)
    assert [line["url"] for line in lines] == [
        "https://api.example.com/a?units=si&key=k",
        "https://api.example.com/b",
        "https://api.example.com/c",
    ]
    assert [line["method"] for line in lines] == ["GET", "GET", "POST"]
    assert all(line["status"] == 200 for line in lines)
    assert json.loads(lines[0]["body"]) == {"path": "/a"}
    for line in lines:
        parsed = datetime.fromisoformat(line["ts"])
        assert parsed.tzinfo is not None


@pytest.mark.asyncio
async def test_gzip_members_concatenate_into_one_stream(tmp_path) -> None:
    archive = tmp_path / "run.jsonl.gz"
    transport = RawArchiveTransport(
        httpx2.MockTransport(lambda _request: httpx2.Response(200, json={})),
        archive,
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        for _ in range(5):
            await client.get("https://api.example.com/")

    decompressed = gzip.decompress(archive.read_bytes()).decode()
    assert decompressed.count("\n") == 5
    assert len(_read_lines(archive)) == 5


@pytest.mark.asyncio
async def test_cache_hits_are_not_recorded_but_revalidations_are(tmp_path) -> None:
    archive = tmp_path / "run.jsonl.gz"
    calls = {"count": 0}

    def handler(_request: httpx2.Request) -> httpx2.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx2.Response(
                200,
                headers={"ETag": '"v1"', "Cache-Control": "max-age=3600"},
                json={"fresh": True},
            )
        return httpx2.Response(304, headers={"ETag": '"v1"'})

    transport = CachingTransport(
        RawArchiveTransport(httpx2.MockTransport(handler), archive),
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        first = await client.get("https://api.example.com/data")
        cached = await client.get("https://api.example.com/data")

    assert first.json() == {"fresh": True}
    assert cached.json() == {"fresh": True}
    assert cached.extensions.get("omni_weather_cache") == "hit"
    # The fresh cache hit never reached the network, so only the original
    # response is archived.
    assert calls["count"] == 1
    lines = _read_lines(archive)
    assert len(lines) == 1
    assert lines[0]["status"] == 200


@pytest.mark.asyncio
async def test_recording_failure_never_breaks_the_fetch(tmp_path, caplog) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied")
    archive = blocker / "run.jsonl.gz"

    transport = RawArchiveTransport(
        httpx2.MockTransport(lambda _request: httpx2.Response(200, json={"ok": 1})),
        archive,
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        with caplog.at_level("ERROR", logger="omni_weather_forecast_apis"):
            first = await client.get("https://api.example.com/")
            second = await client.get("https://api.example.com/")

    assert first.json() == {"ok": 1}
    assert second.json() == {"ok": 1}
    failure_logs = [
        record
        for record in caplog.records
        if "Raw archive write failed" in record.message
    ]
    # The failure latch logs once, then archiving stays silently disabled.
    assert len(failure_logs) == 1
    assert not archive.exists()


@pytest.mark.asyncio
async def test_zero_traffic_creates_no_file_and_aclose_chains(tmp_path) -> None:
    archive = tmp_path / "raw" / "run.jsonl.gz"

    class SpyTransport(httpx2.AsyncBaseTransport):
        closed = False

        async def handle_async_request(
            self,
            _request: httpx2.Request,
        ) -> httpx2.Response:
            raise AssertionError("no requests expected")

        async def aclose(self) -> None:
            self.closed = True

    spy = SpyTransport()
    transport = RawArchiveTransport(spy, archive)
    async with httpx2.AsyncClient(transport=transport):
        pass

    assert spy.closed is True
    assert not archive.exists()
    assert not archive.parent.exists()


@pytest.mark.asyncio
async def test_aclose_waits_for_active_write_and_prevents_reopen(
    tmp_path,
    monkeypatch,
) -> None:
    archive = tmp_path / "raw" / "run.jsonl.gz"
    transport = RawArchiveTransport(
        httpx2.MockTransport(lambda _request: httpx2.Response(200, json={})),
        archive,
    )
    write_started = threading.Event()
    release_write = threading.Event()
    original_append = transport._append

    def slow_append(member: bytes) -> None:
        write_started.set()
        if not release_write.wait(timeout=5):
            raise TimeoutError("test did not release archive write")
        original_append(member)

    monkeypatch.setattr(transport, "_append", slow_append)
    request = httpx2.Request("GET", "https://api.example.com/")
    record_task = asyncio.create_task(transport._record(request, 200, b"{}"))
    assert await asyncio.to_thread(write_started.wait, 2)

    close_task = asyncio.create_task(transport.aclose())
    await asyncio.sleep(0)
    assert close_task.done() is False

    release_write.set()
    await asyncio.gather(record_task, close_task)
    await transport._record(request, 200, b'{"late":true}')

    assert len(_read_lines(archive)) == 1
    assert transport._file is None


@pytest.mark.asyncio
async def test_encoded_responses_survive_rebuild_and_caching(tmp_path) -> None:
    archive = tmp_path / "run.jsonl.gz"
    body = json.dumps({"temperature": 12.5}).encode()

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={
                "Content-Encoding": "gzip",
                "Cache-Control": "max-age=60",
            },
            content=gzip.compress(body),
        )

    transport = CachingTransport(
        RawArchiveTransport(httpx2.MockTransport(handler), archive),
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        response = await client.get("https://api.example.com/enc")

    # The recorder rebuilds the response with decoded content; the cache
    # layer above must still be able to read and store it.
    assert response.json() == {"temperature": 12.5}
    lines = _read_lines(archive)
    assert json.loads(lines[0]["body"]) == {"temperature": 12.5}
