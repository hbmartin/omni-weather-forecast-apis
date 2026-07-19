# Upgrading from 0.3.1 to 1.0.0

This guide covers every change between `0.3.1` and `1.0.0` that can affect a
working installation: the breaking API changes, the removed provider, the four
new providers, and the behavioral differences that are not breaking but do
change what your code, scripts, or terminal see.

## At a glance

| Area | Change | Action needed |
| --- | --- | --- |
| `ProviderLogEvent` / `MetricEvent` | Now keyword-only | Only if you **construct** them |
| Event `timestamp` | Always normalized to UTC | Only if you relied on naive timestamps |
| `weather_unlocked` | **Removed** | Required if configured |
| `ProviderLogEvent.extra` | Typed `Mapping[str, Any]` | Only if you mutate it |
| `ProviderLogEvent` | Now `slots=True` | Only for reflection/weakref users |
| Dependencies | Adds `pyjwt[crypto]>=2.10` | Automatic on install |
| Providers | Adds `nbm`, `met_office`, `xweather`, `weatherkit` | Optional |
| SQLite schema | **Unchanged** (version 2) | None — no migration |
| Python | **Unchanged** (`>=3.13`) | None |

Most consumers only *receive* events in hooks and never construct them. If that
describes you and you do not use Weather Unlocked, this upgrade is a no-op
beyond `uv sync`.

## Quick upgrade

```bash
# 1. Upgrade the package
uv add "omni-weather-forecast-apis@1.0.0"     # or: uv sync after bumping the pin

# 2. Find configurations referencing the removed provider
grep -rn "weather_unlocked" . --include="*.toml" --include="*.py"

# 3. Find positional event construction (breaks at runtime, not import time)
grep -rn "ProviderLogEvent(\|MetricEvent(" --include="*.py" .

# 4. Verify the config still validates
uv run omni-weather --config path/to/config.toml --provider open_meteo \
    --lat 34.24 --lon -117.29
```

Steps 2 and 3 are the only ones that can require code changes. Both failure
modes are loud — a Pydantic validation error and a `TypeError` respectively —
so nothing fails silently.

---

## Breaking changes

### 1. Event dataclasses are keyword-only

`ProviderLogEvent` and `MetricEvent` are both declared
`@dataclass(frozen=True, kw_only=True, slots=True)`. Positional construction now
raises `TypeError`.

```python
# 0.3.x — positional, and order-sensitive
ProviderLogEvent(ProviderId.OPEN_METEO, "success", "Fetched", timestamp, 12.5)

# 1.0.0 — keyword-only
ProviderLogEvent(
    provider=ProviderId.OPEN_METEO,
    phase="success",
    message="Fetched",
    timestamp=timestamp,
    latency_ms=12.5,
)
```

**Why this is a hard break rather than a deprecation.** `ProviderLogEvent`'s
positional field order shifted between releases, so a call written against 0.3.1
could bind a `datetime` into `latency_ms` and a `float` into `error_code`,
silently discarding the caller's timestamp. These are plain dataclasses, not
Pydantic models, so nothing validated the result — the corruption only surfaced
later, when the SQLite archive called `.isoformat()` on a value it expected to
be a datetime. Keyword-only construction removes the failure mode instead of
detecting it after the fact.

The same applies to `MetricEvent`:

```python
MetricEvent(
    kind=MetricKind.REQUEST_END,
    provider=ProviderId.OPEN_METEO,
    latency_ms=42.0,
)
```

Valid `MetricKind` members are `REQUEST_START`, `REQUEST_END`,
`RETRY_SCHEDULED`, `CACHE_HIT`, `CACHE_MISS`, `QUOTA_CONSUMED`, and
`QUOTA_EXHAUSTED`.

!!! note "Hooks are unaffected"
    A `LogHook` or `MetricsHook` receives a fully constructed event and reads
    attributes. Reading is unchanged; only construction is affected. Test code
    that fabricates events is the most common thing that needs updating.

### 2. Event timestamps are normalized to UTC

Both event types normalize `timestamp` in `__post_init__`:

- A **naive** `datetime` is assumed to be UTC and given a UTC tzinfo.
- An **aware** `datetime` in another zone is converted to UTC, preserving the
  instant.

`timestamp` is therefore always offset-aware on a constructed event, matching
the `UTCDateTime` contract the Pydantic models already used.

```python
>>> ProviderLogEvent(provider=ProviderId.NWS, phase="start", message="x",
...                  timestamp=datetime(2026, 1, 1, 12)).timestamp
datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)

>>> ProviderLogEvent(provider=ProviderId.NWS, phase="start", message="x",
...                  timestamp=datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=-8)))).timestamp
datetime.datetime(2026, 1, 1, 20, 0, tzinfo=datetime.timezone.utc)
```

Previously a naive timestamp reached the SQLite archive and was written as an
offset-less ISO string. Rows written by 1.0.0 carry an explicit `+00:00`; rows
written by earlier releases do not. If you parse `provider_logs.timestamp`
yourself, accept both forms — `datetime.fromisoformat` handles each, but the
result is naive for old rows and aware for new ones.

**Impact on hook code:** comparing an event timestamp against a naive
`datetime.now()` now raises `TypeError: can't compare offset-naive and
offset-aware datetimes`. Use `datetime.now(UTC)`.

### 3. Weather Unlocked has been removed

The `weather_unlocked` plugin, the `ProviderId.WEATHER_UNLOCKED` enum member,
the `weather_unlocked_plugin` export, and the `WeatherUnlockedConfig` type are
all gone. There is **no automatic substitution** — credentials and forecast
semantics differ between services.

An existing config fails validation at load time:

```
error: 1 validation error for OmniWeatherConfig
providers.0.plugin_id
  Input should be 'openweather', 'open_meteo', 'nws', 'nbm', 'weatherapi',
  'tomorrow_io', 'visual_crossing', 'weatherbit', 'meteosource',
  'pirate_weather', 'met_norway', 'google_weather', 'stormglass',
  'met_office', 'xweather' or 'weatherkit'
  [type=enum, input_value='weather_unlocked', input_type=str]
```

The process exits `2`. Passing the ID on the command line fails earlier, in
argument parsing:

```
omni-weather: error: argument --provider: unknown provider: weather_unlocked
```

**To fix:** delete the `[[providers]]` block whose `plugin_id =
"weather_unlocked"`, or replace it with a supported provider. Weather Unlocked
was a global, keyed, hourly+daily service; the closest replacements by shape are
`xweather` (global, `client_id` + `client_secret`, hourly + daily) and
`met_office` (global, single `api_key`, hourly + daily). Either requires its own
signup — see [Providers](providers.md).

**Existing SQLite data is not affected.** Provider IDs are stored as text and
never re-parsed into the enum on read, so historical `weather_unlocked` rows
remain queryable. Note that those rows carry the timestamp defect described in
correction 4 of [Data corrections](data-corrections.md); no repair is shipped
for them because the provider no longer runs.

Also removed with the provider: the `--provider weather_unlocked` timezone
prefetch. `_cli_needs_timezone_lookup` now triggers on `weatherkit` (any
granularity) or `tomorrow_io` (daily), rather than `weather_unlocked`
(hourly/daily) or `tomorrow_io` (daily).

### 4. `ProviderLogEvent.extra` is typed `Mapping[str, Any]`

It was `dict[str, Any]`. This matches `MetricEvent.extra` and gives a frozen
event a read-only mapping interface. The runtime default is still a `dict`, so
reads are unchanged; a type checker will now reject `event.extra["k"] = v` and
`event.extra.update(...)`.

Other mapping implementations are preserved as JSON objects when archived — the
SQLite store coerces with `dict(event.extra)` before serializing, so a
`MappingProxyType` or custom mapping no longer breaks the archive.

### 5. `ProviderLogEvent` now uses `slots=True`

`MetricEvent` was already slotted; `ProviderLogEvent` is now too. It no longer
exposes a per-instance `__dict__` and no longer supports weak references. This
can affect:

- reflection-based serializers that read `vars(event)` or `event.__dict__` —
  use `dataclasses.asdict(event)` instead;
- weak-reference caches keyed on event instances;
- monkey-patching arbitrary attributes onto an event (which was already
  impossible on a frozen dataclass for declared fields, and is now impossible
  for undeclared ones too).

Both event types were already frozen, so assignment behavior is unchanged.

**Pickles written by 0.3.x remain readable.** Both classes define `__setstate__`
to accept the legacy dict state as well as the current slot state, and they
normalize the restored timestamp to UTC on the way in. This is covered by tests
using real 0.3.1-generated pickle fixtures
(`tests/test_metrics.py::test_metric_event_restores_legacy_pickle_state`,
`tests/test_schema.py::test_provider_log_event_restores_legacy_pickle_state`).

### 6. New runtime dependency: `pyjwt[crypto]`

`pyjwt[crypto]>=2.10` is now a core dependency, required by the Apple WeatherKit
plugin to sign ES256 tokens. It installs automatically. In an environment with
pinned or vendored dependencies, or an air-gapped install, add `pyjwt` and its
`cryptography` extra to your allowlist.

---

## New providers

Four providers were added. All are opt-in — none change behavior unless you
register them. Full per-provider notes are in [Providers](providers.md).

### NOAA NBM (`nbm`) — keyless, US only

NOAA's National Blend of Models short-range station bulletin, read through the
Iowa Environmental Mesonet MOS archive. This brings the keyless provider count
from three to four.

```toml
[[providers]]
plugin_id = "nbm"
config = { station_id = "KSBD" }  # nearest NBM/METAR station
```

`station_id` is required, 4–8 characters, uppercase alphanumeric. The feed is
station-indexed rather than coordinate-interpolated, so pick the nearest
supported station to your coordinates. It provides 3-hourly points to +72 h.

Two deliberate omissions worth knowing when comparing providers: `P06` is a
**six-hour** probability of precipitation mapped to
`precipitation_probability`, and `Q06` (a six-hour accumulation) is **not**
mapped to hourly `precipitation`, because attributing a 6-hour total to one
3-hourly point would double-count during aggregation.

### Met Office (`met_office`) — API key

UK Met Office Weather DataHub Global Spot (site-specific) API. Requires a Site
Specific plan subscription.

```toml
[[providers]]
plugin_id = "met_office"
config = { api_key = "${MET_OFFICE_API_KEY}" }
```

Hourly is ≈48 h; daily returns six forecast days (the API's leading historical
row is discarded).

### Xweather (`xweather`) — client ID + secret

Xweather (formerly Aeris) `forecasts` endpoint.

```toml
[[providers]]
plugin_id = "xweather"
config = { client_id = "${XWEATHER_CLIENT_ID}", client_secret = "${XWEATHER_CLIENT_SECRET}", hourly_limit = 120, daily_limit = 10 }
```

`hourly_limit` is 1–240 (default 120), `daily_limit` is 1–15 (default 10). Each
granularity is a separately billed request. Note that Xweather reports auth and
quota failures with **HTTP 200** and a `success: false` envelope; the plugin maps
those to typed errors (`invalid_client`/`unauthorized` → `AUTH_FAILED`,
`maxed_out` → `RATE_LIMITED`, `warn_no_data` → `NO_DATA`).

### Apple WeatherKit (`weatherkit`) — signed JWT

WeatherKit REST API. Requires an Apple Developer account with WeatherKit
enabled.

```toml
[[providers]]
plugin_id = "weatherkit"
config = { team_id = "ABCDE12345", service_id = "com.example.weather", key_id = "FGHIJ67890", private_key_path = "/secure/AuthKey_FGHIJ67890.p8", hours = 48 }
```

Provide **exactly one** of `private_key_path` (path to the `.p8` file) or
`private_key` (the PEM text, which works with `${ENV_VAR}` placeholders);
supplying both or neither is a validation error. `country_code` is optional and
gates whether alerts are requested. `hours` is 1–240 (default 48).

Tokens are ES256-signed in process, cached, and refreshed before expiry. An
unreadable or invalid key surfaces as `AUTH_FAILED` before any network call.

WeatherKit requires an IANA `timezone` query parameter for daily rollups, so
registering it makes the CLI perform a timezone lookup (see the
`_cli_needs_timezone_lookup` change in §3).

---

## Behavior changes

These are not API breaks, but they change observable output. Review them if you
parse CLI output, script the setup wizard, or run the maintenance scripts.

### CLI output now includes error codes

Provider failures previously printed only a message. All three human-facing
formats now include the typed `ErrorCode`:

- **Table:** the Detail column shows `code: message` instead of `message`.
- **Plain:** the failure line gains a `code=<code>` field between `latency=` and
  `message=`.
- **All formats** (table, plain, CSV) now mirror provider errors to **stderr**,
  so failures survive stdout redirection to a file or pipe.

If you have log scrapers or assertions matching the old Detail text or plain
line format, update them.

### Explicit `--config` paths are validated up front

An explicitly supplied `--config` is now checked before any provider work:

| State | Message | Exit |
| --- | --- | --- |
| Missing | `error: config file not found: <path>` plus an init hint | `2` |
| Not a regular file (directory, FIFO, socket, device) | `error: config path is not a file: <path>` | `2` |

Previously the directory case leaked a raw errno from deep inside the config
loader — `error: [Errno 21] Is a directory: '...'`. The new wording matches what
`omni-weather doctor` already reported for the same filesystem state.

### Recovery hints are shell-correct

Hints for a missing config now quote the path for the platform's documented
shell: POSIX quoting via `shlex.quote` on Unix-like systems, and explicitly
labeled PowerShell quoting on Windows. Paths containing spaces or shell
metacharacters now produce copy-pastable commands.

### Setup wizard grouping and numbering

`omni-weather init` derives its two groups from each provider's declared
authentication kind rather than a fixed slice of the catalog:

- The second heading is now **"Requires credentials"** (was "Requires API key"),
  since not every keyed provider uses a plain API key.
- Selection numbers are now catalog positions, stable across both groups. A
  script that pipes fixed numbers into the wizard must be re-checked against the
  current list.
- Credential prompts are masked per field rather than always. NBM's `station_id`
  is not a secret and is echoed; all real credentials remain masked.
- A new `jwt` authentication kind renders as "Signed JWT (key file)".

### HTTP cache `Vary` handling

Cached responses are now keyed by `(cache key, Vary values)` rather than storing
one entry per cache key with an attached variant tuple. Multiple variants of the
same URL can now coexist instead of evicting one another, a `Vary` change on a
later response purges the now-unreachable variants, and eviction correctly
maintains the `Vary` index. `cache_max_entries` counts **variants**, not URLs.

### Raw archive is cancellation-safe

`RawArchiveTransport` now shields its append task from caller cancellation and
waits for it to finish before propagating, so cancelling a forecast mid-flight
no longer truncates a gzip member in the raw archive.

### Quota tracker recovers from a deleted database

`SqliteQuotaTracker` caches a "schema exists" flag. If the database file is
deleted or rotated out from under a long-lived tracker, operations now retry
once after recreating the schema instead of failing with `no such table`.

### Timezone lookup timeout

The coordinate-to-timezone lookup against Open-Meteo now uses an explicit 10 s
timeout rather than inheriting the client default, so an unresponsive lookup
cannot stall a run past that bound.

### Windows scheduled-task detection

`_task_is_installed` now reads `StartBoundary`, `Command`, and `Arguments` from
their specific XPath positions instead of flattening every element in the task
XML into a name→text dict. A task whose XML contains same-named elements
elsewhere is no longer misread.

### Maintenance scripts

`scripts/repair_db.py`:

- Backup filenames now carry a full UTC timestamp
  (`<stem>.pre-repair-20260719T121500123456Z.sqlite`) instead of a date only, so
  two runs on the same day no longer collide.
- The backup is taken with SQLite's online backup API inside a `BEGIN IMMEDIATE`
  transaction and reserves its filename with `touch(exist_ok=False)`, instead of
  a `shutil.copy2` outside any transaction. A failed backup is cleaned up and
  aborts the run with exit `2`.
- The Meteosource reverse-icon inference was **removed**. Inferring a source
  icon from a stored normalized condition is ambiguous — multiple icons map to
  the same condition — so daily Meteosource rows are now only rewritten when
  they provably came from the old text mapping. Re-running the repair on an
  already-repaired database is unaffected; a first run on an old database will
  now leave some daily Meteosource conditions untouched rather than rewriting
  them from an ambiguous guess.

`scripts/inspect_db.py` handles two previously-crashing states: a
`schema_metadata` table without a `schema_version` column reports
`version: unknown (missing schema_version column)`, and the timestamp-ordering
check is skipped with an explanatory line when `hourly_points` is not a
rowid-backed table.

---

## Documentation corrections

Two documentation fixes in this release describe behavior that was **already**
present in 0.3.1 — no code changed, but the previous text was wrong:

- **Timezone cache** ([CLI](cli.md)): coordinates are keyed at **six** decimal
  places (not four) and entries are refreshed after **30 days** (they were
  documented as never expiring).
- **Cross-field config defaults** ([Configuration](configuration.md)): when only
  one of `initial_backoff_ms` / `max_backoff_ms` — or one of `max_connections` /
  `max_keepalive_connections` — is set, the explicit value always wins and the
  unset side moves to meet it **in either direction**. So
  `max_keepalive_connections = 50` alone raises `max_connections` from its
  default of 20 to 50, rather than being clamped down to 20. Set both keys when
  you need a specific pool ceiling.

If you tuned either pair against the old description, re-check the effective
values.

---

## What did not change

- **SQLite schema version is still 2.** No migration is required and no repair
  script needs to run as part of this upgrade. Databases written by 0.3.1 are
  read and appended to by 1.0.0 unchanged.
- **Python requirement is still `>=3.13`.**
- **Config file format, discovery order, and default paths** are unchanged
  (beyond the removed provider and the added ones).
- **All other provider plugin IDs and their config keys** are unchanged.
- **Hook registration APIs** (`log_hooks`, `metrics_hooks`, response hooks) and
  the OpenTelemetry integration are unchanged.
- **`OmniWeatherClient` public API** is unchanged.
- **The normalized schema** (`ForecastResponse`, `WeatherDataPoint`,
  `DailyDataPoint`, `MinutelyDataPoint`, `WeatherAlert`) is unchanged.

---

## Verification

Start with `doctor`, which validates the configuration without contacting any
provider (live checks are opt-in via `--live`):

```bash
uv run omni-weather doctor --config path/to/config.toml
```

A config referencing the removed provider produces two `FAIL` rows and exit `1`:

```
│  FAIL  │ Configuration schema    │ providers.0.plugin_id: Input should be
│        │                         │ 'openweather', 'open_meteo', 'nws', …
│  FAIL  │ Provider registration 1 │ plugin_id: Input should be 'openweather', …
```

A clean config exits `0` with no `FAIL` rows. Then confirm the installation end
to end with a keyless provider:

```bash
uv run omni-weather --provider open_meteo --lat 34.24 --lon -117.29
```

To confirm your own event-constructing code:

```bash
uv run pytest tests/ -k "metric or log_event"
```

## Rollback

1.0.0 writes nothing that 0.3.1 cannot read: the SQLite schema version is
unchanged, and the only on-disk difference is that new `provider_logs.timestamp`
values carry an explicit `+00:00` offset. Downgrading is therefore safe:

```bash
uv add "omni-weather-forecast-apis==0.3.1"
```

If you added any of the four new providers to your config, remove those
`[[providers]]` blocks before downgrading — 0.3.1 rejects their plugin IDs with
the same enum validation error, in the opposite direction.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `TypeError: ProviderLogEvent.__init__() takes 1 positional argument but 4 were given` | Positional event construction | Convert to keyword arguments (§1) |
| `TypeError: can't compare offset-naive and offset-aware datetimes` | Comparing an event timestamp to `datetime.now()` | Use `datetime.now(UTC)` (§2) |
| `Input should be 'openweather', … [type=enum, input_value='weather_unlocked']` | Config references the removed provider | Remove or replace the block (§3) |
| `argument --provider: unknown provider: weather_unlocked` | CLI flag references the removed provider | Drop the flag (§3) |
| Type checker rejects `event.extra[...] = ...` | `extra` is now `Mapping` | Build a new dict; do not mutate (§4) |
| `AttributeError: 'ProviderLogEvent' object has no attribute '__dict__'` | `slots=True` | Use `dataclasses.asdict(event)` (§5) |
| `ModuleNotFoundError: No module named 'jwt'` | `pyjwt` not installed in a pinned/offline environment | Add `pyjwt[crypto]>=2.10` (§6) |
| `provide exactly one of private_key or private_key_path` | WeatherKit config sets both or neither | Set exactly one |
| `error: config path is not a file: <path>` | `--config` points at a directory | Point at the TOML file |

## Reference

- [Changelog](https://github.com/hbmartin/omni-weather-forecast-apis/blob/main/CHANGELOG.md)
- [Providers](providers.md) — per-provider config keys and semantics
- [Configuration](configuration.md) — global config reference
- [Observability](observability.md) — hook and event contracts
- [Data corrections](data-corrections.md) — history behind the normalization rules
