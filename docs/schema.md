# Normalized Schema

All provider responses are normalized into a common set of Pydantic models.
Units are standardized: temperatures in °C, wind speeds in m/s, pressure in
hPa, precipitation in mm, visibility in km.

A few fields carry provider-specific semantics that survive normalization —
notably the split between liquid-equivalent and depth snow fields, and the
probability scales. See [Unit and semantics
notes](providers.md#unit-and-semantics-notes) before comparing values across
providers.

> **A note on pressure data.** Pressure is the least reliable field providers
> report — implausible sea-level values have been observed in the wild
> (Stormglass emitting 885 hPa, Weatherbit 1074 hPa). And if you compare
> `pressure_sea` against a personal weather station, calibrate the station
> first: consumer stations report an *absolute* (station-level) pressure and a
> *relative* (sea-level) pressure, and the relative reading requires an
> elevation offset to be configured — an uncalibrated station at altitude can
> read more than 150 hPa below the true sea-level value while its absolute
> sensor is perfectly healthy. Pressure plausibility checks are planned; the
> author will be working on this soon.

## `WeatherDataPoint` (hourly)

| Field | Type | Unit |
|-------|------|------|
| `temperature`, `apparent_temperature`, `dew_point` | float \| None | °C |
| `humidity` | float \| None | % (0-100) |
| `wind_speed`, `wind_gust` | float \| None | m/s |
| `wind_direction` | float \| None | degrees |
| `pressure_sea`, `pressure_surface` | float \| None | hPa |
| `precipitation`, `rain`, `snow` (liquid equivalent), `snow_depth` | float \| None | mm |
| `snowfall_depth` (new snow depth; providers report either this or `snow`, not both) | float \| None | mm |
| `precipitation_probability` | float \| None | 0-1 |
| `cloud_cover`, `cloud_cover_low`, `cloud_cover_mid`, `cloud_cover_high` | float \| None | % |
| `visibility` | float \| None | km |
| `uv_index` | float \| None | 0-11+ |
| `solar_radiation_ghi`, `solar_radiation_dni`, `solar_radiation_dhi` | float \| None | W/m² |
| `condition` | WeatherCondition \| None | enum |
| `is_day` | bool \| None | |

## `DailyDataPoint`

| Field | Type | Unit |
|-------|------|------|
| `date` | date | |
| `temperature_max`, `temperature_min` | float \| None | °C |
| `apparent_temperature_max`, `apparent_temperature_min` | float \| None | °C |
| `wind_speed_max`, `wind_gust_max` | float \| None | m/s |
| `precipitation_sum`, `rain_sum`, `snowfall_sum` (liquid equivalent), `snowfall_depth_sum` (depth) | float \| None | mm |
| `precipitation_probability_max` | float \| None | 0-1 |
| `cloud_cover_mean` | float \| None | % |
| `humidity_mean` | float \| None | % |
| `uv_index_max` | float \| None | 0-11+ |
| `sunrise`, `sunset`, `moonrise`, `moonset` | datetime \| None | UTC |
| `moon_phase` | float \| None | 0-1 |
| `daylight_duration` | float \| None | seconds |
| `condition` | WeatherCondition \| None | enum |
| `summary` | str \| None | |

Daily dates are the provider's **local calendar dates**, not UTC days.
Absolute timestamps and astronomical instants remain UTC.

## Location timezones

`ForecastRequest.timezone` accepts an optional loadable IANA timezone name such
as `America/Los_Angeles`. Fixed numeric offsets are rejected because they cannot
apply daylight-saving rules across a forecast horizon. Normalization chooses a
valid provider-supplied IANA name first, then the request value, then an
Open-Meteo coordinate lookup.

`SourceForecast.timezone` records the IANA name actually used for that source.
A timezone lookup or ambiguous/nonexistent provider wall time becomes a
provider-level `PARSE`/network error; it does not throw from the aggregate
request or suppress successful results from other providers.

## `MinutelyDataPoint`

| Field | Type | Unit |
|-------|------|------|
| `precipitation_intensity` | float \| None | mm/h |
| `precipitation_probability` | float \| None | 0-1 |

## `WeatherAlert`

| Field | Type |
|-------|------|
| `sender_name` | str |
| `event` | str |
| `start`, `end` | datetime (UTC) |
| `description` | str |
| `severity` | `EXTREME` \| `SEVERE` \| `MODERATE` \| `MINOR` \| `UNKNOWN` |
| `url` | str \| None |

## `WeatherCondition` enum

`CLEAR`, `MOSTLY_CLEAR`, `PARTLY_CLOUDY`, `MOSTLY_CLOUDY`, `OVERCAST`, `FOG`,
`DRIZZLE`, `LIGHT_RAIN`, `RAIN`, `HEAVY_RAIN`, `FREEZING_RAIN`, `LIGHT_SNOW`,
`SNOW`, `HEAVY_SNOW`, `SLEET`, `HAIL`, `THUNDERSTORM`, `THUNDERSTORM_RAIN`,
`THUNDERSTORM_HEAVY`, `DUST`, `SAND`, `SMOKE`, `HAZE`, `TORNADO`, `HURRICANE`,
`UNKNOWN`

Each plugin maps its native condition codes onto this enum. When persisting to
SQLite the provider's original values are retained alongside the normalized
one in `condition_original` and `condition_code_original` (see [Database
Design](database.md)).

## Responses and errors

The library is designed for partial-failure tolerance. When some providers fail
— network errors, rate limits, auth issues — the response still completes with
results from the providers that succeeded.

Each entry in `response.results` is either a `ProviderSuccess` or a
`ProviderError`, discriminated by the `status` field. `response.summary` gives
counts at a glance:

```python
response.summary
# ForecastResponseSummary(total=3, succeeded=2, failed=1)
```

`ProviderSuccess` carries `forecasts`, a list of `SourceForecast` — one per
model or upstream source the provider returned (multi-model providers such as
Open-Meteo and Stormglass return several). Each `SourceForecast` holds the
`minutely`, `hourly`, `daily`, and `alerts` collections described above, plus
the optional IANA `timezone` used for civil-time normalization.

`ProviderError` carries a typed `error.code`, a human-readable
`error.message`, the `error.http_status` when one is available, and
`error.latency_ms` for how long the request ran before failing.

| `ErrorCode` | Raised when | Retried |
|-------------|-------------|:-------:|
| `AUTH_FAILED` | Credentials were rejected (HTTP 401 or 403) | — |
| `RATE_LIMITED` | The provider returned HTTP 429 | ✅ |
| `QUOTA_EXCEEDED` | The registration's `max_requests_per_day` budget for the UTC day is spent, so no request is made | — |
| `TIMEOUT` | The request exceeded the effective per-provider timeout | ✅ |
| `NETWORK` | Connection failure, or the provider returned a 5xx status | ✅ |
| `PARSE` | The response arrived but could not be normalized |  — |
| `NOT_AVAILABLE` | The provider is unconfigured, disabled, failed to initialize, supports none of the requested granularities, or returned HTTP 404 | — |
| `UNKNOWN` | Anything else, including unmapped HTTP statuses | — |

Only `NETWORK`, `TIMEOUT`, and `RATE_LIMITED` are treated as transient; see
[Retry policy](configuration.md#retry-policy-retry).

Matching on the result type keeps both branches typed:

```python
from omni_weather_forecast_apis import ProviderError, ProviderSuccess

for result in response.results:
    match result:
        case ProviderSuccess(provider=pid, forecasts=forecasts):
            for fc in forecasts:
                for pt in fc.hourly:
                    print(f"{pid} {pt.timestamp}: {pt.temperature}°C, {pt.condition}")
        case ProviderError(provider=pid, error=err):
            print(f"{pid} failed: {err.code} — {err.message}")
```

The CLI mirrors this in its [exit codes](cli.md#forecast): partial provider
failures exit `1` while still writing the successful results to SQLite.
