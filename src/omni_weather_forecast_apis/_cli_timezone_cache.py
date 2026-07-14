from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

import httpx2

from omni_weather_forecast_apis.types import ForecastResponse, ProviderSuccess
from omni_weather_forecast_apis.utils import zoneinfo_from_name

_TIMEZONE_LOOKUP_URL: Final = "https://api.open-meteo.com/v1/forecast"
_CACHE_TTL: Final = timedelta(days=30)
_RESOLVER_VERSION: Final = 1
_CACHE_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS location_timezones (
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    timezone TEXT NOT NULL,
    source TEXT NOT NULL,
    resolved_at TEXT NOT NULL,
    resolver_version INTEGER NOT NULL,
    PRIMARY KEY (latitude, longitude)
)
"""


@dataclass(frozen=True)
class TimezoneResolution:
    timezone: str | None
    warnings: tuple[str, ...] = ()


@runtime_checkable
class _ManagedTimezoneLookup(Protocol):
    async def lookup_location_timezone(
        self,
        latitude: float,
        longitude: float,
    ) -> str: ...


def timezone_cache_path(database_path: Path) -> Path:
    """Return the CLI-owned timezone cache beside the forecast database."""

    return database_path.with_suffix(".timezones.sqlite")


def _coordinate_key(latitude: float, longitude: float) -> tuple[str, str]:
    return f"{latitude:.6f}", f"{longitude:.6f}"


def _ensure_cache_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(location_timezones)")
    }
    if "source" not in columns:
        connection.execute(
            "ALTER TABLE location_timezones ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy'",
        )
    if "resolved_at" not in columns:
        connection.execute(
            "ALTER TABLE location_timezones ADD COLUMN resolved_at TEXT",
        )
    if "resolver_version" not in columns:
        connection.execute(
            """
            ALTER TABLE location_timezones
            ADD COLUMN resolver_version INTEGER NOT NULL DEFAULT 0
            """,
        )


def _connect(cache_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(cache_path, timeout=1.0)
    try:
        connection.execute("PRAGMA busy_timeout = 1000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(_CACHE_SCHEMA)
        _ensure_cache_columns(connection)
        connection.commit()
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def _read_cached_timezone(
    cache_path: Path,
    latitude: float,
    longitude: float,
) -> TimezoneResolution:
    try:
        connection = _connect(cache_path)
        try:
            row = connection.execute(
                """
                SELECT timezone, resolved_at, resolver_version
                FROM location_timezones
                WHERE latitude = ? AND longitude = ?
                """,
                _coordinate_key(latitude, longitude),
            ).fetchone()
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        return TimezoneResolution(
            None,
            (f"timezone cache {cache_path} is unavailable: {exc}",),
        )
    if row is None:
        return TimezoneResolution(None)
    try:
        resolved_at = datetime.fromisoformat(row[1]) if row[1] is not None else None
    except (TypeError, ValueError):
        resolved_at = None
    if (
        resolved_at is None
        or resolved_at.tzinfo is None
        or datetime.now(UTC) - resolved_at.astimezone(UTC) > _CACHE_TTL
        or row[2] != _RESOLVER_VERSION
    ):
        return TimezoneResolution(
            None,
            (f"timezone cache {cache_path} entry is stale; refreshing",),
        )
    if (location_timezone := zoneinfo_from_name(row[0])) is None:
        return TimezoneResolution(
            None,
            (f"timezone cache {cache_path} contains an invalid IANA timezone",),
        )
    return TimezoneResolution(location_timezone.key)


def _write_cached_timezone(
    cache_path: Path,
    latitude: float,
    longitude: float,
    timezone: str,
    *,
    source: str,
) -> tuple[str, ...]:
    if (location_timezone := zoneinfo_from_name(timezone)) is None:
        return (f"refusing to cache invalid IANA timezone {timezone!r}",)
    try:
        connection = _connect(cache_path)
        try:
            connection.execute(
                """
                INSERT INTO location_timezones (
                    latitude, longitude, timezone, source, resolved_at, resolver_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(latitude, longitude)
                DO UPDATE SET
                    timezone = excluded.timezone,
                    source = excluded.source,
                    resolved_at = excluded.resolved_at,
                    resolver_version = excluded.resolver_version
                """,
                (
                    *_coordinate_key(latitude, longitude),
                    location_timezone.key,
                    source,
                    datetime.now(UTC).isoformat(),
                    _RESOLVER_VERSION,
                ),
            )
            connection.commit()
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        return (f"could not update timezone cache {cache_path}: {exc}",)
    return ()


async def _lookup_timezone(
    latitude: float,
    longitude: float,
    *,
    client: httpx2.AsyncClient | _ManagedTimezoneLookup | None = None,
) -> TimezoneResolution:
    if isinstance(client, _ManagedTimezoneLookup):
        try:
            return TimezoneResolution(
                await client.lookup_location_timezone(latitude, longitude),
            )
        except (httpx2.HTTPError, OSError, ValueError) as exc:
            return TimezoneResolution(None, (f"timezone lookup failed: {exc}",))

    owns_client = not isinstance(client, httpx2.AsyncClient)
    lookup_client = client if isinstance(client, httpx2.AsyncClient) else None
    lookup_client = lookup_client or httpx2.AsyncClient(timeout=10.0)
    try:
        response = await lookup_client.get(
            _TIMEZONE_LOOKUP_URL,
            params={
                "latitude": f"{latitude:.6f}",
                "longitude": f"{longitude:.6f}",
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response is not a JSON object")
        if (location_timezone := zoneinfo_from_name(payload.get("timezone"))) is None:
            raise ValueError("response lacks a valid IANA timezone")
        return TimezoneResolution(location_timezone.key)
    except (httpx2.HTTPError, OSError, ValueError) as exc:
        return TimezoneResolution(None, (f"timezone lookup failed: {exc}",))
    finally:
        if owns_client:
            await lookup_client.aclose()


async def resolve_cli_timezone(
    database_path: Path,
    latitude: float,
    longitude: float,
    *,
    needs_lookup: bool,
    client: httpx2.AsyncClient | _ManagedTimezoneLookup | None = None,
) -> TimezoneResolution:
    """Read the CLI cache and optionally resolve/cache a miss with Open-Meteo."""

    cache_path = timezone_cache_path(database_path)
    cached = _read_cached_timezone(cache_path, latitude, longitude)
    if cached.timezone is not None or not needs_lookup:
        return cached

    resolved = await _lookup_timezone(latitude, longitude, client=client)
    warnings = (*cached.warnings, *resolved.warnings)
    if resolved.timezone is None:
        return TimezoneResolution(None, warnings)
    cache_warnings = _write_cached_timezone(
        cache_path,
        latitude,
        longitude,
        resolved.timezone,
        source="open-meteo",
    )
    return TimezoneResolution(resolved.timezone, (*warnings, *cache_warnings))


def reconcile_cli_timezone(
    database_path: Path,
    latitude: float,
    longitude: float,
    response: ForecastResponse,
) -> tuple[str, ...]:
    """Persist the single IANA timezone agreed on by successful sources."""

    timezones = {
        forecast.timezone
        for result in response.results
        if isinstance(result, ProviderSuccess)
        for forecast in result.forecasts
        if forecast.timezone is not None
    }
    if not timezones:
        return ()
    if len(timezones) > 1:
        joined = ", ".join(sorted(timezones))
        return (
            f"providers returned conflicting timezones ({joined}); cache unchanged",
        )
    return _write_cached_timezone(
        timezone_cache_path(database_path),
        latitude,
        longitude,
        timezones.pop(),
        source="provider-consensus",
    )


__all__ = [
    "TimezoneResolution",
    "reconcile_cli_timezone",
    "resolve_cli_timezone",
    "timezone_cache_path",
]
