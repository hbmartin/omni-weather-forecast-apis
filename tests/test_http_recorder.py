"""Tests for the raw payload archive transport."""

from __future__ import annotations

import gzip
import json
from datetime import datetime

import httpx2
import pytest

from omni_weather_forecast_apis.http_cache import CachingTransport
from omni_weather_forecast_apis.http_recorder import RawArchiveTransport


def _read_lines(path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


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
