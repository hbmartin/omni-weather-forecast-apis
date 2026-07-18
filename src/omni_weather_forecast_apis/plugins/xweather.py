"""Xweather (formerly Aeris Weather) provider adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

import httpx2
from pydantic import Field

from omni_weather_forecast_apis.mapping import (
    map_xweather_coded,
    mm_from_cm,
    ms_from_kmh,
    safe_convert,
)
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_daily_point,
    build_hourly_point,
    build_source_forecast,
    fallback_condition,
    first_present,
    optional_mean,
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
from omni_weather_forecast_apis.utils import zoneinfo_from_name


class XweatherConfig(ProviderConfigModel):
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    hourly_limit: int = Field(default=120, ge=1, le=240)
    daily_limit: int = Field(default=10, ge=1, le=15)


XWEATHER_BASE_URL: Final = "https://data.api.xweather.com"

_XWEATHER_ERROR_CODES: Final[dict[str, ErrorCode]] = {
    "invalid_client": ErrorCode.AUTH_FAILED,
    "unauthorized": ErrorCode.AUTH_FAILED,
    "invalid_location": ErrorCode.NOT_AVAILABLE,
    "maxed_out": ErrorCode.RATE_LIMITED,
    "warn_no_data": ErrorCode.NO_DATA,
}


def _periods(response: list[Any]) -> list[dict[str, Any]]:
    if not response or not isinstance(response[0], dict):
        return []
    periods = response[0].get("periods")
    if not isinstance(periods, list):
        return []
    return [period for period in periods if isinstance(period, dict)]


def _profile_timezone(response: list[Any]) -> str | None:
    if not response or not isinstance(response[0], dict):
        return None
    profile = response[0].get("profile")
    if not isinstance(profile, dict):
        return None
    timezone = profile.get("tz")
    return timezone if isinstance(timezone, str) else None


def _condition(period: dict[str, Any]) -> WeatherCondition | None:
    coded = period.get("weatherPrimaryCoded")
    clouds = period.get("cloudsCoded")
    mapped = map_xweather_coded(
        coded if isinstance(coded, str) else None,
        clouds if isinstance(clouds, str) else None,
    )
    text = period.get("weatherPrimary")
    return fallback_condition(mapped, text if isinstance(text, str) else None)


def _condition_text(period: dict[str, Any]) -> str | None:
    text = period.get("weatherPrimary")
    return text if isinstance(text, str) else None


def _condition_code(period: dict[str, Any]) -> str | None:
    coded = period.get("weatherPrimaryCoded")
    return coded if isinstance(coded, str) else None


def _parse_hour(period: dict[str, Any]) -> WeatherDataPoint:
    is_day = period.get("isDay")
    return build_hourly_point(
        first_present(period, "dateTimeISO", "timestamp"),
        temperature=as_float(period.get("tempC")),
        apparent_temperature=as_float(period.get("feelslikeC")),
        dew_point=as_float(period.get("dewpointC")),
        humidity=as_float(period.get("humidity")),
        wind_speed=safe_convert(as_float(period.get("windSpeedKPH")), ms_from_kmh),
        wind_gust=safe_convert(as_float(period.get("windGustKPH")), ms_from_kmh),
        wind_direction=as_float(period.get("windDirDEG")),
        pressure_sea=as_float(period.get("pressureMB")),
        precipitation=as_float(period.get("precipMM")),
        precipitation_probability=probability_from_percent_value(period.get("pop")),
        snowfall_depth=safe_convert(as_float(period.get("snowCM")), mm_from_cm),
        cloud_cover=as_float(period.get("sky")),
        visibility=as_float(period.get("visibilityKM")),
        uv_index=as_float(period.get("uvi")),
        solar_radiation_ghi=as_float(period.get("solradWM2")),
        condition=_condition(period),
        condition_original=_condition_text(period),
        condition_code_original=_condition_code(period),
        is_day=is_day if isinstance(is_day, bool) else None,
    )


def _parse_day(period: dict[str, Any]) -> DailyDataPoint:
    # The offset-aware period start already carries the local calendar date.
    local_date = datetime.fromisoformat(str(period["dateTimeISO"])).date()
    return build_daily_point(
        local_date,
        temperature_max=as_float(period.get("maxTempC")),
        temperature_min=as_float(period.get("minTempC")),
        apparent_temperature_max=as_float(period.get("maxFeelslikeC")),
        apparent_temperature_min=as_float(period.get("minFeelslikeC")),
        wind_speed_max=safe_convert(
            as_float(period.get("windSpeedMaxKPH")),
            ms_from_kmh,
        ),
        wind_gust_max=safe_convert(as_float(period.get("windGustKPH")), ms_from_kmh),
        wind_direction_dominant=as_float(period.get("windDirDEG")),
        precipitation_sum=as_float(period.get("precipMM")),
        precipitation_probability_max=probability_from_percent_value(
            period.get("pop"),
        ),
        snowfall_depth_sum=safe_convert(as_float(period.get("snowCM")), mm_from_cm),
        cloud_cover_mean=as_float(period.get("sky")),
        uv_index_max=as_float(period.get("uvi")),
        humidity_mean=optional_mean(
            as_float(period.get("maxHumidity")),
            as_float(period.get("minHumidity")),
        ),
        condition=_condition(period),
        summary=_condition_text(period),
        sunrise=period.get("sunriseISO"),
        sunset=period.get("sunsetISO"),
    )


class XweatherInstance(BasePluginInstance[XweatherConfig]):
    """Configured Xweather provider."""

    def __init__(self, config: XweatherConfig) -> None:
        super().__init__(
            ProviderId.XWEATHER,
            config,
            PluginCapabilities(
                granularity_minutely=False,
                granularity_hourly=True,
                granularity_daily=True,
                max_horizon_hourly_hours=float(config.hourly_limit),
                max_horizon_daily_days=float(config.daily_limit),
                requires_api_key=True,
                multi_model=False,
                coverage="global",
                alerts=False,
            ),
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        hourly: list[WeatherDataPoint] = []
        daily: list[DailyDataPoint] = []
        raw: dict[str, Any] = {}
        source_timezone: str | None = None

        try:
            if Granularity.HOURLY in params.granularity:
                response = await self._fetch_forecast_periods(
                    client,
                    params,
                    interval="1hr",
                    limit=self.config.hourly_limit,
                )
                if isinstance(response, PluginFetchError):
                    return response
                hourly = [_parse_hour(period) for period in _periods(response)]
                source_timezone = source_timezone or _profile_timezone(response)
                if params.include_raw:
                    raw["hourly"] = response

            if Granularity.DAILY in params.granularity:
                response = await self._fetch_forecast_periods(
                    client,
                    params,
                    interval="day",
                    limit=self.config.daily_limit,
                )
                if isinstance(response, PluginFetchError):
                    return response
                daily = [_parse_day(period) for period in _periods(response)]
                source_timezone = source_timezone or _profile_timezone(response)
                if params.include_raw:
                    raw["daily"] = response
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse Xweather payload: {exc}",
            )

        if zoneinfo_from_name(source_timezone) is None:
            source_timezone = params.timezone

        forecasts = [
            build_source_forecast(
                ProviderId.XWEATHER,
                timezone=source_timezone,
                hourly=hourly,
                daily=daily,
            ),
        ]
        return self._success(forecasts, raw=raw if params.include_raw else None)

    async def _fetch_forecast_periods(
        self,
        client: httpx2.AsyncClient,
        params: PluginFetchParams,
        *,
        interval: str,
        limit: int,
    ) -> list[Any] | PluginFetchError:
        payload = await self._get_json_dict(
            client,
            f"{XWEATHER_BASE_URL}/forecasts/{params.latitude},{params.longitude}",
            params={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "filter": interval,
                "limit": limit,
            },
            payload_name=f"Xweather {interval} forecast",
        )
        if isinstance(payload, PluginFetchError):
            return payload
        return self._unwrap_envelope(payload)

    def _unwrap_envelope(
        self,
        payload: dict[str, Any],
    ) -> list[Any] | PluginFetchError:
        """Unwrap the Xweather success/error/response envelope.

        Xweather reports auth and quota failures with HTTP 200 and
        ``success: false``, so envelope error codes carry the real status.
        """

        response = payload.get("response")
        if payload.get("success") is True:
            return response if isinstance(response, list) else [response]

        error = payload.get("error")
        error = error if isinstance(error, dict) else {}
        error_code = error.get("code")
        error_code = error_code if isinstance(error_code, str) else ""
        if error_code == "warn_no_data":
            return []
        description = error.get("description")
        return self._error(
            _XWEATHER_ERROR_CODES.get(error_code, ErrorCode.UNKNOWN),
            (
                description
                if isinstance(description, str) and description
                else f"Xweather request failed ({error_code or 'unknown error'})"
            ),
            raw=payload,
        )


class XweatherPlugin(BasePlugin[XweatherConfig]):
    """Xweather plugin facade."""

    config_model = XweatherConfig
    instance_cls = XweatherInstance
    _id = ProviderId.XWEATHER
    _name = "Xweather"


xweather_plugin = XweatherPlugin()

__all__ = ["XweatherConfig", "XweatherInstance", "xweather_plugin"]
