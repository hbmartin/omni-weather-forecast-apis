"""Raw HTTP payload archiving as an httpx2 transport wrapper.

Every response fetched over the network is appended to a gzipped JSONL
archive, one line per response: ``{ts, method, url, status, body}``. The
archive makes historical runs reparseable — any future parser bug can be
repaired by replaying the recorded payloads instead of guessing from the
normalized columns.

Stack the recorder INSIDE :class:`~omni_weather_forecast_apis.http_cache.
CachingTransport` so cache hits are not re-recorded; conditional
revalidations and every retry/redirect hop are real traffic and each get
their own line. URLs are stored verbatim, including any credentials
providers carry in query strings or paths — keep archives out of version
control.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from pathlib import Path
from typing import BinaryIO

import httpx2

from omni_weather_forecast_apis.utils import utc_now

logger = logging.getLogger("omni_weather_forecast_apis")

_TRANSFER_HEADERS = ("Content-Encoding", "Content-Length", "Transfer-Encoding")


def _decoded_headers(headers: httpx2.Headers) -> httpx2.Headers:
    """Drop framing/encoding headers: the rebuilt body is already decoded."""

    stored = httpx2.Headers(headers)
    for name in _TRANSFER_HEADERS:
        if name in stored:
            del stored[name]
    return stored


class RawArchiveTransport(httpx2.AsyncBaseTransport):
    """Append every real network response to a gzipped JSONL archive.

    Each line is compressed as its own gzip member; members concatenate
    legally, so a crash mid-run loses at most the in-flight line while the
    rest of the file stays readable. Recording failures are logged once and
    disable the archive — they never fail the request.
    """

    def __init__(
        self,
        transport: httpx2.AsyncBaseTransport,
        archive_path: str | Path,
    ) -> None:
        self._transport = transport
        self._archive_path = Path(archive_path)
        self._lock = asyncio.Lock()
        self._file: BinaryIO | None = None
        self._recording_failed = False

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._transport.handle_async_request(request)
        body = await response.aread()
        await response.aclose()
        await self._record(request, response.status_code, body)
        return httpx2.Response(
            status_code=response.status_code,
            headers=_decoded_headers(response.headers),
            content=body,
            request=request,
            extensions={"omni_weather_recorded": True},
        )

    async def _record(
        self,
        request: httpx2.Request,
        status_code: int,
        body: bytes,
    ) -> None:
        if self._recording_failed:
            return
        try:
            line = json.dumps(
                {
                    "ts": utc_now().isoformat(),
                    "method": request.method,
                    "url": str(request.url),
                    "status": status_code,
                    "body": body.decode("utf-8", errors="replace"),
                },
                separators=(",", ":"),
            )
            member = gzip.compress(f"{line}\n".encode())
            async with self._lock:
                await asyncio.to_thread(self._append, member)
        except (Exception,):  # noqa: B013
            self._recording_failed = True
            logger.exception(
                "Raw archive write failed; disabling archiving to %s",
                self._archive_path,
            )

    def _append(self, member: bytes) -> None:
        if self._file is None:
            self._archive_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self._archive_path.open("ab")
        self._file.write(member)
        self._file.flush()

    async def aclose(self) -> None:
        try:
            if self._file is not None:
                self._file.close()
                self._file = None
        finally:
            await self._transport.aclose()


__all__ = ["RawArchiveTransport"]
