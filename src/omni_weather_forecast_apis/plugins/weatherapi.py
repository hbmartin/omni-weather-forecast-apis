"""WeatherAPI.com adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from omni_weather_forecast_apis.mapping import condition_from_text
from omni_weather_forecast_apis.mapping.units import ms_from_kmh
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_alert,
    build_daily_point,
    build_hourly_point,
    build_source_forecast,
    normalize_probability,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ErrorCode,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.types.plugin import ProviderConfigModel

if TYPE_CHECKING:
    import httpx

from pydantic import Field


class WeatherAPIConfig(ProviderConfigModel):
    api_key: str = Field(min_length=1)
    days: int = Field(default=7, ge=1, le=14)
    aqi: bool = False
    alerts: bool = True


_FORECAST_URL = "https://api.weatherapi.com/v1/forecast.json"
_CAPABILITIES = PluginCapabilities(
    granularity_minutely=False,
    granularity_hourly=True,
    granularity_daily=True,
    max_horizon_hourly_hours=336,
    max_horizon_daily_days=14,
    alerts=True,
)


def _parse_condition(entry: Mapping[str, Any]) -> tuple[str | None, int | str | None]:
    condition = entry.get("condition")
    if not isinstance(condition, Mapping):
        return None, None
    text = condition.get("text")
    code = condition.get("code")
    return text if isinstance(text, str) else None, (
        code if isinstance(code, (int, str)) else None
    )


def _parse_hour(entry: Mapping[str, Any]) -> WeatherDataPoint:
    text, code = _parse_condition(entry)
    return build_hourly_point(
        entry["time_epoch"],
        temperature=as_float(entry.get("temp_c")),
        apparent_temperature=as_float(entry.get("feelslike_c")),
        dew_point=as_float(entry.get("dewpoint_c")),
        humidity=as_float(entry.get("humidity")),
        wind_speed=(
            ms_from_kmh(as_float(entry.get("wind_kph")) or 0.0)
            if as_float(entry.get("wind_kph")) is not None
            else None
        ),
        wind_gust=(
            ms_from_kmh(as_float(entry.get("gust_kph")) or 0.0)
            if as_float(entry.get("gust_kph")) is not None
            else None
        ),
        wind_direction=as_float(entry.get("wind_degree")),
        pressure_sea=as_float(entry.get("pressure_mb")),
        precipitation=as_float(entry.get("precip_mm")),
        precipitation_probability=normalize_probability(
            entry.get("chance_of_rain") or entry.get("chance_of_snow"),
        ),
        rain=as_float(entry.get("precip_mm")),
        cloud_cover=as_float(entry.get("cloud")),
        visibility=as_float(entry.get("vis_km")),
        uv_index=as_float(entry.get("uv")),
        condition=condition_from_text(text),
        condition_original=text,
        condition_code_original=code,
        is_day=bool(entry.get("is_day")) if entry.get("is_day") is not None else None,
    )


def _parse_forecast_day(entry: Mapping[str, Any]) -> DailyDataPoint:
    day = entry.get("day")
    if not isinstance(day, Mapping):
        day = {}
    text, _code = _parse_condition(day)
    return build_daily_point(
        entry["date"],
        temperature_max=as_float(day.get("maxtemp_c")),
        temperature_min=as_float(day.get("mintemp_c")),
        apparent_temperature_max=as_float(day.get("maxtemp_c")),
        apparent_temperature_min=as_float(day.get("mintemp_c")),
        wind_speed_max=(
            ms_from_kmh(as_float(day.get("maxwind_kph")) or 0.0)
            if as_float(day.get("maxwind_kph")) is not None
            else None
        ),
        precipitation_sum=as_float(day.get("totalprecip_mm")),
        precipitation_probability_max=normalize_probability(
            day.get("daily_chance_of_rain") or day.get("daily_chance_of_snow"),
        ),
        rain_sum=as_float(day.get("totalprecip_mm")),
        uv_index_max=as_float(day.get("uv")),
        visibility_min=as_float(day.get("avgvis_km")),
        humidity_mean=as_float(day.get("avghumidity")),
        condition=condition_from_text(text),
        summary=text,
    )


class _WeatherAPIInstance(BasePluginInstance[WeatherAPIConfig]):
    """Configured WeatherAPI.com adapter."""

    def __init__(self, config: WeatherAPIConfig) -> None:
        super().__init__(ProviderId.WEATHERAPI, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """Fetch and normalize WeatherAPI.com forecast data."""

        raw, error = await self._get_json(
            client,
            _FORECAST_URL,
            params={
                "key": self.config.api_key,
                "q": f"{params.latitude},{params.longitude}",
                "days": self.config.days,
                "aqi": "yes" if self.config.aqi else "no",
                "alerts": "yes" if self.config.alerts else "no",
                "lang": params.language,
            },
        )
        if error is not None:
            return error
        if not isinstance(raw, dict):
            return self._error(
                ErrorCode.PARSE,
                "Unexpected WeatherAPI payload",
                raw=raw,
            )

        forecast = raw.get("forecast")
        forecast_days = (
            forecast.get("forecastday", []) if isinstance(forecast, Mapping) else []
        )
        hourly = [
            _parse_hour(hour)
            for day in forecast_days
            if isinstance(day, Mapping)
            for hour in day.get("hour", [])
            if isinstance(hour, Mapping) and "time_epoch" in hour
        ]
        daily = [
            _parse_forecast_day(day)
            for day in forecast_days
            if isinstance(day, Mapping) and "date" in day
        ]
        alerts_root = raw.get("alerts")
        alert_entries = (
            alerts_root.get("alert", []) if isinstance(alerts_root, Mapping) else []
        )
        alerts = [
            build_alert(
                sender_name=str(entry.get("sender") or "WeatherAPI.com"),
                event=str(entry.get("event") or entry.get("headline") or "Alert"),
                start=entry["effective"],
                end=entry.get("expires"),
                description=str(entry.get("desc") or entry.get("instruction") or ""),
                severity=entry.get("severity"),
            )
            for entry in alert_entries
            if isinstance(entry, Mapping) and "effective" in entry
        ]
        return self._success(
            [
                build_source_forecast(
                    self.provider_id,
                    hourly=hourly,
                    daily=daily,
                    alerts=alerts,
                ),
            ],
            raw=raw if params.include_raw else None,
        )


class _WeatherAPIPlugin(BasePlugin[WeatherAPIConfig]):
    """WeatherAPI.com plugin facade."""

    config_model = WeatherAPIConfig
    instance_cls = _WeatherAPIInstance
    _id = ProviderId.WEATHERAPI
    _name = "WeatherAPI.com"


weatherapi_plugin = _WeatherAPIPlugin()

__all__ = ["weatherapi_plugin"]
