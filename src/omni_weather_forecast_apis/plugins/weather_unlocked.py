"""Weather Unlocked provider adapter."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Final

import httpx
from pydantic import Field

from omni_weather_forecast_apis.mapping import ms_from_kmh
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_daily_point,
    build_hourly_point,
    build_source_forecast,
    fallback_condition,
    first_present,
    normalize_probability,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
)
from omni_weather_forecast_apis.types.plugin import ProviderConfigModel


class WeatherUnlockedConfig(ProviderConfigModel):
    app_id: str = Field(min_length=1)
    app_key: str = Field(min_length=1)
    lang: str | None = None


WEATHER_UNLOCKED_BASE_URL: Final = "https://api.weatherunlocked.com/api/forecast"


def _normalize_date(date_value: Any) -> str:
    if not isinstance(date_value, str):
        raise ValueError("Weather Unlocked day date must be a string")
    normalized = date_value.strip()
    try:
        if "T" in normalized or " " in normalized:
            return (
                datetime.fromisoformat(
                    normalized.replace("Z", "+00:00").replace(" ", "T", 1),
                )
                .date()
                .isoformat()
            )
        return date.fromisoformat(normalized).isoformat()
    except ValueError:
        try:
            day_text, month_text, year_text = normalized.split("/")
            return date(
                year=int(year_text),
                month=int(month_text),
                day=int(day_text),
            ).isoformat()
        except ValueError as exc:
            raise ValueError(
                "Weather Unlocked day date must be ISO or DD/MM/YYYY",
            ) from exc
        except (TypeError, AttributeError) as exc:
            raise ValueError(
                "Weather Unlocked day date must be ISO or DD/MM/YYYY",
            ) from exc


def _time_components(time_value: Any) -> tuple[int, int] | None:
    if time_value in (None, ""):
        return None
    if isinstance(time_value, str) and ":" in time_value:
        hour_text, minute_text, *_unused_rest = time_value.strip().split(":")
        try:
            hour = int(hour_text)
            minute = int(minute_text)
        except ValueError as exc:
            raise ValueError(
                "Weather Unlocked time must contain numeric HH:MM",
            ) from exc
    else:
        numeric = as_float(time_value)
        if numeric is None:
            raise ValueError("Weather Unlocked time must be parseable")
        clock = int(numeric)
        hour = clock // 100
        minute = clock % 100
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Weather Unlocked time must be within 00:00-23:59")
    return hour, minute


def _rounded_coordinate(value: float) -> str:
    return f"{value:.4f}"


def _normalize_datetime(date_value: Any, time_value: Any) -> str:
    normalized_date = _normalize_date(date_value)
    if (components := _time_components(time_value)) is None:
        raise ValueError("Weather Unlocked time must be present")
    hour, minute = components
    return f"{normalized_date}T{hour:02d}:{minute:02d}:00"


def _combine_clock(date_value: Any, clock_value: Any) -> str | None:
    if clock_value in (None, ""):
        return None
    try:
        normalized_date = _normalize_date(date_value)
        components = _time_components(clock_value)
    except ValueError:
        return None
    if components is None:
        return None
    hour, minute = components
    return f"{normalized_date}T{hour:02d}:{minute:02d}:00"


def _wind_speed(
    row: dict[str, Any],
    *,
    metric_keys: tuple[str, ...],
    kmh_keys: tuple[str, ...],
) -> float | None:
    direct = as_float(first_present(row, *metric_keys))
    if direct is not None:
        return direct
    kmh = as_float(first_present(row, *kmh_keys))
    if kmh is not None:
        return ms_from_kmh(kmh)
    return None


def _normalized_day_date(day: dict[str, Any]) -> str | None:
    date_value = first_present(day, "date", "date_local")
    if not isinstance(date_value, str):
        return None
    try:
        return _normalize_date(date_value)
    except ValueError:
        return None


class WeatherUnlockedInstance(BasePluginInstance[WeatherUnlockedConfig]):
    """Configured Weather Unlocked provider."""

    def __init__(self, config: WeatherUnlockedConfig) -> None:
        super().__init__(
            provider_id=ProviderId.WEATHER_UNLOCKED,
            config=config,
            capabilities=PluginCapabilities(
                granularity_minutely=False,
                granularity_hourly=True,
                granularity_daily=True,
                max_horizon_hourly_hours=None,
                max_horizon_daily_days=None,
                requires_api_key=True,
                multi_model=False,
                coverage="global",
            ),
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        payload, error = await self._get_json(
            client,
            (
                f"{WEATHER_UNLOCKED_BASE_URL}/"
                f"{_rounded_coordinate(params.latitude)},"
                f"{_rounded_coordinate(params.longitude)}"
            ),
            params={
                "app_id": self.config.app_id,
                "app_key": self.config.app_key,
                **({"lang": self.config.lang} if self.config.lang is not None else {}),
            },
        )
        if error is not None:
            return error
        if payload is None or not isinstance(payload, dict):
            return self._error(
                ErrorCode.PARSE,
                "Weather Unlocked returned an invalid payload",
            )

        try:
            forecasts = [
                build_source_forecast(
                    ProviderId.WEATHER_UNLOCKED,
                    hourly=self._parse_hourly(payload),
                    daily=self._parse_daily(payload),
                ),
            ]
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse Weather Unlocked payload: {exc}",
            )
        return self._success(forecasts, raw=payload if params.include_raw else None)

    def _days(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_days = payload.get("Days") or payload.get("days")
        if not isinstance(raw_days, list):
            return []
        return [day for day in raw_days if isinstance(day, dict)]

    def _parse_hourly(self, payload: dict[str, Any]) -> list[Any]:
        points: list[Any] = []
        for day in self._days(payload):
            if (normalized_date := _normalized_day_date(day)) is None:
                continue
            timeframes = day.get("Timeframes") or day.get("timeframes")
            if not isinstance(timeframes, list):
                continue
            for timeframe in timeframes:
                if not isinstance(timeframe, dict):
                    continue
                try:
                    timestamp = _normalize_datetime(
                        normalized_date,
                        first_present(timeframe, "time", "time_hm"),
                    )
                except ValueError:
                    continue
                condition_text = first_present(
                    timeframe,
                    "wx_desc",
                    "phrase",
                    "weather_desc",
                )
                points.append(
                    build_hourly_point(
                        timestamp,
                        temperature=as_float(
                            first_present(timeframe, "temp_c", "tempC", "temp"),
                        ),
                        apparent_temperature=as_float(
                            first_present(
                                timeframe,
                                "feelslike_c",
                                "feelslike",
                                "feels_like_c",
                            ),
                        ),
                        humidity=as_float(
                            first_present(timeframe, "humid_pct", "humidity"),
                        ),
                        wind_speed=_wind_speed(
                            timeframe,
                            metric_keys=("windspd_ms", "wind_speed"),
                            kmh_keys=("windspd_kmh", "wind_speed_kmh"),
                        ),
                        wind_direction=as_float(
                            first_present(timeframe, "winddir_deg", "wind_direction"),
                        ),
                        pressure_sea=as_float(
                            first_present(timeframe, "slp_mb", "pressure_hpa"),
                        ),
                        precipitation=as_float(
                            first_present(timeframe, "precip_mm", "rain_mm"),
                        ),
                        precipitation_probability=normalize_probability(
                            first_present(
                                timeframe,
                                "prob_precip_pct",
                                "precip_probability",
                            ),
                        ),
                        cloud_cover=as_float(
                            first_present(timeframe, "cloudtotal_pct", "cloud_pct"),
                        ),
                        visibility=as_float(
                            first_present(timeframe, "vis_km", "visibility_km"),
                        ),
                        uv_index=as_float(
                            first_present(timeframe, "uvindex", "uv_index"),
                        ),
                        condition=fallback_condition(
                            None,
                            condition_text if isinstance(condition_text, str) else None,
                        ),
                        condition_original=(
                            condition_text if isinstance(condition_text, str) else None
                        ),
                        condition_code_original=first_present(
                            timeframe,
                            "wx_code",
                            "icon",
                        ),
                    ),
                )
        return points

    def _parse_daily(self, payload: dict[str, Any]) -> list[Any]:
        points: list[Any] = []
        for day in self._days(payload):
            if (normalized_date := _normalized_day_date(day)) is None:
                continue
            condition_text = first_present(day, "wx_desc", "phrase", "weather_desc")
            points.append(
                build_daily_point(
                    normalized_date,
                    temperature_max=as_float(
                        first_present(day, "temp_max_c", "maxtemp_c", "tempMaxC"),
                    ),
                    temperature_min=as_float(
                        first_present(day, "temp_min_c", "mintemp_c", "tempMinC"),
                    ),
                    wind_speed_max=_wind_speed(
                        day,
                        metric_keys=("windspd_max_ms", "wind_speed_max"),
                        kmh_keys=("windspdmax_kmh", "wind_speed_max_kmh"),
                    ),
                    wind_direction_dominant=as_float(
                        first_present(day, "winddir_deg", "wind_direction"),
                    ),
                    precipitation_sum=as_float(
                        first_present(day, "total_precip_mm", "precip_total_mm"),
                    ),
                    precipitation_probability_max=normalize_probability(
                        first_present(day, "prob_precip_pct", "precip_probability"),
                    ),
                    cloud_cover_mean=as_float(
                        first_present(day, "cloudtotal_pct", "cloud_pct"),
                    ),
                    uv_index_max=as_float(first_present(day, "uvindex", "uv_index")),
                    humidity_mean=as_float(first_present(day, "humid_pct", "humidity")),
                    pressure_sea_mean=as_float(
                        first_present(day, "slp_mb", "pressure_hpa"),
                    ),
                    condition=fallback_condition(
                        None,
                        condition_text if isinstance(condition_text, str) else None,
                    ),
                    summary=condition_text if isinstance(condition_text, str) else None,
                    sunrise=_combine_clock(
                        normalized_date,
                        first_present(day, "sunrise_time", "sunrise"),
                    ),
                    sunset=_combine_clock(
                        normalized_date,
                        first_present(day, "sunset_time", "sunset"),
                    ),
                ),
            )
        return points


class WeatherUnlockedPlugin(BasePlugin[WeatherUnlockedConfig]):
    """Weather Unlocked plugin facade."""

    config_model = WeatherUnlockedConfig
    instance_cls = WeatherUnlockedInstance
    _id = ProviderId.WEATHER_UNLOCKED
    _name = "Weather Unlocked"


weather_unlocked_plugin = WeatherUnlockedPlugin()
