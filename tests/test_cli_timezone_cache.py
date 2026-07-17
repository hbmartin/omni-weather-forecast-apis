from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from omni_weather_forecast_apis._cli_timezone_cache import (
    reconcile_cli_timezone,
    resolve_cli_timezone,
    timezone_cache_path,
)
from omni_weather_forecast_apis.types import (
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    ModelSource,
    ProviderId,
    ProviderSuccess,
    SourceForecast,
)


class _ManagedLookup:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    async def lookup_location_timezone(
        self,
        latitude: float,
        longitude: float,
    ) -> str:
        self.calls.append((latitude, longitude))
        return "America/Los_Angeles"


class _ManagedTimeout:
    async def lookup_location_timezone(
        self,
        latitude: float,
        longitude: float,
    ) -> str:
        request = httpx2.Request(
            "GET",
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": latitude, "longitude": longitude},
        )
        raise httpx2.ReadTimeout("timezone lookup timed out", request=request)


@pytest.mark.asyncio
async def test_resolve_cli_timezone_caches_open_meteo_result(tmp_path) -> None:
    database_path = tmp_path / "forecasts.sqlite"
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json={"timezone": "America/Los_Angeles"})

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler),
    ) as client:
        first = await resolve_cli_timezone(
            database_path,
            34.123456,
            -117.987654,
            needs_lookup=True,
            client=client,
        )
        second = await resolve_cli_timezone(
            database_path,
            34.123456,
            -117.987654,
            needs_lookup=True,
            client=client,
        )

    assert first.timezone == "America/Los_Angeles"
    assert first.warnings == ()
    assert second.timezone == "America/Los_Angeles"
    assert len(calls) == 1
    assert calls[0].url.params["latitude"] == "34.123456"
    assert calls[0].url.params["longitude"] == "-117.987654"
    assert timezone_cache_path(database_path) == tmp_path / "forecasts.timezones.sqlite"

    connection = sqlite3.connect(timezone_cache_path(database_path))
    try:
        metadata = connection.execute(
            "SELECT latitude, longitude, source, resolver_version "
            "FROM location_timezones",
        ).fetchone()
    finally:
        connection.close()
    assert metadata == ("34.123456", "-117.987654", "open-meteo", 1)


@pytest.mark.asyncio
async def test_lookup_can_use_the_aggregation_clients_transport(tmp_path) -> None:
    managed_client = _ManagedLookup()

    result = await resolve_cli_timezone(
        tmp_path / "forecasts.sqlite",
        34.0,
        -117.0,
        needs_lookup=True,
        client=managed_client,
    )

    assert result.timezone == "America/Los_Angeles"
    assert managed_client.calls == [(34.0, -117.0)]


@pytest.mark.asyncio
async def test_managed_lookup_timeout_is_informational(tmp_path: Path) -> None:
    result = await resolve_cli_timezone(
        tmp_path / "forecasts.sqlite",
        34.0,
        -117.0,
        needs_lookup=True,
        client=_ManagedTimeout(),
    )

    assert result.timezone is None
    assert result.warnings == ("timezone lookup failed: timezone lookup timed out",)


@pytest.mark.asyncio
async def test_cache_keys_do_not_collapse_nearby_coordinates(tmp_path) -> None:
    database_path = tmp_path / "forecasts.sqlite"
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json={"timezone": "America/Los_Angeles"})

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler),
    ) as client:
        for latitude in (34.123441, 34.123449):
            result = await resolve_cli_timezone(
                database_path,
                latitude,
                -117.0,
                needs_lookup=True,
                client=client,
            )
            assert result.timezone == "America/Los_Angeles"

    assert calls == 2


@pytest.mark.asyncio
async def test_stale_cache_entry_is_refreshed(tmp_path) -> None:
    database_path = tmp_path / "forecasts.sqlite"
    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(
            200,
            json={"timezone": "America/Los_Angeles"},
        ),
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        await resolve_cli_timezone(
            database_path,
            34.0,
            -117.0,
            needs_lookup=True,
            client=client,
        )

    connection = sqlite3.connect(timezone_cache_path(database_path))
    try:
        connection.execute(
            "UPDATE location_timezones SET resolved_at = ?",
            ("2020-01-01T00:00:00+00:00",),
        )
        connection.commit()
    finally:
        connection.close()

    calls = 0

    def refreshed(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json={"timezone": "America/Denver"})

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(refreshed),
    ) as client:
        result = await resolve_cli_timezone(
            database_path,
            34.0,
            -117.0,
            needs_lookup=True,
            client=client,
        )

    assert result.timezone == "America/Denver"
    assert calls == 1
    assert any("stale" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_legacy_cache_schema_is_migrated_without_lookup(tmp_path) -> None:
    database_path = tmp_path / "forecasts.sqlite"
    cache_path = timezone_cache_path(database_path)
    connection = sqlite3.connect(cache_path)
    try:
        connection.executescript(
            """
            CREATE TABLE location_timezones (
                latitude TEXT NOT NULL,
                longitude TEXT NOT NULL,
                timezone TEXT NOT NULL,
                PRIMARY KEY (latitude, longitude)
            );
            INSERT INTO location_timezones VALUES (
                '34.000000', '-117.000000', 'America/Los_Angeles'
            );
            """,
        )
    finally:
        connection.close()

    result = await resolve_cli_timezone(
        database_path,
        34.0,
        -117.0,
        needs_lookup=False,
    )

    connection = sqlite3.connect(cache_path)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(location_timezones)")
        }
    finally:
        connection.close()
    assert result.timezone is None
    assert any("stale" in warning for warning in result.warnings)
    assert {"source", "resolved_at", "resolver_version"} <= columns


@pytest.mark.asyncio
async def test_cache_failure_warns_but_returns_uncached_lookup(tmp_path) -> None:
    database_path = tmp_path / "forecasts.sqlite"
    timezone_cache_path(database_path).write_text("not a database", encoding="utf-8")
    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(200, json={"timezone": "Europe/Warsaw"}),
    )

    async with httpx2.AsyncClient(transport=transport) as client:
        result = await resolve_cli_timezone(
            database_path,
            52.0,
            21.0,
            needs_lookup=True,
            client=client,
        )

    assert result.timezone == "Europe/Warsaw"
    assert len(result.warnings) == 2
    assert "unavailable" in result.warnings[0]
    assert "could not update" in result.warnings[1]


@pytest.mark.asyncio
async def test_lookup_failure_is_informational(tmp_path) -> None:
    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(429, json={"reason": "limited"}),
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        result = await resolve_cli_timezone(
            tmp_path / "forecasts.sqlite",
            34.0,
            -117.0,
            needs_lookup=True,
            client=client,
        )

    assert result.timezone is None
    assert len(result.warnings) == 1
    assert "timezone lookup failed" in result.warnings[0]


def _response_with_timezones(*timezones: str) -> ForecastResponse:
    return ForecastResponse(
        request=ForecastResponseRequest(
            latitude=34.0,
            longitude=-117.0,
            granularity=[],
            language="en",
        ),
        results=[
            ProviderSuccess(
                provider=ProviderId.OPENWEATHER,
                forecasts=[
                    SourceForecast(
                        source=ModelSource(
                            provider=ProviderId.OPENWEATHER,
                            model="one_call",
                        ),
                        timezone=timezone,
                    )
                    for timezone in timezones
                ],
                fetched_at=datetime(2026, 7, 13, tzinfo=UTC),
                latency_ms=1.0,
            ),
        ],
        summary=ForecastResponseSummary(total=1, succeeded=1, failed=0),
        completed_at=datetime(2026, 7, 13, tzinfo=UTC),
        total_latency_ms=1.0,
    )


@pytest.mark.asyncio
async def test_reconcile_caches_one_provider_timezone(tmp_path) -> None:
    database_path = tmp_path / "forecasts.sqlite"
    warnings = reconcile_cli_timezone(
        database_path,
        34.0,
        -117.0,
        _response_with_timezones("America/Los_Angeles"),
    )

    assert warnings == ()
    cached = await resolve_cli_timezone(
        database_path,
        34.0,
        -117.0,
        needs_lookup=False,
    )
    assert cached.timezone == "America/Los_Angeles"


def test_reconcile_refuses_provider_timezone_conflict(tmp_path) -> None:
    warnings = reconcile_cli_timezone(
        tmp_path / "forecasts.sqlite",
        34.0,
        -117.0,
        _response_with_timezones("America/Los_Angeles", "America/Denver"),
    )

    assert len(warnings) == 1
    assert "conflicting timezones" in warnings[0]
