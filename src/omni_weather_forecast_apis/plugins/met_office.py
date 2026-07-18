"""UK Met Office Global Spot (Weather DataHub site-specific) provider adapter."""

from __future__ import annotations

from typing import Any, Final

import httpx2
from pydantic import Field

from omni_weather_forecast_apis.mapping import (
    hpa_from_pa,
    km_from_meters,
    map_met_office_condition,
    met_office_is_day,
    safe_convert,
)
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_daily_point,
    build_hourly_point,
    build_source_forecast,
    first_present,
    optional_max,
    probability_from_percent_value,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ErrorCode,
    Granularity,
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherCondition,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.types.plugin import ProviderConfigModel


class MetOfficeConfig(ProviderConfigModel):
    api_key: str = Field(min_length=1)


MET_OFFICE_BASE_URL: Final = (
    "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point"
)

_CAPABILITIES = PluginCapabilities(
    granularity_minutely=False,
    granularity_hourly=True,
    granularity_daily=True,
    max_horizon_hourly_hours=48,
    max_horizon_daily_days=6,
    requires_api_key=True,
    multi_model=False,
    coverage="global",
    alerts=False,
)


def _time_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the timeSeries rows from a Global Spot GeoJSON payload."""

    features = payload.get("features")
    if not isinstance(features, list) or not features:
        return []
    feature = features[0]
    if not isinstance(feature, dict):
        return []
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return []
    series = properties.get("timeSeries")
    if not isinstance(series, list):
        return []
    return [entry for entry in series if isinstance(entry, dict)]


def _future_daily_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Drop the leading historical row included by the daily endpoint."""

    return _time_series(payload)[1:]


def _weather_code(value: Any) -> int | None:
    numeric = as_float(value)
    return int(numeric) if numeric is not None else None


def _condition(code: int | None) -> WeatherCondition | None:
    return map_met_office_condition(code) if code is not None else None


def _parse_hour(entry: dict[str, Any]) -> WeatherDataPoint:
    code = _weather_code(entry.get("significantWeatherCode"))
    return build_hourly_point(
        entry["time"],
        temperature=as_float(entry.get("screenTemperature")),
        apparent_temperature=as_float(entry.get("feelsLikeTemperature")),
        dew_point=as_float(entry.get("screenDewPointTemperature")),
        humidity=as_float(entry.get("screenRelativeHumidity")),
        wind_speed=as_float(entry.get("windSpeed10m")),
        wind_gust=as_float(entry.get("windGustSpeed10m")),
        wind_direction=as_float(entry.get("windDirectionFrom10m")),
        pressure_sea=safe_convert(as_float(entry.get("mslp")), hpa_from_pa),
        precipitation=as_float(entry.get("totalPrecipAmount")),
        precipitation_probability=probability_from_percent_value(
            entry.get("probOfPrecipitation"),
        ),
        snow=as_float(entry.get("totalSnowAmount")),
        visibility=safe_convert(as_float(entry.get("visibility")), km_from_meters),
        uv_index=as_float(entry.get("uvIndex")),
        condition=_condition(code),
        condition_code_original=code,
        is_day=met_office_is_day(code) if code is not None else None,
    )


def _parse_day(entry: dict[str, Any]) -> DailyDataPoint:
    day_code = _weather_code(entry.get("daySignificantWeatherCode"))
    night_code = _weather_code(entry.get("nightSignificantWeatherCode"))
    return build_daily_point(
        entry["time"],
        temperature_max=as_float(entry.get("dayMaxScreenTemperature")),
        temperature_min=as_float(entry.get("nightMinScreenTemperature")),
        apparent_temperature_max=as_float(
            first_present(entry, "dayMaxFeelsLikeTemp", "dayMaxFeelsLikeTemperature"),
        ),
        apparent_temperature_min=as_float(
            first_present(
                entry,
                "nightMinFeelsLikeTemp",
                "nightMinFeelsLikeTemperature",
            ),
        ),
        wind_speed_max=optional_max(
            as_float(entry.get("midday10MWindSpeed")),
            as_float(entry.get("midnight10MWindSpeed")),
        ),
        wind_gust_max=optional_max(
            as_float(entry.get("midday10MWindGust")),
            as_float(entry.get("midnight10MWindGust")),
        ),
        wind_direction_dominant=as_float(entry.get("midday10MWindDirection")),
        precipitation_probability_max=probability_from_percent_value(
            optional_max(
                as_float(entry.get("dayProbabilityOfPrecipitation")),
                as_float(entry.get("nightProbabilityOfPrecipitation")),
            ),
        ),
        uv_index_max=as_float(entry.get("maxUvIndex")),
        condition=_condition(day_code) or _condition(night_code),
    )


class MetOfficeInstance(BasePluginInstance[MetOfficeConfig]):
    """Configured Met Office Global Spot provider."""

    def __init__(self, config: MetOfficeConfig) -> None:
        super().__init__(ProviderId.MET_OFFICE, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        hourly: list[WeatherDataPoint] = []
        daily: list[DailyDataPoint] = []
        raw: dict[str, Any] = {}

        try:
            if Granularity.HOURLY in params.granularity:
                payload = await self._fetch_timesteps(client, params, "hourly")
                if isinstance(payload, PluginFetchError):
                    return payload
                hourly = [_parse_hour(entry) for entry in _time_series(payload)]
                if params.include_raw:
                    raw["hourly"] = payload

            if Granularity.DAILY in params.granularity:
                payload = await self._fetch_timesteps(client, params, "daily")
                if isinstance(payload, PluginFetchError):
                    return payload
                daily = [_parse_day(entry) for entry in _future_daily_series(payload)]
                if params.include_raw:
                    raw["daily"] = payload
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse Met Office payload: {exc}",
            )

        forecasts = [
            build_source_forecast(
                ProviderId.MET_OFFICE,
                timezone=params.timezone,
                hourly=hourly,
                daily=daily,
            ),
        ]
        return self._success(forecasts, raw=raw if params.include_raw else None)

    async def _fetch_timesteps(
        self,
        client: httpx2.AsyncClient,
        params: PluginFetchParams,
        timesteps: str,
    ) -> dict[str, Any] | PluginFetchError:
        return await self._get_json_dict(
            client,
            f"{MET_OFFICE_BASE_URL}/{timesteps}",
            params={
                "latitude": params.latitude,
                "longitude": params.longitude,
                "excludeParameterMetadata": "true",
            },
            headers={"apikey": self.config.api_key, "Accept": "application/json"},
            payload_name=f"Met Office {timesteps}",
        )


class MetOfficePlugin(BasePlugin[MetOfficeConfig]):
    """Met Office Global Spot plugin facade."""

    config_model = MetOfficeConfig
    instance_cls = MetOfficeInstance
    _id = ProviderId.MET_OFFICE
    _name = "Met Office"


met_office_plugin = MetOfficePlugin()

__all__ = ["MetOfficeConfig", "MetOfficeInstance", "met_office_plugin"]
