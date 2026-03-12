from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any, Generic, TypeVar

import httpx
from pydantic import BaseModel

from omni_weather_forecast_apis.mapping import (
    condition_from_text,
    probability_from_percent,
)
from omni_weather_forecast_apis.types import (
    AlertSeverity,
    DailyDataPoint,
    ErrorCode,
    MinutelyDataPoint,
    ModelSource,
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
    PluginInstance,
    ProviderId,
    SourceForecast,
    WeatherAlert,
    WeatherCondition,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.utils import parse_date, parse_datetime, unix_timestamp

ConfigT = TypeVar("ConfigT", bound=BaseModel)


def as_float(value: Any) -> float | None:
    """Convert a provider value into a float when possible."""

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def first_present(mapping: Mapping[str, Any], *keys: str) -> Any | None:
    """Return the first present non-null mapping value."""

    for key in keys:
        if (value := mapping.get(key)) is not None:
            return value
    return None


def normalize_probability(value: Any) -> float | None:
    """Normalize probabilities into the 0..1 range."""

    numeric = as_float(value)
    if numeric is None:
        return None
    if numeric > 1:
        return max(0.0, min(1.0, probability_from_percent(numeric)))
    return max(0.0, min(1.0, numeric))


def normalize_percent(value: Any) -> float | None:
    """Normalize percent-like values into the 0..100 range."""

    numeric = as_float(value)
    if numeric is None:
        return None
    if 0 <= numeric <= 1:
        return numeric * 100
    return max(0.0, min(100.0, numeric))


def normalize_severity(value: str | None) -> AlertSeverity | None:
    """Normalize alert severity text."""

    if value is None:
        return None
    normalized = value.strip().lower()
    mapping = {
        "extreme": AlertSeverity.EXTREME,
        "severe": AlertSeverity.SEVERE,
        "moderate": AlertSeverity.MODERATE,
        "minor": AlertSeverity.MINOR,
    }
    return mapping.get(normalized, AlertSeverity.UNKNOWN)


def _coerce_datetime_input(value: object) -> str | int | float | datetime | None:
    if isinstance(value, (str, int, float, datetime)):
        return value
    return None


def _coerce_date_input(value: object) -> str | date | datetime | None:
    if isinstance(value, (str, date, datetime)):
        return value
    return None


def build_hourly_point(
    timestamp_value: object,
    *,
    temperature: float | None = None,
    apparent_temperature: float | None = None,
    dew_point: float | None = None,
    humidity: float | None = None,
    wind_speed: float | None = None,
    wind_gust: float | None = None,
    wind_direction: float | None = None,
    pressure_sea: float | None = None,
    pressure_surface: float | None = None,
    precipitation: float | None = None,
    precipitation_probability: float | None = None,
    rain: float | None = None,
    snow: float | None = None,
    snow_depth: float | None = None,
    cloud_cover: float | None = None,
    cloud_cover_low: float | None = None,
    cloud_cover_mid: float | None = None,
    cloud_cover_high: float | None = None,
    visibility: float | None = None,
    uv_index: float | None = None,
    solar_radiation_ghi: float | None = None,
    solar_radiation_dni: float | None = None,
    solar_radiation_dhi: float | None = None,
    condition: WeatherCondition | None = None,
    condition_original: str | None = None,
    condition_code_original: str | int | None = None,
    is_day: bool | None = None,
) -> WeatherDataPoint:
    """Build one normalized hourly row."""

    timestamp = parse_datetime(_coerce_datetime_input(timestamp_value))
    if timestamp is None:
        raise ValueError("timestamp_value must be parseable")
    return WeatherDataPoint(
        timestamp=timestamp,
        timestamp_unix=unix_timestamp(timestamp),
        temperature=temperature,
        apparent_temperature=apparent_temperature,
        dew_point=dew_point,
        humidity=humidity,
        wind_speed=wind_speed,
        wind_gust=wind_gust,
        wind_direction=wind_direction,
        pressure_sea=pressure_sea,
        pressure_surface=pressure_surface,
        precipitation=precipitation,
        precipitation_probability=precipitation_probability,
        rain=rain,
        snow=snow,
        snow_depth=snow_depth,
        cloud_cover=cloud_cover,
        cloud_cover_low=cloud_cover_low,
        cloud_cover_mid=cloud_cover_mid,
        cloud_cover_high=cloud_cover_high,
        visibility=visibility,
        uv_index=uv_index,
        solar_radiation_ghi=solar_radiation_ghi,
        solar_radiation_dni=solar_radiation_dni,
        solar_radiation_dhi=solar_radiation_dhi,
        condition=condition,
        condition_original=condition_original,
        condition_code_original=condition_code_original,
        is_day=is_day,
    )


def build_minutely_point(
    timestamp_value: object,
    *,
    precipitation_intensity: float | None = None,
    precipitation_probability: float | None = None,
) -> MinutelyDataPoint:
    """Build one normalized minutely row."""

    timestamp = parse_datetime(_coerce_datetime_input(timestamp_value))
    if timestamp is None:
        raise ValueError("timestamp_value must be parseable")
    return MinutelyDataPoint(
        timestamp=timestamp,
        timestamp_unix=unix_timestamp(timestamp),
        precipitation_intensity=precipitation_intensity,
        precipitation_probability=precipitation_probability,
    )


def build_daily_point(
    date_value: object,
    *,
    temperature_max: float | None = None,
    temperature_min: float | None = None,
    apparent_temperature_max: float | None = None,
    apparent_temperature_min: float | None = None,
    wind_speed_max: float | None = None,
    wind_gust_max: float | None = None,
    wind_direction_dominant: float | None = None,
    precipitation_sum: float | None = None,
    precipitation_probability_max: float | None = None,
    rain_sum: float | None = None,
    snowfall_sum: float | None = None,
    cloud_cover_mean: float | None = None,
    uv_index_max: float | None = None,
    visibility_min: float | None = None,
    humidity_mean: float | None = None,
    pressure_sea_mean: float | None = None,
    condition: WeatherCondition | None = None,
    summary: str | None = None,
    sunrise: str | float | None = None,
    sunset: str | float | None = None,
    moonrise: str | float | None = None,
    moonset: str | float | None = None,
    moon_phase: float | None = None,
    daylight_duration: float | None = None,
    solar_radiation_sum: float | None = None,
) -> DailyDataPoint:
    """Build one normalized daily row."""

    if isinstance(date_value, (int, float)):
        parsed_timestamp = parse_datetime(_coerce_datetime_input(date_value))
        if parsed_timestamp is None:
            raise ValueError("date_value must be parseable")
        parsed_date = parsed_timestamp.date()
    else:
        parsed_date = parse_date(_coerce_date_input(date_value))
        if parsed_date is None:
            raise ValueError("date_value must be parseable")
    return DailyDataPoint(
        date=parsed_date,
        temperature_max=temperature_max,
        temperature_min=temperature_min,
        apparent_temperature_max=apparent_temperature_max,
        apparent_temperature_min=apparent_temperature_min,
        wind_speed_max=wind_speed_max,
        wind_gust_max=wind_gust_max,
        wind_direction_dominant=wind_direction_dominant,
        precipitation_sum=precipitation_sum,
        precipitation_probability_max=precipitation_probability_max,
        rain_sum=rain_sum,
        snowfall_sum=snowfall_sum,
        cloud_cover_mean=cloud_cover_mean,
        uv_index_max=uv_index_max,
        visibility_min=visibility_min,
        humidity_mean=humidity_mean,
        pressure_sea_mean=pressure_sea_mean,
        condition=condition,
        summary=summary,
        sunrise=parse_datetime(sunrise),
        sunset=parse_datetime(sunset),
        moonrise=parse_datetime(moonrise),
        moonset=parse_datetime(moonset),
        moon_phase=moon_phase,
        daylight_duration=daylight_duration,
        solar_radiation_sum=solar_radiation_sum,
    )


def build_alert(
    *,
    sender_name: str,
    event: str,
    start: str | float,
    end: str | float | None,
    description: str,
    severity: str | None = None,
    url: str | None = None,
) -> WeatherAlert:
    """Build one normalized weather alert."""

    start_value = parse_datetime(start)
    if start_value is None:
        raise ValueError("start must be parseable")
    return WeatherAlert(
        sender_name=sender_name,
        event=event,
        start=start_value,
        end=parse_datetime(end),
        description=description,
        severity=normalize_severity(severity),
        url=url,
    )


def provider_source(
    provider: ProviderId,
    *,
    model: str | None = None,
) -> ModelSource:
    """Create a provider/model source tuple."""

    return ModelSource(provider=provider, model=model or provider.value)


def build_source_forecast(
    provider: ProviderId,
    *,
    model: str | None = None,
    minutely: list[MinutelyDataPoint] | None = None,
    hourly: list[WeatherDataPoint] | None = None,
    daily: list[DailyDataPoint] | None = None,
    alerts: list[WeatherAlert] | None = None,
) -> SourceForecast:
    """Create a normalized source forecast block."""

    return SourceForecast(
        source=provider_source(provider, model=model),
        minutely=minutely or [],
        hourly=hourly or [],
        daily=daily or [],
        alerts=alerts or [],
    )


class BasePlugin(ABC, Generic[ConfigT]):
    """Reusable plugin facade with config validation."""

    config_model: type[ConfigT]
    instance_cls: Callable[[ConfigT], PluginInstance]
    _id: ProviderId
    _name: str

    @property
    def id(self) -> ProviderId:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    def validate_config(self, config: dict[str, Any]) -> ConfigT:
        return self.config_model.model_validate(config)

    async def initialize(self, config: ConfigT) -> PluginInstance:
        return self.instance_cls(config)


class BasePluginInstance(ABC, Generic[ConfigT]):
    """Shared HTTP and error handling for provider instances."""

    provider_id: ProviderId
    config: ConfigT
    capabilities: PluginCapabilities

    def __init__(
        self,
        provider_id: ProviderId,
        config: ConfigT,
        capabilities: PluginCapabilities,
    ) -> None:
        self.provider_id = provider_id
        self.config = config
        self.capabilities = capabilities

    def get_capabilities(self) -> PluginCapabilities:
        return self.capabilities

    @abstractmethod
    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        """Fetch and normalize provider data."""

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[dict[str, Any] | list[Any] | None, PluginFetchError | None]:
        try:
            response = await client.get(url, params=params, headers=headers)
        except (httpx.ConnectError, httpx.NetworkError, httpx.ProtocolError) as exc:
            return None, self._error(ErrorCode.NETWORK, str(exc))
        except httpx.HTTPError as exc:
            return None, self._error(ErrorCode.UNKNOWN, str(exc))

        if response.status_code >= 400:
            error_code = self._http_error_code(response.status_code)
            try:
                raw = response.json()
            except ValueError:
                raw = response.text
            message = (
                raw.get("message")
                if isinstance(raw, dict) and isinstance(raw.get("message"), str)
                else response.reason_phrase
            )
            return None, self._error(
                error_code,
                message or "HTTP request failed",
                http_status=response.status_code,
                raw=raw,
            )

        try:
            return response.json(), None
        except ValueError as exc:
            return None, self._error(
                ErrorCode.PARSE,
                f"Could not decode JSON: {exc}",
                http_status=response.status_code,
                raw=response.text,
            )

    def _success(
        self,
        forecasts: list[SourceForecast],
        *,
        raw: Any | None = None,
    ) -> PluginFetchSuccess:
        return PluginFetchSuccess(forecasts=forecasts, raw=raw)

    def _error(
        self,
        code: ErrorCode,
        message: str,
        *,
        http_status: int | None = None,
        raw: Any | None = None,
    ) -> PluginFetchError:
        return PluginFetchError(
            code=code,
            message=message,
            http_status=http_status,
            raw=raw,
        )

    @staticmethod
    def _http_error_code(status_code: int) -> ErrorCode:
        if status_code in {401, 403}:
            return ErrorCode.AUTH_FAILED
        if status_code == 404:
            return ErrorCode.NOT_AVAILABLE
        if status_code == 429:
            return ErrorCode.RATE_LIMITED
        if status_code >= 500:
            return ErrorCode.NETWORK
        return ErrorCode.UNKNOWN


def fallback_condition(
    code_condition: WeatherCondition | None,
    text: str | None,
) -> WeatherCondition | None:
    """Prefer explicit code mappings and fall back to provider text."""

    return code_condition or condition_from_text(text)


def cardinal_direction_to_degrees(value: str | None) -> float | None:
    """Convert cardinal wind directions into degrees."""

    if value is None:
        return None
    normalized = value.strip().upper()
    mapping = {
        "N": 0.0,
        "NNE": 22.5,
        "NE": 45.0,
        "ENE": 67.5,
        "E": 90.0,
        "ESE": 112.5,
        "SE": 135.0,
        "SSE": 157.5,
        "S": 180.0,
        "SSW": 202.5,
        "SW": 225.0,
        "WSW": 247.5,
        "W": 270.0,
        "WNW": 292.5,
        "NW": 315.0,
        "NNW": 337.5,
    }
    return mapping.get(normalized)
