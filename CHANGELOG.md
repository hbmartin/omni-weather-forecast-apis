# Changelog

## 1.0.0

Breaking release. The two public event dataclasses — `ProviderLogEvent` and `MetricEvent` —
are now keyword-only, and their timestamps are always normalized to UTC.

### Breaking changes

- **`ProviderLogEvent` and `MetricEvent` are keyword-only.** Both are declared
  `@dataclass(frozen=True, kw_only=True, slots=True)`. Positional construction now raises
  `TypeError` instead of binding a value into whichever field happens to sit at that index.

  `ProviderLogEvent`'s positional order had shifted between releases, so a call written against
  0.3.1 could silently land a `datetime` in `latency_ms` and a `float` in `error_code`, discarding
  the caller's timestamp. Because these are plain dataclasses rather than Pydantic models, nothing
  validated the result and the corruption only surfaced later, when the SQLite archive called
  `.isoformat()` on what it expected to be a datetime. Keyword-only construction removes the
  failure mode rather than detecting it.

  ```python
  # before (0.3.x) — positional, and order-sensitive
  ProviderLogEvent(ProviderId.OPEN_METEO, "success", "Fetched", timestamp, 12.5)

  # after (1.0.0) — keyword-only
  ProviderLogEvent(
      provider=ProviderId.OPEN_METEO,
      phase="success",
      message="Fetched",
      timestamp=timestamp,
      latency_ms=12.5,
  )
  ```

- **Event timestamps are normalized to UTC.** A naive `datetime` is assumed to be UTC; an aware
  `datetime` in another zone is converted to UTC, preserving the instant. `timestamp` is therefore
  always offset-aware on a constructed event, matching the `UTCDateTime` contract the Pydantic
  models already used. Previously a naive timestamp reached the SQLite archive and was written as
  an offset-less ISO string.

- **`ProviderLogEvent.extra` is typed `Mapping[str, Any]`** rather than `dict[str, Any]`, matching
  `MetricEvent.extra` and giving a frozen event a read-only mapping interface. The runtime default
  is still a `dict`; this affects type checking only.

- **Both event types use `slots=True`**, so assigning an undeclared attribute raises
  `AttributeError` instead of silently succeeding.

### Fixed

- `omni-weather --config <path>` now reports `error: config path is not a file: <path>` when the
  path exists but is a directory (or a FIFO, socket, or device). Previously it leaked the raw
  errno — `error: [Errno 21] Is a directory: '...'` — from deep in the config loader. The wording
  matches what `omni-weather doctor` already reports for the same filesystem state.

- Recovery hints for a missing config are shell-quoted, so paths containing spaces or shell
  metacharacters produce copy-pastable commands.
