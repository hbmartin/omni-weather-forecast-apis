"""Tomorrow.io plugin."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from omni_weather_forecast_apis.mapping.conditions import TOMORROW_IO_CONDITION_MAP
from omni_weather_forecast_apis.types.plugin import (
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
)
from omni_weather_forecast_apis.types.schema import (
    DailyDataPoint,
    ErrorCode,
    Granularity,
    ModelSource,
    ProviderId,
    SourceForecast,
    WeatherCondition,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.utils.time_helpers import parse_iso_datetime

_TIMESTEP_MAP = {
    Granularity.MINUTELY: "1m",
    Granularity.HOURLY: "1h",
    Granularity.DAILY: "1d",
}


class TomorrowIOConfig(BaseModel):
    api_key: str = Field(min_length=1)
    fields: list[str] | None = None


_DEFAULT_FIELDS = [
    "temperature",
    "temperatureApparent",
    "dewPoint",
    "humidity",
    "windSpeed",
    "windGust",
    "windDirection",
    "pressureSurfaceLevel",
    "pressureSeaLevel",
    "precipitationIntensity",
    "precipitationProbability",
    "rainIntensity",
    "snowIntensity",
    "cloudCover",
    "visibility",
    "uvIndex",
    "weatherCode",
]


class TomorrowIOPlugin:
    @property
    def id(self) -> ProviderId:
        return ProviderId.TOMORROW_IO

    @property
    def name(self) -> str:
        return "Tomorrow.io"

    def validate_config(self, config: dict[str, Any]) -> TomorrowIOConfig:
        return TomorrowIOConfig(**config)

    async def initialize(self, config: Any) -> TomorrowIOInstance:
        return TomorrowIOInstance(config)


class TomorrowIOInstance:
    def __init__(self, config: TomorrowIOConfig) -> None:
        self._config = config

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.TOMORROW_IO

    def get_capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            granularity_minutely=True,
            granularity_hourly=True,
            granularity_daily=True,
            max_horizon_minutely_hours=6,
            max_horizon_hourly_hours=120,
            max_horizon_daily_days=6,
            requires_api_key=True,
            multi_model=False,
            coverage="global",
            alerts=False,
        )

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx.AsyncClient,
    ) -> PluginFetchResult:
        try:
            all_hourly: list[WeatherDataPoint] = []
            all_daily: list[DailyDataPoint] = []
            raw_responses: list[Any] = []

            for gran in params.granularity:
                if gran == Granularity.MINUTELY:
                    continue
                timestep = _TIMESTEP_MAP[gran]
                url = "https://api.tomorrow.io/v4/timelines"
                fields = self._config.fields or _DEFAULT_FIELDS
                query: dict[str, Any] = {
                    "apikey": self._config.api_key,
                    "location": f"{params.latitude},{params.longitude}",
                    "fields": ",".join(fields),
                    "timesteps": timestep,
                    "units": "metric",
                }

                resp = await client.get(url, params=query)

                if resp.status_code in (401, 403):
                    return PluginFetchError(
                        code=ErrorCode.AUTH_FAILED,
                        message="Invalid API key",
                        http_status=resp.status_code,
                    )
                if resp.status_code == 429:
                    return PluginFetchError(
                        code=ErrorCode.RATE_LIMITED,
                        message="Rate limited",
                        http_status=429,
                    )
                if resp.status_code != 200:
                    return PluginFetchError(
                        code=ErrorCode.UNKNOWN,
                        message=f"HTTP {resp.status_code}",
                        http_status=resp.status_code,
                    )

                data = resp.json()
                if params.include_raw:
                    raw_responses.append(data)

                timelines = data.get("data", {}).get("timelines", [])
                for tl in timelines:
                    intervals = tl.get("intervals", [])
                    match gran:
                        case Granularity.HOURLY:
                            all_hourly.extend(self._parse_hourly(intervals))
                        case Granularity.DAILY:
                            all_daily.extend(self._parse_daily(intervals))

            source = ModelSource(provider=ProviderId.TOMORROW_IO, model="tomorrow_io")
            forecast = SourceForecast(source=source, hourly=all_hourly, daily=all_daily)
            raw = raw_responses if params.include_raw else None
            return PluginFetchSuccess(forecasts=[forecast], raw=raw)

        except httpx.TimeoutException:
            return PluginFetchError(code=ErrorCode.TIMEOUT, message="Request timed out")
        except (httpx.HTTPError, OSError) as e:
            return PluginFetchError(code=ErrorCode.NETWORK, message=str(e))
        except (KeyError, ValueError, TypeError) as e:
            return PluginFetchError(code=ErrorCode.PARSE, message=str(e))

    def _parse_hourly(self, intervals: list[dict[str, Any]]) -> list[WeatherDataPoint]:
        result: list[WeatherDataPoint] = []
        for interval in intervals:
            start = interval.get("startTime", "")
            dt = parse_iso_datetime(start)
            v = interval.get("values", {})
            wc = v.get("weatherCode")

            result.append(
                WeatherDataPoint(
                    timestamp=dt,
                    timestamp_unix=int(dt.timestamp()),
                    temperature=v.get("temperature"),
                    apparent_temperature=v.get("temperatureApparent"),
                    dew_point=v.get("dewPoint"),
                    humidity=v.get("humidity"),
                    wind_speed=v.get("windSpeed"),
                    wind_gust=v.get("windGust"),
                    wind_direction=v.get("windDirection"),
                    pressure_sea=v.get("pressureSeaLevel"),
                    pressure_surface=v.get("pressureSurfaceLevel"),
                    precipitation=v.get("precipitationIntensity"),
                    precipitation_probability=(
                        v["precipitationProbability"] / 100.0
                        if v.get("precipitationProbability") is not None
                        else None
                    ),
                    rain=v.get("rainIntensity"),
                    snow=v.get("snowIntensity"),
                    cloud_cover=v.get("cloudCover"),
                    visibility=v.get("visibility"),
                    uv_index=v.get("uvIndex"),
                    condition=(
                        TOMORROW_IO_CONDITION_MAP.get(wc, WeatherCondition.UNKNOWN)
                        if wc is not None
                        else None
                    ),
                    condition_code_original=wc,
                ),
            )
        return result

    def _parse_daily(self, intervals: list[dict[str, Any]]) -> list[DailyDataPoint]:
        result: list[DailyDataPoint] = []
        for interval in intervals:
            start = interval.get("startTime", "")
            dt = parse_iso_datetime(start)
            v = interval.get("values", {})
            wc = v.get("weatherCode")

            result.append(
                DailyDataPoint(
                    date=dt.date(),
                    temperature_max=v.get("temperatureMax"),
                    temperature_min=v.get("temperatureMin"),
                    apparent_temperature_max=v.get("temperatureApparentMax"),
                    apparent_temperature_min=v.get("temperatureApparentMin"),
                    wind_speed_max=v.get("windSpeedMax"),
                    wind_gust_max=v.get("windGustMax"),
                    precipitation_sum=v.get("precipitationIntensityMax"),
                    precipitation_probability_max=(
                        v["precipitationProbabilityMax"] / 100.0
                        if v.get("precipitationProbabilityMax") is not None
                        else None
                    ),
                    uv_index_max=v.get("uvIndexMax"),
                    visibility_min=v.get("visibilityMin"),
                    humidity_mean=v.get("humidityAvg"),
                    condition=(
                        TOMORROW_IO_CONDITION_MAP.get(wc, WeatherCondition.UNKNOWN)
                        if wc is not None
                        else None
                    ),
                    sunrise=(
                        parse_iso_datetime(v["sunriseTime"])
                        if v.get("sunriseTime")
                        else None
                    ),
                    sunset=(
                        parse_iso_datetime(v["sunsetTime"])
                        if v.get("sunsetTime")
                        else None
                    ),
                    moon_phase=v.get("moonPhase"),
                ),
            )
        return result


tomorrow_io_plugin = TomorrowIOPlugin()
