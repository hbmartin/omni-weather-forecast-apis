from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx2

from omni_weather_forecast_apis.types import ForecastResponse, ProviderSuccess
from omni_weather_forecast_apis.utils import rounded_coordinate, zoneinfo_from_name

_TIMEZONE_LOOKUP_URL: Final = "https://api.open-meteo.com/v1/forecast"
_CACHE_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS location_timezones (
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    timezone TEXT NOT NULL,
    PRIMARY KEY (latitude, longitude)
)
"""


@dataclass(frozen=True)
class TimezoneResolution:
    timezone: str | None
    warnings: tuple[str, ...] = ()


def timezone_cache_path(database_path: Path) -> Path:
    """Return the CLI-owned timezone cache beside the forecast database."""

    return database_path.with_suffix(".timezones.sqlite")


def _coordinate_key(latitude: float, longitude: float) -> tuple[str, str]:
    return rounded_coordinate(latitude), rounded_coordinate(longitude)


def _connect(cache_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(cache_path, timeout=1.0)
    try:
        connection.execute("PRAGMA busy_timeout = 1000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(_CACHE_SCHEMA)
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
                SELECT timezone
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
) -> tuple[str, ...]:
    if (location_timezone := zoneinfo_from_name(timezone)) is None:
        return (f"refusing to cache invalid IANA timezone {timezone!r}",)
    try:
        connection = _connect(cache_path)
        try:
            connection.execute(
                """
                INSERT INTO location_timezones (latitude, longitude, timezone)
                VALUES (?, ?, ?)
                ON CONFLICT(latitude, longitude)
                DO UPDATE SET timezone = excluded.timezone
                """,
                (*_coordinate_key(latitude, longitude), location_timezone.key),
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
    client: httpx2.AsyncClient | None = None,
) -> TimezoneResolution:
    owns_client = client is None
    lookup_client = client or httpx2.AsyncClient(timeout=10.0)
    try:
        response = await lookup_client.get(
            _TIMEZONE_LOOKUP_URL,
            params={
                "latitude": rounded_coordinate(latitude),
                "longitude": rounded_coordinate(longitude),
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
    client: httpx2.AsyncClient | None = None,
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
    )


__all__ = [
    "TimezoneResolution",
    "reconcile_cli_timezone",
    "resolve_cli_timezone",
    "timezone_cache_path",
]
