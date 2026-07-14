# Future work

Known issues and improvements deliberately deferred from the 2026-07-13
correctness sweep (see [Data corrections](data-corrections.md)).

## Reliability

- **Connect timeouts are never retried.** `httpx2.ConnectTimeout` is a
  subclass of `httpx2.HTTPError` but not of
  `ConnectError`/`NetworkError`/`ProtocolError`, so `_get_json`
  (`plugins/_base.py`) classifies it as `ErrorCode.UNKNOWN`, which is not
  in the client's retryable set — contradicting the documented [retry
  policy](configuration.md), which promises that timeouts are retried. Fix:
  catch `httpx2.TimeoutException` first and map it to `ErrorCode.TIMEOUT`.
- **Plugin-raised httpx timeouts are labeled NETWORK.** In
  `client.py::_attempt_fetch` the `except httpx2.HTTPError` branch catches
  `TimeoutException` before the generic handler that would classify it as
  TIMEOUT. Retryable either way; only logs/metrics are misattributed.

## HTTP cache

- `CachingTransport._response_from_revalidation` mutates the shared cache
  entry outside the lock; a concurrent reader between awaits can observe a
  half-updated entry.
- `CachingTransport` with `max_entries=0` would raise `StopIteration` on
  the first store. Unreachable via config (`cache_max_entries` is `ge=1`),
  but worth a guard if the transport is ever constructed directly.

## Providers

- **OpenWeather hourly `is_day` is always `None`** — hourly One Call
  entries carry no sunrise/sunset; it could be derived from the daily
  block.
- **Weatherbit imperial pressure** — `slp`/`pres` are passed through
  unconverted for `units="I"`; verify against Weatherbit's docs whether
  imperial responses switch pressure to inHg.
- **Weatherbit sea-level pressure plausibility** — one stored run shows
  `slp` up to 1074 hPa (implausible at sea level). Consider a
  provider-side plausibility filter or at least a data-quality flag in
  `scripts/inspect_db.py`.

## Data model

- Condition vocabulary gaps: provider texts like "Patchy rain possible" or
  "Thundery outbreaks" map through generic keywords; a per-provider code
  table (e.g. WeatherAPI's numeric condition codes) would be more precise
  than text matching.
