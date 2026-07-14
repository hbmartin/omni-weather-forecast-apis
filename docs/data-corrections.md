# Data corrections (2026-07-13)

A correctness audit found multiple defects, several of which corrupted
normalized forecast data on default configurations. This page records what
changed semantically, how existing databases were repaired, and which
caveats remain. Rows written before the fix are identifiable by
`forecast_runs.normalization_revision = 1`; rows written with the corrected
normalizers use revision `2`. This marker is authoritative even when an older
row already has an `app_version`. Repaired databases carry a `db_repairs`
audit table listing every action and row count.

## Parser defects fixed

| # | Defect | Wrong before | Correct after |
|---|--------|--------------|---------------|
| 1 | Meteosource icon map used a fictional 1–8 table | icon 5 (Mostly cloudy) → `drizzle`, 6 (Cloudy) → `rain`, 7 (Overcast) → `snow`, 8 → `thunderstorm` | Full official 1–36 table; icon 1 ("Not available") falls back to summary text |
| 2 | Pirate Weather SI accumulations stored unconverted | `precipAccumulation`/`snowAccumulation` are **cm**; stored as mm (10× low); `precipIntensity` (mm/h rate) leaked into the amount field | Liquid from `liquidAccumulation` (cm→mm, rain-typed `precipAccumulation` fallback); snow depth cm→mm into `snowfall_depth` |
| 3 | Text keyword ordering mapped wintry showers to RAIN | "Snow Showers", "Sleet showers", "Wintry Showers" → `rain`; "Mostly/Partly Sunny" → `clear`; "Partially cloudy"/"Cloudy" → `unknown` | Wintry phrases win before the generic "showers"; sunny/cloudy variants map to their own buckets |
| 4 | Weather Unlocked local times stored as UTC | Every hourly timestamp and sunrise/sunset was treated as an absolute UTC instant | An IANA location timezone converts wall times with date-specific DST rules; ambiguous/nonexistent wall times fail that provider |
| 5 | Open-Meteo DNI held horizontal direct radiation | `solar_radiation_dni` = `direct_radiation` (horizontal plane) | Requests and stores `direct_normal_irradiance` |
| 6 | Probability heuristic collapsed 1% into 100% | Any raw value ≤ 1 was treated as a 0–1 fraction, so a raw `1` (1%) became 1.0 | Every plugin declares its provider's documented scale (percent vs fraction) explicitly |
| 7 | Daily dates east of Greenwich off by one day | Pirate Weather / OpenWeather daily epochs converted to the **UTC** calendar date | Local calendar date computed with the provider's IANA timezone, never a fixed offset |
| 8 | OpenWeather alert tag stored as URL | `alerts[].tags[0]` (a category label) landed in `WeatherAlert.url` | `url` is `None` (OpenWeather provides no alert link) |
| 9 | Weatherbit `units="S"`/`"I"` latent unit bugs | Kelvin temperatures passed through as °C; imperial `vis` (miles) and `snow_depth` (inches) unconverted | Kelvin→°C, miles→km, inches→mm conversions per configured units |
| 10 | WeatherAPI fabricated daily values | `apparent_temperature_max/min` were copies of the air temps; `avgvis_km` (an average) stored as `visibility_min`; a valid 0% rain chance fell through to the snow chance | Feels-like and visibility_min left `NULL`; probability is the max of the chances present |
| 11 | Snow semantics mixed depth and liquid equivalent | Open-Meteo/Pirate depth values sat in the liquid-equivalent `snow`/`snowfall_sum` fields (~7–10× the liquid value) | Two fields: `snow` (liquid-equivalent mm) and new `snowfall_depth` (depth mm); each provider maps only what it actually reports. Open-Meteo now also requests `snowfall_water_equivalent` for real liquid values |
| 12 | Unguarded timestamp keys | A malformed OpenWeather/Weatherbit row raised out of the plugin | Rows missing their timestamp key are skipped |
| 13 | Tomorrow.io stored zero rows | The parser only accepted the legacy Timelines `startTime` key; the modern `/v4/weather/forecast` response keys entries with `time`, so every entry was silently skipped (discovered by reading the new raw payload archive) | Both keys accepted |
| 14 | Tomorrow.io daily dates treated UTC timestamps as local dates | Taking the date portion of a UTC timestamp can select the preceding/following location day | Absolute timestamp converted through the location's IANA timezone before taking its civil date |
| 15 | Weatherbit snowfall depth stored as liquid-equivalent snow | `snow` populated normalized `snow` / `snowfall_sum`, even though Weatherbit documents physical accumulated snowfall | Weatherbit `snow` populates `snowfall_depth` / `snowfall_depth_sum`; liquid-equivalent snow remains unset |
| 16 | Weatherbit generic precipitation copied into rain | `precip` populated both total precipitation and rain, including snow/mixed intervals | `precip` populates only generic precipitation; rain remains unset without a rain-specific field |
| 17 | WeatherAPI generic precipitation copied into rain | `precip_mm`/`totalprecip_mm` always populated rain, including snow/mixed intervals | Generic precipitation remains in `precipitation`; rain is populated only when rain is indicated without snow |
| 18 | Open-Meteo and Meteosource wall times were requested/interpreted as UTC | A caller-supplied IANA timezone was ignored, and offset-free timestamps could represent the wrong instant | The requested IANA timezone is sent upstream, offset-free timestamps are localized with DST-aware rules, and the source timezone is recorded |
| 19 | Provider timezone provenance was incomplete | NWS, Google Weather, Visual Crossing, WeatherAPI, and Weatherbit could normalize data without retaining their provider-supplied IANA zone | Valid provider timezones are retained on `SourceForecast`, with the request zone as fallback where applicable |

## Schema additions

- `hourly_points.snowfall_depth` and `daily_points.snowfall_depth_sum`
  (new snowfall depth, mm) — also exposed in `stacking_features`.
- `source_forecasts.timezone` — IANA timezone used for civil-time
  normalization; also exposed in `stacking_features`.
- `forecast_runs.raw_archive_path` — links each run to its raw payload
  archive (see below).
- `forecast_runs.app_version` — package version stamp, giving pre-/post-fix
  provenance.
- `forecast_runs.request_timezone` — resolved IANA timezone sent with the
  aggregate request.
- `forecast_runs.normalization_revision` — durable semantic revision marker;
  migrated historical rows default to `1`, while new corrected rows use `2`.
- `schema_metadata.schema_version` — singleton structural schema version used
  to reject databases created by newer, incompatible releases.
- `db_repairs` — audit log written by `scripts/repair_db.py` and the follow-up
  `scripts/repair_db_v2.py`.

## Follow-up v2 repair

For a database on which `scripts/repair_db.py` v1 has already run, apply the
narrow follow-up repair with:

```bash
uv run scripts/repair_db_v2.py path/to/forecasts.sqlite --dry-run
uv run scripts/repair_db_v2.py path/to/forecasts.sqlite
```

Version 2.0 moves legacy Weatherbit snow values into the depth columns, clears
nonzero Weatherbit rain values copied from generic precipitation, and clears
nonzero legacy Pirate Weather daily `precipitation_sum` values. Exact zeros are
preserved. It leaves Pirate Weather `rain_sum` and all historical timestamp/date
rows untouched because the required source semantics or historical IANA rules
cannot be reconstructed safely from normalized rows alone.

A real run first creates
`<stem>.pre-repair-v2-YYYYMMDD.sqlite`, records each action and row count in
`db_repairs`, and commits all actions in one transaction. `--dry-run` rolls the
data changes back and creates no backup. If a Weatherbit source value conflicts
with an unequal non-null corrected destination, the transaction aborts; equal
duplicates collapse safely.

## Raw payload archive

`raw_json` was never populated for successful fetches, so the pre-fix data
could only be repaired from its normalized columns. To preserve the HTTP
inputs needed for future parser recovery, every network response is now
archived as gzipped JSONL (one line per response: `ts`, `method`, `url`,
`status`, `body`) in a `raw/` directory next to the SQLite database — one file
per CLI invocation, on by default when `--sqlite` is used. Disable with
`--no-raw-archive` or `[http] raw_archive_enabled = false`. URLs are stored
verbatim (including API keys in query strings); the `raw/` directory is
gitignored and there is no automatic retention — delete old files manually.
Archives only cover traffic recorded after the feature is enabled, and replay
still depends on each archived response being complete and parseable; they do
not make older normalized-only runs reconstructable.

## Repair of crestline_forecasts.sqlite

`scripts/repair_db.py` ran on 2026-07-13 after backing the file up to
`crestline_forecasts.pre-repair-20260713.sqlite`. Actions and row counts:

| Action | Rows |
|--------|------|
| Recompute hourly conditions from stored originals | 131 |
| Recompute daily conditions from stored summaries | 16 |
| Move Open-Meteo hourly `snow` (depth mm) → `snowfall_depth` | 168 |
| Move Open-Meteo daily `snowfall_sum` → `snowfall_depth_sum` | 7 |
| Move Pirate Weather hourly `snow` (cm ×10) → `snowfall_depth` | 48 |
| Move Pirate Weather daily `snowfall_sum` (cm ×10) → `snowfall_depth_sum` | 8 |
| NULL ambiguous Pirate Weather precipitation/rain (zeros kept) | 48 |
| NULL Open-Meteo `solar_radiation_dni` (was horizontal direct) | 168 |
| NULL ambiguous hourly probability = 1.0 (1% vs 100%) | 24 |
| NULL ambiguous daily probability = 1.0 | 3 |
| NULL WeatherAPI fabricated daily feels-like / visibility_min | 7 |

Representative condition corrections (before → after):

- Meteosource "Mostly cloudy": `drizzle` → `mostly_cloudy`; "Overcast":
  `snow` → `overcast`; "Sunny": `partly_cloudy` → `clear`
- NWS "Partly Sunny": `clear` → `partly_cloudy`; "Mostly Sunny":
  `clear` → `mostly_clear`
- Visual Crossing "Partially cloudy": `unknown` → `partly_cloudy` (87 rows)

## Residual caveats for pre-fix data

- **Open-Meteo DNI is NULL** for pre-fix rows. The recorded value was
  horizontal direct radiation, reconstructable as
  `solar_radiation_ghi - solar_radiation_dhi` if ever needed.
- **Probabilities that were exactly 1.0** for percent-scale providers were
  NULLed — a raw `1` (1%) and a raw `100` collapsed into the same stored
  value and cannot be distinguished. Stored values strictly between 0 and 1
  were kept; a fractional raw percent (e.g. `0.5` meaning 0.5%) would also
  have been misread, but percent APIs report integers in practice.
- **Pirate Weather precipitation amounts** were NULLed (zeros kept): the
  old parser mixed cm accumulations with mm/h intensity rates per row and
  the source cannot be recovered.
- **Weather Unlocked rows** would need a timestamp shift by the location's
  UTC offset; this database has none (the provider errored in both runs),
  so no shift was implemented in the repair script.
- **Weatherbit sea-level pressure** reached 1074 hPa in one run — outside
  any plausible sea-level value. This is provider-side data (the parser
  passes `slp` through unchanged) and was left as-is.
