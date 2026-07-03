"""Tests for the conditional-request HTTP cache transport."""

from __future__ import annotations

import json

import httpx
import pytest

from omni_weather_forecast_apis.http_cache import CachingTransport


class RecordingTransport(httpx.AsyncBaseTransport):
    """Scripted transport that records incoming requests."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses[min(len(self.requests), len(self.responses)) - 1]
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )


def _json_response(payload: dict, headers: dict[str, str]) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
    )


@pytest.mark.asyncio
async def test_fresh_response_served_without_second_request() -> None:
    inner = RecordingTransport(
        [_json_response({"value": 1}, {"Cache-Control": "max-age=3600"})],
    )
    async with httpx.AsyncClient(transport=CachingTransport(inner)) as client:
        first = await client.get("https://example.test/data")
        second = await client.get("https://example.test/data")

    assert first.json() == {"value": 1}
    assert second.json() == {"value": 1}
    assert second.extensions.get("omni_weather_cache") == "hit"
    assert len(inner.requests) == 1


@pytest.mark.asyncio
async def test_stale_response_revalidated_with_conditional_headers() -> None:
    inner = RecordingTransport(
        [
            _json_response(
                {"value": 1},
                {
                    "ETag": '"abc"',
                    "Last-Modified": "Wed, 01 Jul 2026 00:00:00 GMT",
                },
            ),
            httpx.Response(304, headers={"Cache-Control": "max-age=60"}),
        ],
    )
    async with httpx.AsyncClient(transport=CachingTransport(inner)) as client:
        first = await client.get("https://example.test/data")
        second = await client.get("https://example.test/data")
        third = await client.get("https://example.test/data")

    assert first.json() == {"value": 1}
    assert second.json() == {"value": 1}
    assert len(inner.requests) == 2
    revalidation = inner.requests[1]
    assert revalidation.headers["If-None-Match"] == '"abc"'
    assert revalidation.headers["If-Modified-Since"] == "Wed, 01 Jul 2026 00:00:00 GMT"
    # The 304 refreshed the entry, so the third call is a cache hit.
    assert third.json() == {"value": 1}
    assert len(inner.requests) == 2


@pytest.mark.asyncio
async def test_uncacheable_responses_always_hit_network() -> None:
    inner = RecordingTransport([_json_response({"value": 1}, {})])
    async with httpx.AsyncClient(transport=CachingTransport(inner)) as client:
        await client.get("https://example.test/data")
        await client.get("https://example.test/data")

    assert len(inner.requests) == 2


@pytest.mark.asyncio
async def test_no_store_is_never_cached() -> None:
    inner = RecordingTransport(
        [_json_response({"value": 1}, {"Cache-Control": "no-store", "ETag": '"x"'})],
    )
    async with httpx.AsyncClient(transport=CachingTransport(inner)) as client:
        await client.get("https://example.test/data")
        await client.get("https://example.test/data")

    assert len(inner.requests) == 2
    assert "If-None-Match" not in inner.requests[1].headers


@pytest.mark.asyncio
async def test_non_get_requests_bypass_cache() -> None:
    inner = RecordingTransport(
        [_json_response({"value": 1}, {"Cache-Control": "max-age=3600"})],
    )
    async with httpx.AsyncClient(transport=CachingTransport(inner)) as client:
        await client.post("https://example.test/data")
        await client.post("https://example.test/data")

    assert len(inner.requests) == 2


@pytest.mark.asyncio
async def test_cache_evicts_oldest_entry_when_full() -> None:
    inner = RecordingTransport(
        [_json_response({"value": 1}, {"Cache-Control": "max-age=3600"})],
    )
    transport = CachingTransport(inner, max_entries=1)
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://example.test/one")
        await client.get("https://example.test/two")
        await client.get("https://example.test/one")

    # /one was evicted by /two, so it required a second network fetch.
    assert len(inner.requests) == 3
