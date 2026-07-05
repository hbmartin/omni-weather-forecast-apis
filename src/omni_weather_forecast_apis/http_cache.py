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
_SENSITIVE_REQUEST_HEADERS = frozenset({"authorization", "cookie"})
_VARIANT_REQUEST_HEADERS = ("accept", "accept-encoding", "accept-language")
type _CacheKey = tuple[str, tuple[tuple[str, str], ...]]


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


def _freshness_lifetime(
    headers: httpx.Headers,
    *,
    now: float,
    response_time: float | None = None,
) -> float | None:
    """Compute the absolute expiry time from response headers, if any."""

    cache_control = headers.get("Cache-Control", "").lower()
    if "no-store" in cache_control or "no-cache" in cache_control:
        return None
    if (match := _MAX_AGE_PATTERN.search(cache_control)) is not None:
        effective_response_time = (
            response_time
            if response_time is not None
            else _parse_http_date(headers.get("Date"))
        ) or now
        return effective_response_time + int(match.group(1))
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
    if headers.get("Vary") == "*":
        return False
    return (
        headers.get("ETag") is not None
        or headers.get("Last-Modified") is not None
        or _freshness_lifetime(headers, now=now) is not None
    )


def _is_sensitive_request(request: httpx.Request) -> bool:
    return any(header in request.headers for header in _SENSITIVE_REQUEST_HEADERS)


def _cache_key(request: httpx.Request) -> _CacheKey:
    variant_headers = tuple(
        (header, request.headers[header])
        for header in _VARIANT_REQUEST_HEADERS
        if header in request.headers
    )
    return str(request.url), variant_headers


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
        self._entries: dict[_CacheKey, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET" or _is_sensitive_request(request):
            return await self._transport.handle_async_request(request)

        key = _cache_key(request)
        now = time.time()
        async with self._lock:
            entry = self._entries.get(key)

        if (
            entry is not None
            and entry.fresh_until is not None
            and now < entry.fresh_until
        ):
            return self._response_from_entry(entry, request)

        if entry is not None:
            if entry.etag is not None:
                request.headers["If-None-Match"] = entry.etag
            if entry.last_modified is not None:
                request.headers["If-Modified-Since"] = entry.last_modified

        response = await self._transport.handle_async_request(request)

        if entry is not None and response.status_code == httpx.codes.NOT_MODIFIED:
            return await self._response_from_revalidation(
                key,
                entry,
                request,
                response,
                now,
            )

        if response.status_code == httpx.codes.OK and _is_cacheable(
            response.headers,
            now=now,
        ):
            return await self._response_from_store(key, request, response, now)

        return response

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def _response_from_revalidation(
        self,
        key: _CacheKey,
        entry: _CacheEntry,
        request: httpx.Request,
        response: httpx.Response,
        now: float,
    ) -> httpx.Response:
        await response.aread()
        await response.aclose()
        entry.headers.update(_storable_headers(response.headers))
        entry.fresh_until = (
            _freshness_lifetime(response.headers, now=now)
            or _freshness_lifetime(entry.headers, now=now, response_time=now)
            or entry.fresh_until
        )
        async with self._lock:
            self._entries[key] = entry
        return self._response_from_entry(entry, request)

    async def _response_from_store(
        self,
        key: _CacheKey,
        request: httpx.Request,
        response: httpx.Response,
        now: float,
    ) -> httpx.Response:
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
        return self._response_from_entry(new_entry, request, hit=False)

    @staticmethod
    def _response_from_entry(
        entry: _CacheEntry,
        request: httpx.Request,
        *,
        hit: bool = True,
    ) -> httpx.Response:
        return httpx.Response(
            status_code=entry.status_code,
            headers=entry.headers,
            content=entry.content,
            request=request,
            extensions={"omni_weather_cache": "hit" if hit else "store"},
        )


__all__ = ["CachingTransport"]
