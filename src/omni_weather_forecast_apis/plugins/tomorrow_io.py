"""Tomorrow.io adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_daily_point,
    build_hourly_point,
    build_minutely_point,
    build_source_forecast,
    first_present,
    normalize_probability,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ErrorCode,
    Granularity,
    MinutelyDataPoint,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    TomorrowIOConfig,
    WeatherCondition,
    WeatherDataPoint,
)

if TYPE_CHECKING:
    import httpx

_FORECAST_URL = "https://api.tomorrow.io/v4/weather/forecast"
_CAPABILITIES = PluginCapabilities(
    granularity_minutely=True,
    granularity_hourly=True,
    granularity_daily=True,
    max_horizon_hourly_hours=120,
    max_horizon_daily_days=6,
)
_WEATHER_CODE_MAP: dict[int, WeatherCondition] = {
    1000: WeatherCondition.CLEAR,
    1001: WeatherCondition.OVERCAST,
    1100: WeatherCondition.MOSTLY_CLEAR,
    1101: WeatherCondition.PARTLY_CLOUDY,
    1102: WeatherCondition.MOSTLY_CLOUDY,
    2000: WeatherCondition.FOG,
    2100: WeatherCondition.FOG,
    4000: WeatherCondition.DRIZZLE,
    4001: WeatherCondition.RAIN,
    4200: WeatherCondition.LIGHT_RAIN,
    4201: WeatherCondition.HEAVY_RAIN,
    5000: WeatherCondition.SNOW,
    5001: WeatherCondition.LIGHT_SNOW,
    5100: WeatherCondition.LIGHT_SNOW,
    5101: WeatherCondition.HEAVY_SNOW,
    6000: WeatherCondition.FREEZING_RAIN,
    6001: WeatherCondition.FREEZING_RAIN,
    6200: WeatherCondition.FREEZING_RAIN,
    6201: WeatherCondition.HEAVY_RAIN,
    7000: WeatherCondition.HAIL,
    7101: WeatherCondition.HAIL,
    7102: WeatherCondition.HAIL,
    8000: WeatherCondition.THUNDERSTORM,
}


def _timeline_list(raw: dict[str, Any], timestep: str) -> list[Mapping[str, Any]]:
    timelines = raw.get("timelines")
    if isinstance(timelines, Mapping):
        timeline = timelines.get(timestep)
        if isinstance(timeline, list):
            return [item for item in timeline if isinstance(item, Mapping)]
    if isinstance(timelines, list):
        for entry in timelines:
            if isinstance(entry, Mapping) and entry.get("timestep") == timestep:
                intervals = entry.get("intervals", [])
                return [item for item in intervals if isinstance(item, Mapping)]
    return []


def _condition_from_values(
    values: Mapping[str, Any],
) -> tuple[WeatherCondition | None, int | None]:
    code = as_float(
        first_present(
            values,
            "weatherCode",
            "weatherCodeFullDay",
            "weatherCodeDay",
            "weatherCodeMinutely",
        ),
    )
    normalized_code = int(code) if code is not None else None
    return (
        _WEATHER_CODE_MAP.get(normalized_code) if normalized_code is not None else None
    ), normalized_code


def _parse_minutely(entry: Mapping[str, Any]) -> MinutelyDataPoint:
    values = entry.get("values")
    if not isinstance(values, Mapping):
        values = {}
    return build_minutely_point(
        entry["startTime"],
        precipitation_intensity=as_float(
            first_present(values, "precipitationIntensity", "rainIntensity"),
        ),
        precipitation_probability=normalize_probability(
            values.get("precipitationProbability"),
        ),
    )


def _parse_hourly(entry: Mapping[str, Any]) -> WeatherDataPoint:
    values = entry.get("values")
    if not isinstance(values, Mapping):
        values = {}
    condition, code = _condition_from_values(values)
    return build_hourly_point(
        entry["startTime"],
        temperature=as_float(values.get("temperature")),
        apparent_temperature=as_float(values.get("temperatureApparent")),
        dew_point=as_float(values.get("dewPoint")),
        humidity=as_float(values.get("humidity")),
        wind_speed=as_float(values.get("windSpeed")),
        wind_gust=as_float(values.get("windGust")),
        wind_direction=as_float(values.get("windDirection")),
        pressure_sea=as_float(values.get("pressureSeaLevel")),
        pressure_surface=as_float(values.get("pressureSurfaceLevel")),
        precipitation=as_float(
            first_present(values, "precipitationIntensity", "rainIntensity"),
        ),
        precipitation_probability=normalize_probability(
            values.get("precipitationProbability"),
        ),
        rain=as_float(values.get("rainIntensity")),
        snow=as_float(values.get("snowIntensity")),
        cloud_cover=as_float(values.get("cloudCover")),
        visibility=as_float(values.get("visibility")),
        uv_index=as_float(values.get("uvIndex")),
        solar_radiation_ghi=as_float(values.get("solarGHI")),
        solar_radiation_dni=as_float(values.get("solarDNI")),
        solar_radiation_dhi=as_float(values.get("solarDHI")),
        condition=condition,
        condition_code_original=code,
        is_day=bool(values.get("isDay")) if values.get("isDay") is not None else None,
    )


def _parse_daily(entry: Mapping[str, Any]) -> DailyDataPoint:
    values = entry.get("values")
    if not isinstance(values, Mapping):
        values = {}
    condition, _ = _condition_from_values(values)
    return build_daily_point(
        entry["startTime"],
        temperature_max=as_float(values.get("temperatureMax")),
        temperature_min=as_float(values.get("temperatureMin")),
        apparent_temperature_max=as_float(values.get("temperatureApparentMax")),
        apparent_temperature_min=as_float(values.get("temperatureApparentMin")),
        wind_speed_max=as_float(values.get("windSpeedMax")),
        wind_gust_max=as_float(values.get("windGustMax")),
        wind_direction_dominant=as_float(values.get("windDirection")),
        precipitation_sum=as_float(values.get("precipitationIntensityAvg")),
        precipitation_probability_max=normalize_probability(
            values.get("precipitationProbabilityMax"),
        ),
        rain_sum=as_float(values.get("rainAccumulation")),
        snowfall_sum=as_float(values.get("snowAccumulation")),
        cloud_cover_mean=as_float(values.get("cloudCoverAvg")),
        uv_index_max=as_float(values.get("uvIndexMax")),
        visibility_min=as_float(values.get("visibilityMin")),
        humidity_mean=as_float(values.get("humidityAvg")),
        pressure_sea_mean=as_float(values.get("pressureSeaLevelAvg")),
        condition=condition,
        sunrise=first_present(values, "sunriseTime", "sunrise"),
        sunset=first_present(values, "sunsetTime", "sunset"),
        moonrise=first_present(values, "moonriseTime", "moonrise"),
        moonset=first_present(values, "moonsetTime", "moonset"),
        moon_phase=as_float(values.get("moonPhase")),
    )


class _TomorrowIOInstance(BasePluginInstance[TomorrowIOConfig]):
    """Configured Tomorrow.io adapter."""

    def __init__(self, config: TomorrowIOConfig) -> None:
        super().__init__(ProviderId.TOMORROW_IO, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """Fetch and normalize Tomorrow.io forecast data."""

        requested_timesteps: list[str] = []
        if Granularity.MINUTELY in params.granularity:
            requested_timesteps.append("1m")
        if Granularity.HOURLY in params.granularity:
            requested_timesteps.append("1h")
        if Granularity.DAILY in params.granularity:
            requested_timesteps.append("1d")
        request_params: dict[str, Any] = {
            "location": f"{params.latitude},{params.longitude}",
            "timesteps": ",".join(requested_timesteps),
            "apikey": self.config.api_key,
            "units": "metric",
        }
        if self.config.fields:
            request_params["fields"] = ",".join(self.config.fields)
        raw, error = await self._get_json(client, _FORECAST_URL, params=request_params)
        if error is not None:
            return error
        if not isinstance(raw, dict):
            return self._error(
                ErrorCode.PARSE,
                "Unexpected Tomorrow.io payload",
                raw=raw,
            )

        minutely = [
            _parse_minutely(item)
            for item in _timeline_list(raw, "1m")
            if "startTime" in item
        ]
        hourly = [
            _parse_hourly(item)
            for item in _timeline_list(raw, "1h")
            if "startTime" in item
        ]
        daily = [
            _parse_daily(item)
            for item in _timeline_list(raw, "1d")
            if "startTime" in item
        ]
        return self._success(
            [
                build_source_forecast(
                    self.provider_id,
                    minutely=minutely,
                    hourly=hourly,
                    daily=daily,
                ),
            ],
            raw=raw if params.include_raw else None,
        )


class _TomorrowIOPlugin(BasePlugin[TomorrowIOConfig]):
    """Tomorrow.io plugin facade."""

    config_model = TomorrowIOConfig
    instance_cls = _TomorrowIOInstance
    _id = ProviderId.TOMORROW_IO
    _name = "Tomorrow.io"


tomorrow_io_plugin = _TomorrowIOPlugin()

__all__ = ["tomorrow_io_plugin"]
