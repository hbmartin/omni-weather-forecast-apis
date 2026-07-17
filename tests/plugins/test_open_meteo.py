"""Tests for Open-Meteo plugin using httpx2 mocks."""

from datetime import UTC, datetime

import httpx2
import pytest

from omni_weather_forecast_apis.plugins.open_meteo import (
    OpenMeteoConfig,
    OpenMeteoInstance,
    _scope_model_section,
    open_meteo_plugin,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    Granularity,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchSuccess,
    ProviderId,
)


class TestOpenMeteoPlugin:
    def test_plugin_id(self) -> None:
        assert open_meteo_plugin._id == ProviderId.OPEN_METEO

    def test_validate_config_defaults(self) -> None:
        config = open_meteo_plugin.validate_config({})
        assert isinstance(config, OpenMeteoConfig)
        assert config.api_key is None
        assert config.models == ["best_match"]


class TestOpenMeteoInstance:
    @pytest.fixture
    def instance(self) -> OpenMeteoInstance:
        config = OpenMeteoConfig()
        return OpenMeteoInstance(config)

    def test_capabilities(self, instance: OpenMeteoInstance) -> None:
        caps = instance.get_capabilities()
        assert caps.requires_api_key is False
        assert caps.multi_model is True

    def test_scope_model_section_handles_non_list_time(self) -> None:
        section = _scope_model_section(
            {
                "time": "invalid",
                "temperature_2m_icon_d2": [21.0],
            },
            "icon_d2",
        )

        assert section == {
            "time": "invalid",
            "temperature_2m": [21.0],
        }

    @pytest.mark.asyncio
    async def test_fetch_success(self, instance: OpenMeteoInstance) -> None:
        mock_response = {
            "hourly": {
                "time": ["2024-01-01T00:00", "2024-01-01T01:00"],
                "temperature_2m": [20.0, 19.5],
                "apparent_temperature": [18.0, 17.5],
                "weather_code": [0, 1],
                "is_day": [1, 0],
            },
            "daily": {
                "time": ["2024-01-01"],
                "temperature_2m_max": [25.0],
                "temperature_2m_min": [10.0],
                "weather_code": [0],
                "sunrise": ["2024-01-01T07:00"],
                "sunset": ["2024-01-01T17:00"],
            },
        }

        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=mock_response),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY, Granularity.DAILY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 1
        assert len(result.forecasts[0].hourly) == 2
        assert result.forecasts[0].hourly[0].temperature == 20.0
        assert len(result.forecasts[0].daily) == 1

    @pytest.mark.asyncio
    async def test_fetch_uses_and_localizes_requested_timezone(
        self,
        instance: OpenMeteoInstance,
    ) -> None:
        captured_timezone = ""

        def handler(request: httpx2.Request) -> httpx2.Response:
            nonlocal captured_timezone
            captured_timezone = request.url.params["timezone"]
            return httpx2.Response(
                200,
                json={
                    "timezone": "America/Los_Angeles",
                    "minutely_15": {
                        "time": ["2024-01-01T00:00"],
                        "precipitation": [0.5],
                    },
                    "hourly": {
                        "time": ["2024-01-01T00:00"],
                        "temperature_2m": [20.0],
                    },
                    "daily": {
                        "time": ["2024-01-01"],
                        "sunrise": ["2024-01-01T07:00"],
                    },
                },
            )

        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler),
        ) as client:
            result = await instance.fetch_forecast(
                PluginFetchParams(
                    latitude=34.0,
                    longitude=-117.0,
                    granularity=[
                        Granularity.MINUTELY,
                        Granularity.HOURLY,
                        Granularity.DAILY,
                    ],
                    timezone="America/Los_Angeles",
                ),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert captured_timezone == "America/Los_Angeles"
        assert forecast.timezone == "America/Los_Angeles"
        assert forecast.minutely[0].timestamp == datetime(2024, 1, 1, 8, tzinfo=UTC)
        assert forecast.hourly[0].timestamp == datetime(2024, 1, 1, 8, tzinfo=UTC)
        assert forecast.daily[0].sunrise == datetime(2024, 1, 1, 15, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_fetch_parses_full_dst_fall_back_day(
        self,
        instance: OpenMeteoInstance,
    ) -> None:
        """A fall-back day must parse fully, not be discarded on the bad hour.

        Open-Meteo emits offset-free local timestamps. In America/Los_Angeles
        the 01:00 hour of 2024-11-03 occurs twice; the old strict localizer
        raised on that ambiguous hour and dropped every point in the run.
        """
        mock_response = {
            "timezone": "America/Los_Angeles",
            "hourly": {
                "time": [
                    "2024-11-03T00:00",
                    "2024-11-03T01:00",
                    "2024-11-03T02:00",
                ],
                "temperature_2m": [10.0, 9.5, 9.0],
            },
        }

        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=mock_response),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                PluginFetchParams(
                    latitude=34.0,
                    longitude=-117.0,
                    granularity=[Granularity.HOURLY],
                    timezone="America/Los_Angeles",
                ),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        forecast = result.forecasts[0]
        assert len(forecast.hourly) == 3
        # The ambiguous 01:00 resolves to the earlier (pre-transition) instant.
        assert forecast.hourly[1].timestamp == datetime(2024, 11, 3, 8, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_fetch_multi_model(self) -> None:
        """Multi-model responses suffix each variable key inside one section.

        Open-Meteo returns a single ``hourly``/``daily`` section no matter how
        many models are requested; asking for more than one suffixes every
        variable key with the model name. Parsing must scope the keys per model
        rather than looking for a per-model section.
        """
        config = OpenMeteoConfig(models=["ecmwf_ifs025", "gfs_seamless"])
        instance = OpenMeteoInstance(config)

        mock_response = {
            "hourly": {
                "time": ["2024-01-01T00:00"],
                "temperature_2m_ecmwf_ifs025": [21.0],
                "weather_code_ecmwf_ifs025": [0],
                "is_day_ecmwf_ifs025": [1],
                "temperature_2m_gfs_seamless": [22.0],
                "weather_code_gfs_seamless": [1],
                "is_day_gfs_seamless": [1],
            },
            "daily": {
                "time": ["2024-01-01"],
                "temperature_2m_max_ecmwf_ifs025": [25.0],
                "temperature_2m_max_gfs_seamless": [26.0],
            },
        }

        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=mock_response),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY, Granularity.DAILY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 2

        ecmwf, gfs = result.forecasts
        assert ecmwf.source.model == "ecmwf_ifs025"
        assert ecmwf.hourly[0].temperature == 21.0
        assert ecmwf.daily[0].temperature_max == 25.0

        assert gfs.source.model == "gfs_seamless"
        assert gfs.hourly[0].temperature == 22.0
        assert gfs.daily[0].temperature_max == 26.0

    @pytest.mark.asyncio
    async def test_fetch_multi_model_does_not_bleed_across_models(self) -> None:
        """A model missing a variable must not inherit another model's values."""
        config = OpenMeteoConfig(models=["best_match", "ecmwf_ifs025"])
        instance = OpenMeteoInstance(config)

        mock_response = {
            "hourly": {
                "time": ["2024-01-01T00:00"],
                "temperature_2m_best_match": [21.0],
                "temperature_2m_ecmwf_ifs025": [22.0],
                # Only best_match reports wind.
                "wind_speed_10m_best_match": [5.0],
            },
        }

        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=mock_response),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        best_match, ecmwf = result.forecasts
        assert best_match.hourly[0].wind_speed == 5.0
        assert ecmwf.hourly[0].temperature == 22.0
        assert ecmwf.hourly[0].wind_speed is None

    @pytest.mark.asyncio
    async def test_fetch_multi_model_drops_rows_beyond_model_horizon(self) -> None:
        """Shared time axes must not create empty rows for shorter models."""
        config = OpenMeteoConfig(models=["best_match", "icon_d2"])
        instance = OpenMeteoInstance(config)

        mock_response = {
            "hourly": {
                "time": [
                    "2024-01-01T00:00",
                    "2024-01-01T01:00",
                    "2024-01-01T02:00",
                    "2024-01-01T03:00",
                ],
                "temperature_2m_best_match": [20.0, 19.0, 18.0, 17.0],
                "is_day_best_match": [0, 0, 0, 0],
                "temperature_2m_icon_d2": [21.0, None, 19.0, None],
                # Open-Meteo keeps model-independent values populated after a
                # model's weather forecast ends.
                "is_day_icon_d2": [0, 0, 0, 0],
            },
            "daily": {
                "time": ["2024-01-01", "2024-01-02"],
                "temperature_2m_max_best_match": [25.0, 24.0],
                "sunrise_best_match": [
                    "2024-01-01T07:00",
                    "2024-01-02T07:00",
                ],
                "temperature_2m_max_icon_d2": [26.0, None],
                "sunrise_icon_d2": [
                    "2024-01-01T07:00",
                    "2024-01-02T07:00",
                ],
            },
        }

        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json=mock_response),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                PluginFetchParams(
                    latitude=52.5,
                    longitude=13.4,
                    granularity=[Granularity.HOURLY, Granularity.DAILY],
                ),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        best_match, icon_d2 = result.forecasts
        assert len(best_match.hourly) == 4
        assert len(best_match.daily) == 2
        assert len(icon_d2.hourly) == 3
        assert [point.temperature for point in icon_d2.hourly] == [21.0, None, 19.0]
        assert len(icon_d2.daily) == 1
        assert icon_d2.daily[0].temperature_max == 26.0

    @pytest.mark.asyncio
    async def test_fetch_http_error(self, instance: OpenMeteoInstance) -> None:
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(500, json={"error": "server error"}),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchError)
        assert result.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_fetch_empty_models_defaults_to_best_match(self) -> None:
        instance = OpenMeteoInstance(OpenMeteoConfig(models=[]))
        transport = httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200,
                json={
                    "hourly": {
                        "time": ["2024-01-01T00:00"],
                        "temperature_2m": [18.0],
                        "weather_code": [0],
                        "is_day": [1],
                    },
                },
            ),
        )
        async with httpx2.AsyncClient(transport=transport) as client:
            result = await instance.fetch_forecast(
                PluginFetchParams(
                    latitude=34.0,
                    longitude=-117.0,
                    granularity=[Granularity.HOURLY],
                ),
                client,
            )

        assert isinstance(result, PluginFetchSuccess)
        assert len(result.forecasts) == 1
        assert result.forecasts[0].source.model == "best_match"
        assert result.forecasts[0].hourly[0].temperature == 18.0

    @pytest.mark.asyncio
    async def test_fetch_converts_units(self, instance: OpenMeteoInstance) -> None:
        captured_params: dict[str, str] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured_params["wind_speed_unit"] = request.url.params["wind_speed_unit"]
            return httpx2.Response(
                200,
                json={
                    "minutely_15": {
                        "time": ["2024-01-01T00:00"],
                        "precipitation": [0.5],
                        "precipitation_probability": [25],
                    },
                    "hourly": {
                        "time": ["2024-01-01T00:00"],
                        "temperature_2m": [10.0],
                        "weather_code": [71],
                        "snowfall": [1.2],
                        "snowfall_water_equivalent": [1.4],
                        "direct_normal_irradiance": [512.0],
                    },
                    "daily": {
                        "time": ["2024-01-01"],
                        "temperature_2m_max": [12.0],
                        "temperature_2m_min": [5.0],
                        "weather_code": [71],
                        "snowfall_sum": [2.3],
                        "snowfall_water_equivalent_sum": [2.6],
                    },
                },
            )

        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            params = PluginFetchParams(
                latitude=34.0,
                longitude=-117.0,
                granularity=[
                    Granularity.MINUTELY,
                    Granularity.HOURLY,
                    Granularity.DAILY,
                ],
            )
            result = await instance.fetch_forecast(params, client)

        assert isinstance(result, PluginFetchSuccess)
        assert captured_params["wind_speed_unit"] == "ms"
        forecast = result.forecasts[0]
        assert forecast.minutely[0].precipitation_intensity == 2.0
        # snowfall (cm of depth) feeds snowfall_depth; the liquid field comes
        # from snowfall_water_equivalent (already mm).
        assert forecast.hourly[0].snowfall_depth == 12.0
        assert forecast.hourly[0].snow == 1.4
        assert forecast.hourly[0].solar_radiation_dni == 512.0
        assert forecast.daily[0].snowfall_depth_sum == 23.0
        assert forecast.daily[0].snowfall_sum == 2.6
