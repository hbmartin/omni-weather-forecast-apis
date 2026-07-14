from __future__ import annotations

from datetime import UTC, datetime

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
    assert calls[0].url.params["latitude"] == "34.1235"
    assert calls[0].url.params["longitude"] == "-117.9877"
    assert timezone_cache_path(database_path) == tmp_path / "forecasts.timezones.sqlite"


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
