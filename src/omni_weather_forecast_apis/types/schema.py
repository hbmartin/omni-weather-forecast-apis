"""Common schema types for weather forecast data."""

import datetime as _dt
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

import omni_weather_forecast_apis._compat  # noqa: F401  # Pydantic Python 3.14 compat

# ─── Identifiers & Metadata ──────────────────────────────────────────


class ProviderId(StrEnum):
    """Every provider has a unique slug."""

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
    """Model source attribution."""

    model_config = ConfigDict(frozen=True)

    provider: ProviderId
    model: str


# ─── Weather Condition Codes ──────────────────────────────────────────


class WeatherCondition(StrEnum):
    """Normalized weather condition."""

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


class Granularity(StrEnum):
    MINUTELY = "minutely"
    HOURLY = "hourly"
    DAILY = "daily"


# ─── Data Points ──────────────────────────────────────────────────────


class WeatherDataPoint(BaseModel):
    """A single point-in-time weather observation/forecast."""

    model_config = ConfigDict(frozen=True)

    # Time
    timestamp: _dt.datetime = Field(description="UTC timestamp")
    timestamp_unix: int = Field(description="Unix timestamp (seconds)")

    # Temperature
    temperature: float | None = Field(None, description="Air temperature at 2m, °C")
    apparent_temperature: float | None = Field(
        None,
        description="Feels-like temperature, °C",
    )
    dew_point: float | None = Field(None, description="Dew point, °C")

    # Moisture
    humidity: float | None = Field(None, description="Relative humidity, % (0–100)")

    # Wind
    wind_speed: float | None = Field(None, description="Wind speed at 10m, m/s")
    wind_gust: float | None = Field(None, description="Wind gust speed, m/s")
    wind_direction: float | None = Field(
        None,
        description="Wind direction, degrees (meteorological)",
    )

    # Pressure
    pressure_sea: float | None = Field(None, description="Sea-level pressure, hPa")
    pressure_surface: float | None = Field(None, description="Surface pressure, hPa")

    # Precipitation
    precipitation: float | None = Field(
        None,
        description="Precipitation (liquid equiv.), mm",
    )
    precipitation_probability: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Precipitation probability, 0–1",
    )
    rain: float | None = Field(None, description="Rain amount, mm")
    snow: float | None = Field(None, description="Snowfall (liquid equiv.), mm")
    snow_depth: float | None = Field(None, description="Snow depth on ground, mm")

    # Sky
    cloud_cover: float | None = Field(None, description="Total cloud cover, % (0–100)")
    cloud_cover_low: float | None = Field(None, description="Low cloud cover, %")
    cloud_cover_mid: float | None = Field(None, description="Mid cloud cover, %")
    cloud_cover_high: float | None = Field(None, description="High cloud cover, %")
    visibility: float | None = Field(None, description="Visibility, km")

    # Radiation & UV
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

    # Condition
    condition: WeatherCondition | None = Field(
        None,
        description="Normalized weather condition",
    )
    condition_original: str | None = Field(
        None,
        description="Original condition text from provider",
    )
    condition_code_original: str | int | None = Field(
        None,
        description="Original condition/icon code from provider",
    )

    # Day/Night
    is_day: bool | None = Field(
        None,
        description="Whether this timestamp is during daylight hours",
    )


class MinutelyDataPoint(BaseModel):
    """Minutely data point — precipitation nowcast only."""

    model_config = ConfigDict(frozen=True)

    timestamp: _dt.datetime = Field(description="UTC timestamp")
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
    """Daily forecast summary."""

    model_config = ConfigDict(frozen=True)

    date: _dt.date = Field(description="Forecast date (YYYY-MM-DD)")

    # Temperature envelope
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

    # Wind
    wind_speed_max: float | None = Field(None, description="Max wind speed, m/s")
    wind_gust_max: float | None = Field(None, description="Max wind gust, m/s")
    wind_direction_dominant: float | None = Field(
        None,
        description="Dominant wind direction, degrees",
    )

    # Precipitation
    precipitation_sum: float | None = Field(
        None,
        description="Total precipitation (liquid equiv.), mm",
    )
    precipitation_probability_max: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Max precipitation probability, 0–1",
    )
    rain_sum: float | None = Field(None, description="Total rain, mm")
    snowfall_sum: float | None = Field(
        None,
        description="Total snowfall (liquid equiv.), mm",
    )

    # Sky
    cloud_cover_mean: float | None = Field(None, description="Mean cloud cover, %")
    uv_index_max: float | None = Field(None, description="Max UV index")
    visibility_min: float | None = Field(None, description="Min visibility, km")

    # Moisture
    humidity_mean: float | None = Field(None, description="Mean humidity, %")

    # Pressure
    pressure_sea_mean: float | None = Field(
        None,
        description="Mean sea-level pressure, hPa",
    )

    # Condition
    condition: WeatherCondition | None = Field(
        None,
        description="Most representative condition",
    )
    summary: str | None = Field(
        None,
        description="Human-readable summary if provider offers one",
    )

    # Astronomy
    sunrise: _dt.datetime | None = Field(None, description="Sunrise UTC timestamp")
    sunset: _dt.datetime | None = Field(None, description="Sunset UTC timestamp")
    moonrise: _dt.datetime | None = Field(None, description="Moonrise UTC timestamp")
    moonset: _dt.datetime | None = Field(None, description="Moonset UTC timestamp")
    moon_phase: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Moon phase 0–1 (0=new, 0.5=full)",
    )
    daylight_duration: float | None = Field(
        None,
        description="Daylight duration in seconds",
    )

    # Radiation
    solar_radiation_sum: float | None = Field(
        None,
        description="Shortwave radiation sum, MJ/m²",
    )


# ─── Weather Alerts ───────────────────────────────────────────────────


class AlertSeverity(StrEnum):
    EXTREME = "extreme"
    SEVERE = "severe"
    MODERATE = "moderate"
    MINOR = "minor"
    UNKNOWN = "unknown"


class WeatherAlert(BaseModel):
    model_config = ConfigDict(frozen=True)

    sender_name: str = Field(description="Alert source/agency name")
    event: str = Field(description="Event type name")
    start: _dt.datetime = Field(description="Alert start, UTC")
    end: _dt.datetime | None = Field(
        None,
        description="Alert end, UTC (None if unknown)",
    )
    description: str = Field(description="Full alert description")
    severity: AlertSeverity | None = Field(None, description="Severity level")
    url: str | None = Field(None, description="URL for more information")


# ─── Per-Source Forecast Block ────────────────────────────────────────


class SourceForecast(BaseModel):
    """A complete forecast from a single model/source."""

    model_config = ConfigDict(frozen=True)

    source: ModelSource = Field(description="Which provider + model produced this data")
    minutely: list[MinutelyDataPoint] = Field(default_factory=list)
    hourly: list[WeatherDataPoint] = Field(default_factory=list)
    daily: list[DailyDataPoint] = Field(default_factory=list)
    alerts: list[WeatherAlert] = Field(default_factory=list)


# ─── Provider Results ──────────────────────────────────────────────────


class ErrorCode(StrEnum):
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK = "network"
    PARSE = "parse"
    NOT_AVAILABLE = "not_available"
    UNKNOWN = "unknown"


class ProviderErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    http_status: int | None = Field(None, description="HTTP status code if applicable")
    latency_ms: float = Field(description="How long we waited before giving up, ms")
    raw: Any | None = Field(None, description="Raw error response if available")


class ProviderSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["success"] = "success"
    provider: ProviderId
    forecasts: list[SourceForecast] = Field(
        description="One or more forecasts, keyed by model.",
    )
    fetched_at: _dt.datetime = Field(description="When this data was fetched, UTC")
    latency_ms: float = Field(description="Response time in ms")
    raw: Any | None = Field(None, description="Raw API response, if requested")


class ProviderError(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["error"] = "error"
    provider: ProviderId
    error: ProviderErrorDetail


ProviderResult = ProviderSuccess | ProviderError


# ─── Request / Response ───────────────────────────────────────────────


class ForecastRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90, description="Latitude in decimal degrees")
    longitude: float = Field(
        ge=-180,
        le=180,
        description="Longitude in decimal degrees",
    )
    granularity: list[Granularity] = Field(
        default=[Granularity.HOURLY, Granularity.DAILY],
        description="Which granularities to request",
    )
    include_raw: bool = Field(
        default=False,
        description="Include raw API responses in each ProviderResult",
    )
    timeout_ms: float = Field(
        default=10_000,
        description="Request timeout per provider in ms",
    )
    providers: list[ProviderId] | None = Field(
        None,
        description="If provided, only fetch from these providers. "
        "If None, fetch from all configured providers.",
    )


class ForecastResponseSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    succeeded: int
    failed: int


class ForecastResponseRequest(BaseModel):
    """Echo of the resolved request parameters."""

    model_config = ConfigDict(frozen=True)

    latitude: float
    longitude: float
    granularity: list[Granularity]


class ForecastResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request: ForecastResponseRequest = Field(description="Echo of request parameters")
    results: list[ProviderSuccess | ProviderError] = Field(
        description="Results from each provider (success or error)",
    )
    summary: ForecastResponseSummary
    completed_at: _dt.datetime = Field(
        description="When the aggregation completed, UTC",
    )
    total_latency_ms: float = Field(
        description="Wall-clock time for the full fan-out, ms",
    )
