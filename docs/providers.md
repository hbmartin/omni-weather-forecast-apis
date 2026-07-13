# Providers

Three of the thirteen providers need no API key at all, so you can try the
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
| [Weather Unlocked](https://developer.weatherunlocked.com/) | `weather_unlocked` | Required | — | ✅ | ✅ | — | — | Global |
| [Google Weather](https://developers.google.com/maps/documentation/weather) | `google_weather` | Required | — | 10 d | 10 d | — | — | Global |

The minutely, hourly, and daily columns give each provider's **maximum forecast
horizon**. `✅` means the granularity is supported but the plugin declares no
horizon bound, and `—` means it is not supported at all. **Multi-model**
providers return several independent forecasts per request — Open-Meteo exposes
named numerical weather models (`best_match`, `ecmwf_ifs025`, …) and Stormglass
returns multiple upstream sources — which is what makes them useful for
ensembles.

MET Norway and NWS additionally require a `user_agent` identifying your
application; Weather Unlocked uses an `app_id` + `app_key` pair rather than a
single key. Pirate Weather's hourly horizon extends to 168 h when
`extend_hourly = true`.

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
| `weather_unlocked` | **`app_id`**, **`app_key`**, `lang`? |
| `google_weather` | **`api_key`**, `hours` (1-240, default: 48), `days` (1-10, default: 10) |

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
