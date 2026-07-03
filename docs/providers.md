# Providers

| Provider | Plugin ID | API Key | Notes |
|----------|-----------|---------|-------|
| [Open-Meteo](https://open-meteo.com/) | `open_meteo` | Optional | Free tier; multiple forecast models |
| [MET Norway](https://api.met.no/) | `met_norway` | No | Requires `user_agent` identification |
| [NWS / NOAA](https://www.weather.gov/documentation/services-web-api) | `nws` | No | US coverage only; requires `user_agent` |
| [OpenWeather](https://openweathermap.org/api) | `openweather` | Yes | |
| [WeatherAPI](https://www.weatherapi.com/) | `weatherapi` | Yes | |
| [Tomorrow.io](https://www.tomorrow.io/) | `tomorrow_io` | Yes | |
| [Visual Crossing](https://www.visualcrossing.com/) | `visual_crossing` | Yes | |
| [Weatherbit](https://www.weatherbit.io/) | `weatherbit` | Yes | |
| [Meteosource](https://www.meteosource.com/) | `meteosource` | Yes | |
| [Pirate Weather](https://pirateweather.net/) | `pirate_weather` | Yes | Dark Sky-compatible API |
| [Stormglass](https://stormglass.io/) | `stormglass` | Yes | Hourly only; multi-model |
| [Weather Unlocked](https://developer.weatherunlocked.com/) | `weather_unlocked` | Yes | Requires `app_id` + `app_key` |
| [Google Weather](https://developers.google.com/maps/documentation/weather) | `google_weather` | Yes | Google Maps Platform Weather API |

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
