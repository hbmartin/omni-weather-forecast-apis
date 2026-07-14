from __future__ import annotations

import argparse
import asyncio
import csv
import importlib
import json
import logging
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypeVar, cast
from uuid import uuid4

from omni_weather_forecast_apis._cli_discovery import print_providers, run_doctor
from omni_weather_forecast_apis._cli_paths import (
    default_config_path,
    find_config_path,
    init_target_path,
)
from omni_weather_forecast_apis._cli_setup import InitDefaults, run_init
from omni_weather_forecast_apis._cli_timezone_cache import (
    reconcile_cli_timezone,
    resolve_cli_timezone,
)
from omni_weather_forecast_apis.client import create_omni_weather
from omni_weather_forecast_apis.quota import SqliteQuotaTracker
from omni_weather_forecast_apis.sqlite_store import (
    save_forecast_response,
    save_provider_logs,
)
from omni_weather_forecast_apis.types import (
    DailyDataPoint,
    ForecastRequest,
    ForecastResponse,
    Granularity,
    LogHook,
    MinutelyDataPoint,
    OmniWeatherConfig,
    ProviderError,
    ProviderId,
    ProviderLogEvent,
    ProviderSuccess,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.utils import utc_now

T = TypeVar("T")


def _parse_provider_id(value: str) -> ProviderId:
    try:
        return ProviderId(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"unknown provider: {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="omni-weather",
        description="Fetch normalized forecasts from multiple weather providers.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to TOML config (default: platform-native config directory)",
    )
    parser.add_argument(
        "--lat",
        type=float,
        default=None,
        help="Latitude in decimal degrees (overrides config)",
    )
    parser.add_argument(
        "--lon",
        type=float,
        default=None,
        help="Longitude in decimal degrees (overrides config)",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help=(
            "Path to the SQLite database output file (overrides config); "
            "results are not persisted when omitted"
        ),
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv", "ndjson"],
        default="table",
        dest="output_format",
        help=(
            "Output format: human-readable table, full response as JSON, "
            "one flattened data point per CSV row, or one JSON object per "
            "line (default: table)"
        ),
    )
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        type=_parse_provider_id,
        help="Restrict to one or more configured providers",
    )
    parser.add_argument(
        "--granularity",
        action="append",
        choices=[item.value for item in Granularity],
        default=[],
        help="Forecast granularity to request (repeatable)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Provider language preference (overrides config)",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Persist raw provider payloads alongside normalized results",
    )
    parser.add_argument(
        "--no-raw-archive",
        action="store_true",
        help=(
            "Do not archive raw HTTP payloads to the raw/ directory next to "
            "the SQLite database"
        ),
    )
    parser.add_argument(
        "--timeout-ms",
        type=float,
        default=None,
        help="Override the default request timeout in milliseconds",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Enable verbose debug output and write a log file next to the SQLite "
            "database, or ./omni-weather.log when --sqlite is omitted"
        ),
    )
    subcommands = parser.add_subparsers(dest="command")
    init_parser = subcommands.add_parser(
        "init",
        help="Interactively create or replace a configuration",
    )
    init_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        dest="command_config",
        help="Configuration path to create or edit",
    )
    subcommands.add_parser(
        "providers",
        help="Show provider coverage, granularities, authentication, and setup links",
    )
    doctor_parser = subcommands.add_parser(
        "doctor",
        help="Validate configuration and optionally contact providers",
    )
    doctor_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        dest="command_config",
        help="Configuration path to diagnose",
    )
    doctor_parser.add_argument(
        "--live",
        action="store_true",
        help="Opt in to live provider API checks",
    )
    doctor_parser.add_argument(
        "--provider",
        action="append",
        default=[],
        type=_parse_provider_id,
        dest="doctor_provider",
        help="Restrict provider-specific checks (repeatable)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the async CLI entrypoint."""

    parsed = build_parser().parse_args(argv)
    try:
        return asyncio.run(_dispatch(parsed))
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _init_defaults(parsed: argparse.Namespace) -> InitDefaults:
    granularity_values = cast(list[str], parsed.granularity)
    return InitDefaults(
        latitude=cast(float | None, parsed.lat),
        longitude=cast(float | None, parsed.lon),
        sqlite=cast(Path | None, parsed.sqlite),
        granularities=tuple(Granularity(item) for item in granularity_values),
        providers=tuple(cast(list[ProviderId], parsed.provider)),
    )


def _config_argument(parsed: argparse.Namespace) -> Path | None:
    command_path = cast(Path | None, getattr(parsed, "command_config", None))
    return command_path or cast(Path | None, parsed.config)


def _automatic_setup_available() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


async def _run_explicit_init(parsed: argparse.Namespace) -> int:
    target_path = init_target_path(_config_argument(parsed))
    result = run_init(
        target_path,
        defaults=_init_defaults(parsed),
        automatic=False,
    )
    if result is None or not result.run_forecast:
        return 0
    forecast_args = build_parser().parse_args(["--config", str(result.path)])
    return await _async_main(forecast_args)


async def _run_forecast(parsed: argparse.Namespace) -> int:
    explicit_path = cast(Path | None, parsed.config)
    if (config_path := find_config_path(explicit_path)) is not None:
        parsed.config = config_path
        return await _async_main(parsed)
    expected_path = default_config_path()
    if not _automatic_setup_available():
        print(
            f"error: no configuration found at {expected_path}",
            file=sys.stderr,
        )
        print(
            f"run 'omni-weather init --config {expected_path}' in an interactive terminal",
            file=sys.stderr,
        )
        return 2
    result = run_init(
        expected_path,
        defaults=_init_defaults(parsed),
        automatic=True,
    )
    if result is None:
        return 2
    parsed.config = result.path
    return await _async_main(parsed)


async def _dispatch(parsed: argparse.Namespace) -> int:
    match parsed.command:
        case "init":
            return await _run_explicit_init(parsed)
        case "providers":
            print_providers()
            return 0
        case "doctor":
            path = find_config_path(_config_argument(parsed)) or default_config_path()
            return await run_doctor(
                path,
                live=cast(bool, parsed.live),
                provider_filter=cast(list[ProviderId], parsed.doctor_provider),
            )
        case _:
            return await _run_forecast(parsed)


def _resolve_required(
    cli_value: object,
    config_value: object,
    name: str,
) -> object:
    resolved = cli_value if cli_value is not None else config_value
    if resolved is not None:
        return resolved
    print(f"error: --{name} is required (via CLI flag or config file)", file=sys.stderr)
    sys.exit(2)


def _resolve_optional(cli_value: T | None, config_value: T) -> T:
    return cli_value if cli_value is not None else config_value


def _default_raw_archive_path(sqlite_path: Path) -> Path:
    """One archive file per CLI invocation, named by UTC start time."""

    stamp = utc_now().strftime("%Y%m%dT%H%M%S.%fZ")
    unique_suffix = uuid4().hex[:12]
    return sqlite_path.parent / "raw" / f"{stamp}-{unique_suffix}.jsonl.gz"


def _selected_provider_ids(
    config: OmniWeatherConfig,
    providers: list[ProviderId] | None,
) -> set[ProviderId]:
    enabled = {
        registration.plugin_id
        for registration in config.providers
        if registration.enabled
    }
    return enabled if providers is None else enabled & set(providers)


def _cli_needs_timezone_lookup(
    provider_ids: set[ProviderId],
    granularities: list[Granularity],
) -> bool:
    requested = set(granularities)
    return (
        ProviderId.WEATHER_UNLOCKED in provider_ids
        and bool(requested & {Granularity.HOURLY, Granularity.DAILY})
    ) or (ProviderId.TOMORROW_IO in provider_ids and Granularity.DAILY in requested)


def _print_timezone_warnings(warnings: tuple[str, ...]) -> None:
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def _setup_debug_logging(log_path: Path) -> LogHook:
    """Configure debug output to stderr and a log file.

    Prefers loguru (installed via the ``cli`` extra) and falls back to
    stdlib logging when it is unavailable. Returns a LogHook callback
    that logs ProviderLogEvents.
    """
    try:
        loguru_logger = importlib.import_module("loguru").logger
    except ImportError:
        print(
            "warning: loguru is not installed; using stdlib logging for --debug. "
            'Install the CLI extra for richer output: pip install "omni-weather-forecast-apis[cli]"',
            file=sys.stderr,
        )
        return _setup_stdlib_debug_logging(log_path)

    loguru_logger.remove()
    loguru_logger.add(
        sys.stderr,
        level="DEBUG",
        format="{time:HH:mm:ss} | {level:<7} | {message}",
    )
    loguru_logger.add(
        str(log_path),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}",
        rotation="10 MB",
    )
    debug_message = f"Debug logging enabled, writing to {log_path}"
    loguru_logger.info(debug_message)

    def _loguru_hook(event: ProviderLogEvent) -> None:
        match event.phase:
            case "start" | "retry":
                message = f"[{event.provider.value}] {event.message}"
                loguru_logger.debug(message)
            case "success":
                message = (
                    f"[{event.provider.value}] {event.message} "
                    f"(latency={event.latency_ms:.0f}ms)"
                )
                loguru_logger.info(message)
            case "error":
                error_code = event.error_code.value if event.error_code else "unknown"
                message = (
                    f"[{event.provider.value}] {event.message} "
                    f"(code={error_code}, http={event.http_status}, "
                    f"latency={event.latency_ms:.0f}ms)"
                )
                loguru_logger.warning(message)

    return _loguru_hook


def _setup_stdlib_debug_logging(log_path: Path) -> LogHook:
    """Stdlib-logging fallback for --debug when loguru is unavailable."""

    debug_logger = logging.getLogger("omni_weather_forecast_apis.cli.debug")
    debug_logger.setLevel(logging.DEBUG)
    debug_logger.propagate = False
    debug_logger.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S"
        ),
    )
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"),
    )
    debug_logger.addHandler(stream_handler)
    debug_logger.addHandler(file_handler)
    debug_logger.info("Debug logging enabled, writing to %s", log_path)

    def _stdlib_hook(event: ProviderLogEvent) -> None:
        match event.phase:
            case "start" | "retry":
                debug_logger.debug("[%s] %s", event.provider.value, event.message)
            case "success":
                debug_logger.info(
                    "[%s] %s (latency=%.0fms)",
                    event.provider.value,
                    event.message,
                    event.latency_ms,
                )
            case "error":
                error_code = event.error_code.value if event.error_code else "unknown"
                debug_logger.warning(
                    "[%s] %s (code=%s, http=%s, latency=%.0fms)",
                    event.provider.value,
                    event.message,
                    error_code,
                    event.http_status,
                    event.latency_ms,
                )

    return _stdlib_hook


async def _async_main(parsed: argparse.Namespace) -> int:
    config = _load_config(parsed.config)
    latitude = cast(
        float,
        _resolve_required(parsed.lat, config.latitude, "lat"),
    )
    longitude = cast(
        float,
        _resolve_required(parsed.lon, config.longitude, "lon"),
    )
    sqlite_value = cast(
        Path | str | None,
        parsed.sqlite if parsed.sqlite is not None else config.sqlite,
    )
    sqlite_path = Path(sqlite_value) if sqlite_value is not None else None
    granularity_values = cast(list[str], parsed.granularity)
    granularity = (
        [Granularity(item) for item in granularity_values]
        if granularity_values
        else config.granularity
    )
    providers = cast(list[ProviderId], parsed.provider) or None
    language = _resolve_optional(cast(str | None, parsed.language), config.language)
    include_raw = cast(bool, parsed.include_raw) or config.include_raw

    log_events: list[ProviderLogEvent] = []
    log_hooks: list[LogHook] = []

    def _collector_hook(event: ProviderLogEvent) -> None:
        log_events.append(event)

    log_hooks.append(_collector_hook)

    debug: bool = cast(bool, parsed.debug) or config.debug
    if debug:
        log_path = (
            sqlite_path.with_suffix(".log")
            if sqlite_path is not None
            else Path("omni-weather.log")
        )
        loguru_hook = _setup_debug_logging(log_path)
        log_hooks.append(loguru_hook)

    raw_archive_path: Path | None = None
    if (
        sqlite_path is not None
        and config.http.raw_archive_enabled
        and not cast(bool, parsed.no_raw_archive)
    ):
        raw_archive_path = _default_raw_archive_path(sqlite_path)
        config.http.raw_archive_path = str(raw_archive_path)

    quota_tracker = SqliteQuotaTracker(sqlite_path) if sqlite_path is not None else None
    async with await create_omni_weather(
        config,
        log_hooks=log_hooks,
        quota_tracker=quota_tracker,
    ) as client:
        timezone: str | None = None
        if sqlite_path is not None:
            timezone_resolution = await resolve_cli_timezone(
                sqlite_path,
                latitude,
                longitude,
                needs_lookup=_cli_needs_timezone_lookup(
                    _selected_provider_ids(config, providers),
                    granularity,
                ),
                client=client,
            )
            timezone = timezone_resolution.timezone
            _print_timezone_warnings(timezone_resolution.warnings)
        request = ForecastRequest(
            latitude=latitude,
            longitude=longitude,
            granularity=granularity,
            language=language,
            timezone=timezone,
            include_raw=include_raw,
            providers=providers,
            timeout_ms=_resolve_optional(
                cast(float | None, parsed.timeout_ms),
                config.default_timeout_ms,
            ),
        )
        response = await client.forecast(request)

    run_id: int | None = None
    if sqlite_path is not None:
        # The archive file is created lazily on the first network response;
        # a zero-traffic run leaves the column NULL rather than dangling.
        run_id = save_forecast_response(
            sqlite_path,
            response,
            raw_archive_path=(
                raw_archive_path
                if raw_archive_path is not None and raw_archive_path.exists()
                else None
            ),
        )
        save_provider_logs(sqlite_path, log_events, run_id=run_id)
        _print_timezone_warnings(
            reconcile_cli_timezone(
                sqlite_path,
                latitude,
                longitude,
                response,
            ),
        )

    match cast(str, parsed.output_format):
        case "json":
            print(response.model_dump_json(indent=2))
        case "csv":
            _print_csv(response)
        case "ndjson":
            _print_ndjson(response)
        case _:
            _print_results(response, run_id, sqlite_path)
    return 0 if response.summary.failed == 0 else 1


def _iter_point_rows(response: ForecastResponse) -> Iterator[dict[str, Any]]:
    """Flatten every forecast data point into one row carrying its origin."""

    for result in response.results:
        if not isinstance(result, ProviderSuccess):
            continue
        for forecast in result.forecasts:
            for granularity, points in (
                ("minutely", forecast.minutely),
                ("hourly", forecast.hourly),
                ("daily", forecast.daily),
            ):
                for point in points:
                    yield {
                        "provider": result.provider.value,
                        "model": forecast.source.model,
                        "granularity": granularity,
                        "timezone": forecast.timezone,
                        **point.model_dump(mode="json"),
                    }


def _csv_field_names() -> list[str]:
    names = ["provider", "model", "granularity", "timezone"]
    for model_cls in (WeatherDataPoint, DailyDataPoint, MinutelyDataPoint):
        for field_name in model_cls.model_fields:
            if field_name not in names:
                names.append(field_name)
    return names


def _print_csv(response: ForecastResponse) -> None:
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=_csv_field_names(),
        restval="",
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _iter_point_rows(response):
        writer.writerow(row)

    alert_count = sum(
        len(forecast.alerts)
        for result in response.results
        if isinstance(result, ProviderSuccess)
        for forecast in result.forecasts
    )
    if alert_count:
        print(
            f"note: {alert_count} alert(s) omitted from CSV output; "
            "use --format ndjson to include them",
            file=sys.stderr,
        )
    for result in response.results:
        if isinstance(result, ProviderError):
            print(
                f"provider {result.provider.value} failed: "
                f"{result.error.code.value}: {result.error.message}",
                file=sys.stderr,
            )


def _print_ndjson(response: ForecastResponse) -> None:
    for row in _iter_point_rows(response):
        print(json.dumps({"type": "forecast_point", **row}, separators=(",", ":")))
    for result in response.results:
        match result:
            case ProviderSuccess():
                for forecast in result.forecasts:
                    for alert in forecast.alerts:
                        print(
                            json.dumps(
                                {
                                    "type": "alert",
                                    "provider": result.provider.value,
                                    "model": forecast.source.model,
                                    "timezone": forecast.timezone,
                                    **alert.model_dump(mode="json"),
                                },
                                separators=(",", ":"),
                            )
                        )
            case ProviderError():
                print(
                    json.dumps(
                        {
                            "type": "provider_error",
                            "provider": result.provider.value,
                            "code": result.error.code.value,
                            "message": result.error.message,
                            "http_status": result.error.http_status,
                            "latency_ms": result.error.latency_ms,
                        },
                        separators=(",", ":"),
                    )
                )


def _print_results(
    response: ForecastResponse,
    run_id: int | None,
    sqlite_path: Path | None,
) -> None:
    try:
        console_cls = importlib.import_module("rich.console").Console
        table_cls = importlib.import_module("rich.table").Table
        text_cls = importlib.import_module("rich.text").Text
    except ImportError:
        _print_results_plain(response, run_id, sqlite_path)
        return

    console = console_cls()
    summary = response.summary

    title_prefix = f"Run {run_id} — " if run_id is not None else ""
    caption = (
        f"Saved to {sqlite_path} in {response.total_latency_ms:.0f}ms"
        if sqlite_path is not None
        else f"Completed in {response.total_latency_ms:.0f}ms (not persisted)"
    )
    table = table_cls(
        title=f"{title_prefix}{summary.succeeded}/{summary.total} succeeded",
        caption=caption,
    )
    table.add_column("Provider", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")
    table.add_column("Hourly", justify="right")
    table.add_column("Daily", justify="right")
    table.add_column("Minutely", justify="right")
    table.add_column("Alerts", justify="right")
    table.add_column("Detail")

    for result in response.results:
        match result:
            case ProviderSuccess():
                hourly = daily = minutely = alerts = 0
                for forecast in result.forecasts:
                    hourly += len(forecast.hourly)
                    daily += len(forecast.daily)
                    minutely += len(forecast.minutely)
                    alerts += len(forecast.alerts)
                table.add_row(
                    result.provider.value,
                    text_cls("OK", style="green bold"),
                    f"{result.latency_ms:.0f}ms",
                    str(hourly),
                    str(daily),
                    str(minutely),
                    str(alerts) if alerts else "-",
                    f"{len(result.forecasts)} source(s)",
                )
            case ProviderError():
                table.add_row(
                    result.provider.value,
                    text_cls("FAIL", style="red bold"),
                    f"{result.error.latency_ms:.0f}ms",
                    "-",
                    "-",
                    "-",
                    "-",
                    text_cls(result.error.message, style="red"),
                )

    console.print(table)


def _print_results_plain(
    response: ForecastResponse,
    run_id: int | None,
    sqlite_path: Path | None,
) -> None:
    summary = response.summary
    run_prefix = f"Run {run_id}: " if run_id is not None else ""
    print(
        f"{run_prefix}{summary.succeeded}/{summary.total} succeeded "
        f"in {response.total_latency_ms:.0f}ms",
    )
    if sqlite_path is not None:
        print(f"Saved to {sqlite_path}")
    for result in response.results:
        match result:
            case ProviderSuccess():
                hourly = daily = minutely = alerts = 0
                for forecast in result.forecasts:
                    hourly += len(forecast.hourly)
                    daily += len(forecast.daily)
                    minutely += len(forecast.minutely)
                    alerts += len(forecast.alerts)
                print(
                    f"{result.provider.value}: ok "
                    f"latency={result.latency_ms:.0f}ms "
                    f"hourly={hourly} daily={daily} minutely={minutely} "
                    f"alerts={alerts}",
                )
            case ProviderError():
                print(
                    f"{result.provider.value}: fail "
                    f"latency={result.error.latency_ms:.0f}ms "
                    f"message={result.error.message}",
                )


def _load_config(path: Path) -> OmniWeatherConfig:
    with path.open("rb") as file_pointer:
        raw_config = tomllib.load(file_pointer)
    return OmniWeatherConfig.model_validate(raw_config)
