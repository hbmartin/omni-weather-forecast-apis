from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import date as calendar_date
from enum import Enum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

import omni_weather_forecast_apis._compat  # noqa: F401  # Pydantic Python 3.14 compat


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)


UTCDateTime = Annotated[datetime, AfterValidator(_normalize_utc_datetime)]


class ProviderId(str, Enum):
    """Every supported provider has a stable slug."""

    OPENWEATHER = "openweather"
    OPEN_METEO = "open_meteo"
    NWS = "nws"
    WEATHERAPI = "weatherapi"
    TOMORROW_IO = "tomorrow_io"
    VISUAL_CROSSING = "visual_crossing"
    WEATHERBIT = "weatherbit"
    METEOSOURCE = "meteosource"
    PIRATE_WEATHER = "pirate_weather"
    MET_NORWAY = "met_norway"
    GOOGLE_WEATHER = "google_weather"
    STORMGLASS = "stormglass"
    WEATHER_UNLOCKED = "weather_unlocked"


class ModelSource(BaseModel):
    """Model source attribution for one forecast payload."""

    model_config = ConfigDict(frozen=True)

    provider: ProviderId
    model: str


class WeatherCondition(str, Enum):
    """Closed normalized condition vocabulary."""

    CLEAR = "clear"
    MOSTLY_CLEAR = "mostly_clear"
    PARTLY_CLOUDY = "partly_cloudy"
    MOSTLY_CLOUDY = "mostly_cloudy"
    OVERCAST = "overcast"
    FOG = "fog"
    DRIZZLE = "drizzle"
    LIGHT_RAIN = "light_rain"
    RAIN = "rain"
    HEAVY_RAIN = "heavy_rain"
    FREEZING_RAIN = "freezing_rain"
    LIGHT_SNOW = "light_snow"
    SNOW = "snow"
    HEAVY_SNOW = "heavy_snow"
    SLEET = "sleet"
    HAIL = "hail"
    THUNDERSTORM = "thunderstorm"
    THUNDERSTORM_RAIN = "thunderstorm_rain"
    THUNDERSTORM_HEAVY = "thunderstorm_heavy"
    DUST = "dust"
    SAND = "sand"
    SMOKE = "smoke"
    HAZE = "haze"
    TORNADO = "tornado"
    HURRICANE = "hurricane"
    UNKNOWN = "unknown"


class Granularity(str, Enum):
    MINUTELY = "minutely"
    HOURLY = "hourly"
    DAILY = "daily"


class WeatherDataPoint(BaseModel):
    """A normalized point-in-time forecast row."""

    model_config = ConfigDict(frozen=True)

    timestamp: UTCDateTime = Field(description="UTC timestamp")
    timestamp_unix: int = Field(description="Unix timestamp (seconds)")
    temperature: float | None = Field(None, description="Air temperature at 2m, °C")
    apparent_temperature: float | None = Field(
        None,
        description="Feels-like temperature, °C",
    )
    dew_point: float | None = Field(None, description="Dew point, °C")
    humidity: float | None = Field(None, description="Relative humidity, % (0–100)")
    wind_speed: float | None = Field(None, description="Wind speed at 10m, m/s")
    wind_gust: float | None = Field(None, description="Wind gust speed, m/s")
    wind_direction: float | None = Field(
        None,
        description="Wind direction, degrees (meteorological)",
    )
    pressure_sea: float | None = Field(None, description="Sea-level pressure, hPa")
    pressure_surface: float | None = Field(None, description="Surface pressure, hPa")
    precipitation: float | None = Field(
        None,
        description="Precipitation (liquid equivalent), mm",
    )
    precipitation_probability: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Precipitation probability, 0–1",
    )
    rain: float | None = Field(None, description="Rain amount, mm")
    snow: float | None = Field(None, description="Snowfall (liquid equivalent), mm")
    snow_depth: float | None = Field(None, description="Snow depth on ground, mm")
    cloud_cover: float | None = Field(None, description="Total cloud cover, % (0–100)")
    cloud_cover_low: float | None = Field(None, description="Low cloud cover, %")
    cloud_cover_mid: float | None = Field(None, description="Mid cloud cover, %")
    cloud_cover_high: float | None = Field(None, description="High cloud cover, %")
    visibility: float | None = Field(None, description="Visibility, km")
    uv_index: float | None = Field(None, description="UV index (0–11+)")
    solar_radiation_ghi: float | None = Field(
        None,
        description="Global horizontal irradiance, W/m²",
    )
    solar_radiation_dni: float | None = Field(
        None,
        description="Direct normal irradiance, W/m²",
    )
    solar_radiation_dhi: float | None = Field(
        None,
        description="Diffuse horizontal irradiance, W/m²",
    )
    condition: WeatherCondition | None = Field(
        None,
        description="Normalized weather condition",
    )
    condition_original: str | None = Field(
        None,
        description="Original provider condition text",
    )
    condition_code_original: str | int | None = Field(
        None,
        description="Original provider condition or icon code",
    )
    is_day: bool | None = Field(
        None,
        description="Whether this timestamp is in daylight",
    )


class MinutelyDataPoint(BaseModel):
    """Normalized minutely precipitation point."""

    model_config = ConfigDict(frozen=True)

    timestamp: UTCDateTime = Field(description="UTC timestamp")
    timestamp_unix: int = Field(description="Unix timestamp (seconds)")
    precipitation_intensity: float | None = Field(
        None,
        description="Precipitation intensity, mm/h",
    )
    precipitation_probability: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Precipitation probability, 0–1",
    )


class DailyDataPoint(BaseModel):
    """Normalized daily summary row."""

    model_config = ConfigDict(frozen=True)

    date: calendar_date = Field(description="Forecast date")
    temperature_max: float | None = Field(None, description="Max temperature, °C")
    temperature_min: float | None = Field(None, description="Min temperature, °C")
    apparent_temperature_max: float | None = Field(
        None,
        description="Max apparent temperature, °C",
    )
    apparent_temperature_min: float | None = Field(
        None,
        description="Min apparent temperature, °C",
    )
    wind_speed_max: float | None = Field(None, description="Max wind speed, m/s")
    wind_gust_max: float | None = Field(None, description="Max wind gust, m/s")
    wind_direction_dominant: float | None = Field(
        None,
        description="Dominant wind direction, degrees",
    )
    precipitation_sum: float | None = Field(
        None,
        description="Total precipitation (liquid equivalent), mm",
    )
    precipitation_probability_max: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Max precipitation probability, 0–1",
    )
    rain_sum: float | None = Field(None, description="Total rain, mm")
    snowfall_sum: float | None = Field(None, description="Total snowfall, mm")
    cloud_cover_mean: float | None = Field(None, description="Mean cloud cover, %")
    uv_index_max: float | None = Field(None, description="Max UV index")
    visibility_min: float | None = Field(None, description="Min visibility, km")
    humidity_mean: float | None = Field(None, description="Mean humidity, %")
    pressure_sea_mean: float | None = Field(
        None,
        description="Mean sea-level pressure, hPa",
    )
    condition: WeatherCondition | None = Field(
        None,
        description="Most representative condition",
    )
    summary: str | None = Field(None, description="Provider summary text")
    sunrise: UTCDateTime | None = Field(None, description="Sunrise UTC timestamp")
    sunset: UTCDateTime | None = Field(None, description="Sunset UTC timestamp")
    moonrise: UTCDateTime | None = Field(None, description="Moonrise UTC timestamp")
    moonset: UTCDateTime | None = Field(None, description="Moonset UTC timestamp")
    moon_phase: float | None = Field(None, ge=0, le=1, description="Moon phase 0–1")
    daylight_duration: float | None = Field(
        None,
        description="Daylight duration in seconds",
    )
    solar_radiation_sum: float | None = Field(
        None,
        description="Shortwave radiation sum, MJ/m²",
    )


class AlertSeverity(str, Enum):
    EXTREME = "extreme"
    SEVERE = "severe"
    MODERATE = "moderate"
    MINOR = "minor"
    UNKNOWN = "unknown"


class WeatherAlert(BaseModel):
    """Normalized weather alert."""

    model_config = ConfigDict(frozen=True)

    sender_name: str
    event: str
    start: UTCDateTime
    end: UTCDateTime | None = None
    description: str
    severity: AlertSeverity | None = None
    url: str | None = None


class SourceForecast(BaseModel):
    """A complete normalized forecast for one model or provider source."""

    model_config = ConfigDict(frozen=True)

    source: ModelSource = Field(description="Provider/model identity")
    minutely: list[MinutelyDataPoint] = Field(default_factory=list)
    hourly: list[WeatherDataPoint] = Field(default_factory=list)
    daily: list[DailyDataPoint] = Field(default_factory=list)
    alerts: list[WeatherAlert] = Field(default_factory=list)


class ErrorCode(str, Enum):
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK = "network"
    PARSE = "parse"
    NOT_AVAILABLE = "not_available"
    UNKNOWN = "unknown"


class ProviderErrorDetail(BaseModel):
    """Structured provider error payload."""

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    http_status: int | None = Field(
        None,
        description="HTTP status code, when available",
    )
    latency_ms: float = Field(
        description="Elapsed time until the failure, milliseconds",
    )
    raw: Any | None = Field(None, description="Raw error payload when available")


class ProviderSuccess(BaseModel):
    """Successful provider response."""

    model_config = ConfigDict(frozen=True)

    status: Literal["success"] = "success"
    provider: ProviderId
    forecasts: list[SourceForecast]
    fetched_at: UTCDateTime
    latency_ms: float
    raw: Any | None = None


class ProviderError(BaseModel):
    """Failed provider response."""

    status: Literal["error"] = "error"
    provider: ProviderId
    error: ProviderErrorDetail


ProviderResult: TypeAlias = ProviderSuccess | ProviderError


class ForecastRequest(BaseModel):
    """Public forecast request."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    granularity: list[Granularity] = Field(
        default_factory=lambda: [Granularity.HOURLY, Granularity.DAILY],
    )
    language: str = Field(default="en", min_length=1)
    include_raw: bool = False
    timeout_ms: float | None = Field(default=None, gt=0)
    providers: list[ProviderId] | None = None


class ForecastResponseSummary(BaseModel):
    total: int
    succeeded: int
    failed: int


class ForecastResponseRequest(BaseModel):
    """Echo of the resolved request parameters."""

    latitude: float
    longitude: float
    granularity: list[Granularity]
    language: str


class ForecastResponse(BaseModel):
    """Public aggregated response."""

    model_config = ConfigDict(frozen=True)

    request: ForecastResponseRequest
    results: list[ProviderResult]
    summary: ForecastResponseSummary
    completed_at: UTCDateTime
    total_latency_ms: float


@dataclass(frozen=True)
class ProviderLogEvent:
    """Structured log event emitted by the client for each provider interaction."""

    provider: ProviderId
    phase: Literal["start", "success", "error"]
    message: str
    timestamp: datetime = field(default_factory=_utc_now)
    latency_ms: float = 0.0
    error_code: ErrorCode | None = None
    http_status: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


LogHook: TypeAlias = Callable[[ProviderLogEvent], None]
