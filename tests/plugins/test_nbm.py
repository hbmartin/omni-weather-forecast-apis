"""Tests for the NOAA NBM (via IEM) provider."""

import httpx2
import pytest
from pydantic import ValidationError

from omni_weather_forecast_apis.plugins.nbm import (
    _hourly_point,
    _latest_run_rows,
    nbm_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchParams,
)

_PARAMS = PluginFetchParams(
    latitude=34.2768,
    longitude=-117.1692,
    granularity=[Granularity.HOURLY],
)


def _row(**overrides: object) -> dict[str, object]:
    """One IEM mos.json data row, shaped like the recorded KSBD response."""
    base: dict[str, object] = {
        "model": "NBS",
        "runtime": "2026-07-18 12:00",
        "runtime_utc": "2026-07-18T12:00:00.000",
        "ftime": "2026-07-18 18:00",
        "ftime_utc": "2026-07-18T18:00:00.000",
        "station": "KSBD",
        "tmp": 83,
        "dpt": 61,
        "wdr": 240,
        "wsp": 2,
        "gst": 7,
        "sky": 20,
        "p06": 1.0,
        "q06": 0.0,
        "cig": -88,
        "vis": 100,
    }
    base.update(overrides)
    return base


class TestConfig:
    def test_station_id_required(self):
        with pytest.raises(ValidationError):
            nbm_plugin.validate_config({})

    def test_station_id_pattern(self):
        with pytest.raises(ValidationError):
            nbm_plugin.validate_config({"station_id": "ks"})
        config = nbm_plugin.validate_config({"station_id": "KSBD"})
        assert config.station_id == "KSBD"

    def test_extra_keys_forbidden(self):
        with pytest.raises(ValidationError):
            nbm_plugin.validate_config({"station_id": "KSBD", "user_agent": "x"})


class TestParsing:
    def test_hourly_point_units(self):
        point = _hourly_point(_row())
        assert point is not None
        assert point.temperature == pytest.approx((83 - 32) * 5 / 9)
        assert point.dew_point == pytest.approx((61 - 32) * 5 / 9)
        assert point.wind_speed == pytest.approx(2 * 0.514444, rel=1e-3)
        assert point.wind_gust == pytest.approx(7 * 0.514444, rel=1e-3)
        assert point.wind_direction == pytest.approx(240)
        assert point.cloud_cover == pytest.approx(20)
        assert point.precipitation_probability == pytest.approx(0.01)
        # Q06 is a 6-hour total: never mapped onto an hourly point
        assert point.precipitation is None
        assert point.timestamp.isoformat().startswith("2026-07-18T18:00")

    def test_sentinels_become_none(self):
        point = _hourly_point(_row(tmp=-88, dpt=None, wsp=None))
        assert point is not None
        assert point.temperature is None
        assert point.dew_point is None
        assert point.wind_speed is None

    def test_missing_timestamp_skips_row(self):
        assert _hourly_point(_row(ftime_utc=None, ftime=None)) is None

    def test_latest_run_filter(self):
        stale = _row(runtime_utc="2026-07-18T06:00:00.000")
        fresh = _row()
        assert _latest_run_rows([stale, fresh]) == [fresh]


class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_normalizes_latest_run(self):
        payload = {
            "schema": {"fields": []},
            "data": [
                _row(),
                _row(
                    ftime_utc="2026-07-18T21:00:00.000",
                    tmp=91,
                    p06=None,
                ),
                _row(runtime_utc="2026-07-18T06:00:00.000", tmp=50),
            ],
        }

        def handler(request: httpx2.Request) -> httpx2.Response:
            assert request.url.params["station"] == "KSBD"
            assert request.url.params["model"] == "NBS"
            return httpx2.Response(200, json=payload)

        config = nbm_plugin.validate_config({"station_id": "KSBD"})
        instance = await nbm_plugin.initialize(config)
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            result = await instance.fetch_forecast(_PARAMS, client)

        assert result.status == "success"
        forecast = result.forecasts[0]
        assert len(forecast.hourly) == 2  # the stale 06z row is dropped
        assert forecast.hourly[0].temperature == pytest.approx((83 - 32) * 5 / 9)
        assert forecast.hourly[1].temperature == pytest.approx((91 - 32) * 5 / 9)
        assert forecast.hourly[1].precipitation_probability is None
        assert forecast.daily == []

    @pytest.mark.asyncio
    async def test_fetch_reports_malformed_payload(self):
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json={"detail": "nope"}),
        )
        config = nbm_plugin.validate_config({"station_id": "KSBD"})
        instance = await nbm_plugin.initialize(config)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_PARAMS, client)
        assert result.status == "error"
        assert result.code == ErrorCode.PARSE

    @pytest.mark.asyncio
    async def test_fetch_reports_malformed_row_and_preserves_raw_payload(self):
        payload = {"data": [_row(ftime_utc="not-a-timestamp")]}
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=payload),
        )
        config = nbm_plugin.validate_config({"station_id": "KSBD"})
        instance = await nbm_plugin.initialize(config)
        params = _PARAMS.model_copy(update={"include_raw": True})

        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(params, client)

        assert result.status == "error"
        assert result.code == ErrorCode.PARSE
        assert result.message.startswith("Failed to parse NBM payload:")
        assert result.raw == payload

    @pytest.mark.asyncio
    async def test_fetch_reports_http_error(self):
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(503, text="unavailable"),
        )
        config = nbm_plugin.validate_config({"station_id": "KSBD"})
        instance = await nbm_plugin.initialize(config)
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(_PARAMS, client)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_capabilities(self):
        config = nbm_plugin.validate_config({"station_id": "KSBD"})
        instance = await nbm_plugin.initialize(config)
        capabilities = instance.get_capabilities()
        assert capabilities.granularity_hourly
        assert not capabilities.granularity_daily
        assert not capabilities.requires_api_key
        assert capabilities.coverage == "us_only"
        assert capabilities.max_horizon_hourly_hours == pytest.approx(72.0)
