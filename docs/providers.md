# Providers

Three of the fifteen providers need no API key at all, so you can try the
library without signing up for anything.

| Provider | Plugin ID | API key | Minutely | Hourly | Daily | Alerts | Multi-model | Coverage |
|----------|-----------|---------|---------:|-------:|------:|:------:|:-----------:|----------|
| [Open-Meteo](https://open-meteo.com/) | `open_meteo` | Optional | 1 h | 16 d | 16 d | — | ✅ | Global |
| [MET Norway](https://api.met.no/) | `met_norway` | None | — | 9 d | — | — | — | Nordics |
| [NWS / NOAA](https://www.weather.gov/documentation/services-web-api) | `nws` | None | — | ✅ | ✅ | ✅ | — | US only |
| [OpenWeather](https://openweathermap.org/api) | `openweather` | Required | 1 h | 48 h | 8 d | ✅ | — | Global |
| [WeatherAPI](https://www.weatherapi.com/) | `weatherapi` | Required | — | 14 d | 14 d | ✅ | — | Global |
| [Tomorrow.io](https://www.tomorrow.io/) | `tomorrow_io` | Required | 1 h | 5 d | 6 d | — | — | Global |
| [Visual Crossing](https://www.visualcrossing.com/) | `visual_crossing` | Required | — | 15 d | 15 d | ✅ | — | Global |
| [Weatherbit](https://www.weatherbit.io/) | `weatherbit` | Required | — | 10 d | 16 d | — | — | Global |
| [Meteosource](https://www.meteosource.com/) | `meteosource` | Required | 1 h | 7 d | 30 d | ✅ | — | Global |
| [Pirate Weather](https://pirateweather.net/) | `pirate_weather` | Required | 1 h | 48 h | 8 d | ✅ | — | Global |
| [Stormglass](https://stormglass.io/) | `stormglass` | Required | — | ✅ | — | — | ✅ | Global |
| [Google Weather](https://developers.google.com/maps/documentation/weather) | `google_weather` | Required | — | 10 d | 10 d | — | — | Global |
| [Met Office](https://datahub.metoffice.gov.uk/) | `met_office` | Required | — | 48 h | 7 d | — | — | Global |
| [Xweather](https://www.xweather.com/) | `xweather` | Required | — | 10 d | 15 d | — | — | Global |
| [Apple WeatherKit](https://developer.apple.com/weatherkit/) | `weatherkit` | Required | 1 h | 10 d | 10 d | ✅ | — | Global |

The minutely, hourly, and daily columns give each provider's **maximum forecast
horizon**. `✅` means the granularity is supported but the plugin declares no
horizon bound, and `—` means it is not supported at all. **Multi-model**
providers return several independent forecasts per request — Open-Meteo exposes
named numerical weather models (`best_match`, `ecmwf_ifs025`, …) and Stormglass
returns multiple upstream sources — which is what makes them useful for
ensembles.

MET Norway and NWS additionally require a `user_agent` identifying your
application; Xweather uses a `client_id` + `client_secret` pair, and Apple
WeatherKit signs each request with an ES256 JWT built from your Apple
Developer credentials rather than sending a static key. Pirate Weather's
hourly horizon extends to 168 h when `extend_hourly = true`.

## Configuration reference

Each provider accepts a typed config dict. Required fields are marked in
**bold**. Any string value may be an [environment variable
placeholder](configuration.md#environment-variable-placeholders).

| Provider | Config Keys |
|----------|-------------|
| `open_meteo` | `api_key`?, `models` (default: `["best_match"]`), `extra_hourly_vars`?, `extra_daily_vars`? |
| `met_norway` | **`user_agent`**, `altitude`?, `variant` (`"compact"` \| `"complete"`, default: `"complete"`) |
| `nws` | **`user_agent`**, `grid_override`? (`{office, grid_x, grid_y}`) |
| `openweather` | **`api_key`**, `exclude`?, `units` (`"standard"` \| `"metric"` \| `"imperial"`, default: `"metric"`) |
| `weatherapi` | **`api_key`**, `days` (1-14, default: 7), `aqi` (default: false), `alerts` (default: true) |
| `tomorrow_io` | **`api_key`**, `fields`? |
| `visual_crossing` | **`api_key`**, `include` (default: `"hours,days,alerts"`) |
| `weatherbit` | **`api_key`**, `hours` (1-240, default: 48), `units` (`"M"` \| `"S"` \| `"I"`, default: `"M"`) |
| `meteosource` | **`api_key`**, `sections` (default: `["current", "hourly", "daily"]`) |
| `pirate_weather` | **`api_key`**, `extend_hourly` (default: false), `version` (`"1"` \| `"2"`, default: `"2"`) |
| `stormglass` | **`api_key`**, `sources` (default: `["sg"]`), `params` (list of weather variables) |
| `google_weather` | **`api_key`**, `hours` (1-240, default: 48), `days` (1-10, default: 10) |
| `met_office` | **`api_key`** |
| `xweather` | **`client_id`**, **`client_secret`**, `hourly_limit` (1-240, default: 120), `daily_limit` (1-15, default: 10) |
| `weatherkit` | **`team_id`**, **`service_id`**, **`key_id`**, `private_key` or `private_key_path` (exactly one), `country_code`?, `hours` (1-240, default: 48) |

## Google Weather

The `google_weather` plugin talks to the [Google Maps Platform Weather
API](https://developers.google.com/maps/documentation/weather). It needs a
Google Maps Platform API key with the Weather API enabled.

- Hourly forecasts come from `forecast/hours:lookup` (paginated, up to 240
  hours; the `hours` config key bounds how much is fetched).
- Daily forecasts come from `forecast/days:lookup` (up to 10 days) and
  aggregate Google's daytime/nighttime part forecasts into the normalized
  daily schema.
- Responses are requested in metric units and converted to the library's
  normalized units (km/h wind speeds become m/s, etc.).

## Met Office

The `met_office` plugin talks to the [Met Office Weather DataHub Global Spot
API](https://datahub.metoffice.gov.uk/) (site-specific forecasts). Subscribe
to the Site Specific plan on the DataHub portal to obtain the `api_key`,
which is sent as an `apikey` request header.

- Hourly forecasts come from the `point/hourly` endpoint (≈48 h) and daily
  forecasts from `point/daily` (≈7 days); the service snaps the request to
  the nearest of its global forecast sites.
- Sea-level pressure arrives in pascals and is converted to hPa.
- Daily rows merge the API's day/night split: `temperature_max` is the day
  maximum, `temperature_min` the night minimum, and wind maxima take the
  larger of the midday/midnight values. `humidity_mean`,
  `pressure_sea_mean`, and `visibility_min` stay `None` because the API
  only exposes single-instant midday values, not daily aggregates.

## Xweather

The `xweather` plugin talks to the [Xweather (formerly Aeris) Weather
API](https://www.xweather.com/docs/weather-api) `forecasts` endpoint with
`filter=1hr` for hourly and `filter=day` for daily periods.

- Xweather reports auth and quota failures with **HTTP 200** and a
  `success: false` envelope; the plugin maps envelope error codes to typed
  errors (`invalid_client`/`unauthorized` → `AUTH_FAILED`, `maxed_out` →
  `RATE_LIMITED`, `warn_no_data` → `NO_DATA`).
- `hourly_limit` and `daily_limit` bound how many periods are requested;
  each granularity is a separate billed request.
- The forecast timezone comes from the response's `profile.tz` field, so no
  extra timezone lookup is needed.

## Apple WeatherKit

The `weatherkit` plugin talks to the [WeatherKit REST
API](https://developer.apple.com/documentation/weatherkitrestapi). It needs
an Apple Developer account with WeatherKit enabled: a Team ID, a WeatherKit
service identifier, and a `.p8` signing key (Key ID + private key).

- Provide the key as either `private_key_path` (path to the `.p8` file) or
  `private_key` (the PEM text, handy with `${ENV_VAR}` placeholders) —
  exactly one of the two.
- Each request is authenticated with a short-lived ES256 JWT signed in
  process; tokens are cached and refreshed before expiry. An unreadable or
  invalid key surfaces as `AUTH_FAILED` before any network call.
- One `GET /api/v1/weather/...` call covers minutely
  (`forecastNextHour`, available only in some regions), hourly
  (`forecastHourly`, bounded by the `hours` config key), daily
  (`forecastDaily`, 10 days), and alerts (`weatherAlerts`, only requested
  when `country_code` is configured).
- The API requires an IANA `timezone` query parameter for daily rollups, so
  the plugin resolves one from the request or the keyless Open-Meteo
  lookup.

## Unit and semantics notes

A few provider-specific behaviors are worth knowing when comparing values
across providers (see [Data corrections](data-corrections.md) for the
history behind these rules):

- **Snow fields are split by what the provider reports.** `snow` /
  `snowfall_sum` hold liquid-equivalent millimetres (OpenWeather, Met
  Office `totalSnowAmount`, and Open-Meteo via
  `snowfall_water_equivalent`); `snowfall_depth` / `snowfall_depth_sum`
  hold new-snow depth in millimetres (Open-Meteo `snowfall`, Pirate
  Weather `snowAccumulation`, Xweather `snowCM`, WeatherKit
  `snowfallAmount`). No 10:1 conversion is ever guessed between the two.
- **Pirate Weather liquid amounts** come from `liquidAccumulation`
  (cm→mm), falling back to `precipAccumulation` only for rain-typed rows —
  when snowing, `precipAccumulation` reports snow depth and is not a
  liquid amount. `precipIntensity` (a mm/h rate) is used only for the
  minutely `precipitation_intensity` field.
- **Open-Meteo and Meteosource emit offset-free local times**, but they
  resolve DST discontinuities deterministically instead of failing the whole
  run: an ambiguous fall-back hour maps to the earlier (pre-transition)
  instant, and a nonexistent spring-forward hour is shifted to the real
  post-gap instant. A single transition hour therefore no longer discards an
  entire day of hourly, daily, and minutely points.
- **A 200 response with no usable content is reported as `NO_DATA`.** When a
  provider answers successfully but yields no hourly, daily, minutely, or
  alert data, the result is a typed `NO_DATA` error (see
  [schema](schema.md#responses-and-errors)) rather than a hollow success, so a
  silently dead provider is recorded as an error instead of an empty column.
- **Daily dates are local calendar dates.** Pirate Weather and OpenWeather
  daily epochs are converted with an IANA location timezone, so a Berlin
  forecast for "January 1" is dated January 1 even though its local midnight
  is December 31 in UTC.
- **Generic precipitation is not automatically rain.** Weatherbit leaves
  `rain` unset because it exposes only a generic amount. WeatherAPI populates
  `rain` only when its rain/snow indicators identify rain without snow.
- **WeatherAPI daily rows have no feels-like or minimum visibility** —
  `apparent_temperature_max/min` and `visibility_min` are `None` rather
  than approximations (the API only offers air temps and a daily average
  visibility).
- **Probability scales are declared per provider** (percent for NWS,
  Open-Meteo, Google, Meteosource, WeatherAPI, Visual Crossing,
  Tomorrow.io, Weatherbit, Met Office, Xweather; 0-1 fractions for
  OpenWeather, Pirate Weather, Stormglass, WeatherKit), so a raw `1` from
  a percent API means 1%, never 100%.
