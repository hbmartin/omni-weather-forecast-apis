"""HTTP response caching with conditional-request revalidation.

Implements a small, standards-aware cache for GET requests as an httpx
transport wrapper. Fresh responses (``Cache-Control: max-age`` / ``Expires``)
are served without a network round-trip; stale responses that carry
validators (``ETag`` / ``Last-Modified``) are revalidated with conditional
headers and reused on ``304 Not Modified``.

MET Norway's terms of service require ``If-Modified-Since`` support and the
NWS strongly encourages caching, so the cache is enabled by default.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

_MAX_AGE_PATTERN = re.compile(r"max-age=(\d+)")


@dataclass
class _CacheEntry:
    status_code: int
    headers: httpx.Headers
    content: bytes
    etag: str | None
    last_modified: str | None
    fresh_until: float | None


def _parse_http_date(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        return None


def _freshness_lifetime(headers: httpx.Headers, *, now: float) -> float | None:
    """Compute the absolute expiry time from response headers, if any."""

    cache_control = headers.get("Cache-Control", "").lower()
    if "no-store" in cache_control or "no-cache" in cache_control:
        return None
    if (match := _MAX_AGE_PATTERN.search(cache_control)) is not None:
        response_time = _parse_http_date(headers.get("Date")) or now
        return response_time + int(match.group(1))
    if (expires := _parse_http_date(headers.get("Expires"))) is not None:
        return expires
    return None


def _storable_headers(headers: httpx.Headers) -> httpx.Headers:
    """Drop framing/encoding headers: cached content is already decoded."""

    stored = httpx.Headers(headers)
    for name in ("Content-Encoding", "Content-Length", "Transfer-Encoding"):
        if name in stored:
            del stored[name]
    return stored


def _is_cacheable(headers: httpx.Headers, *, now: float) -> bool:
    if "no-store" in headers.get("Cache-Control", "").lower():
        return False
    return (
        headers.get("ETag") is not None
        or headers.get("Last-Modified") is not None
        or _freshness_lifetime(headers, now=now) is not None
    )


class CachingTransport(httpx.AsyncBaseTransport):
    """Wrap a transport with an in-memory ETag/Expires-aware GET cache."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport,
        *,
        max_entries: int = 256,
    ) -> None:
        self._transport = transport
        self._max_entries = max_entries
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            return await self._transport.handle_async_request(request)

        key = str(request.url)
        now = time.time()
        async with self._lock:
            entry = self._entries.get(key)

        if entry is not None and entry.fresh_until is not None and now < entry.fresh_until:
            return self._response_from_entry(entry, request)

        if entry is not None:
            if entry.etag is not None:
                request.headers["If-None-Match"] = entry.etag
            if entry.last_modified is not None:
                request.headers["If-Modified-Since"] = entry.last_modified

        response = await self._transport.handle_async_request(request)

        if entry is not None and response.status_code == httpx.codes.NOT_MODIFIED:
            await response.aread()
            await response.aclose()
            entry.fresh_until = _freshness_lifetime(response.headers, now=now)
            async with self._lock:
                self._entries[key] = entry
            return self._response_from_entry(entry, request)

        if response.status_code == httpx.codes.OK and _is_cacheable(
            response.headers,
            now=now,
        ):
            content = await response.aread()
            await response.aclose()
            new_entry = _CacheEntry(
                status_code=response.status_code,
                headers=_storable_headers(response.headers),
                content=content,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
                fresh_until=_freshness_lifetime(response.headers, now=now),
            )
            async with self._lock:
                if key not in self._entries and len(self._entries) >= self._max_entries:
                    oldest_key = next(iter(self._entries))
                    del self._entries[oldest_key]
                self._entries[key] = new_entry
            return self._response_from_entry(new_entry, request)

        return response

    async def aclose(self) -> None:
        await self._transport.aclose()

    @staticmethod
    def _response_from_entry(
        entry: _CacheEntry,
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            status_code=entry.status_code,
            headers=entry.headers,
            content=entry.content,
            request=request,
            extensions={"omni_weather_cache": "hit"},
        )


__all__ = ["CachingTransport"]
