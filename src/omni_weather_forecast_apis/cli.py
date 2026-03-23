from __future__ import annotations

import argparse
import asyncio
import sys
import tomllib
from pathlib import Path
from typing import TypeVar, cast

from pydantic import ValidationError

from omni_weather_forecast_apis.client import create_omni_weather
from omni_weather_forecast_apis.sqlite_store import (
    save_forecast_response,
    save_provider_logs,
)
from omni_weather_forecast_apis.types import (
    ForecastRequest,
    ForecastResponse,
    Granularity,
    LogHook,
    OmniWeatherConfig,
    ProviderError,
    ProviderId,
    ProviderLogEvent,
    ProviderSuccess,
)

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
        default=Path.home() / ".config" / "omni_weather_forecast_apis.toml",
        help="Path to TOML config (default: ~/.config/omni_weather_forecast_apis.toml)",
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
        help="Path to the SQLite database output file (overrides config)",
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
        "--timeout-ms",
        type=float,
        default=None,
        help="Override the default request timeout in milliseconds",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug output and write a log file next to the SQLite database",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the async CLI entrypoint."""

    parsed = build_parser().parse_args(argv)
    try:
        return asyncio.run(_async_main(parsed))
    except (
        FileNotFoundError,
        OSError,
        tomllib.TOMLDecodeError,
        ValidationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _resolve_required(
    cli_value: object, config_value: object, name: str,
) -> object:
    resolved = cli_value if cli_value is not None else config_value
    if resolved is not None:
        return resolved
    print(f"error: --{name} is required (via CLI flag or config file)", file=sys.stderr)
    sys.exit(2)


def _resolve_optional(cli_value: T | None, config_value: T) -> T:
    return cli_value if cli_value is not None else config_value


def _setup_debug_logging(log_path: Path) -> LogHook:
    """Configure loguru for debug output to stderr and a log file.

    Returns a LogHook callback that logs ProviderLogEvents via loguru.
    """
    from loguru import logger  # noqa: PLC0415

    logger.remove()
    logger.add(sys.stderr, level="DEBUG", format="{time:HH:mm:ss} | {level:<7} | {message}")
    logger.add(
        str(log_path),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}",
        rotation="10 MB",
    )
    logger.info("Debug logging enabled, writing to {}", log_path)

    def _loguru_hook(event: ProviderLogEvent) -> None:
        match event.phase:
            case "start":
                logger.debug("[{}] {}", event.provider.value, event.message)
            case "success":
                logger.info(
                    "[{}] {} (latency={:.0f}ms)",
                    event.provider.value,
                    event.message,
                    event.latency_ms,
                )
            case "error":
                logger.warning(
                    "[{}] {} (code={}, http={}, latency={:.0f}ms)",
                    event.provider.value,
                    event.message,
                    event.error_code.value if event.error_code else "unknown",
                    event.http_status,
                    event.latency_ms,
                )

    return _loguru_hook


async def _async_main(parsed: argparse.Namespace) -> int:
    config = _load_config(parsed.config)
    latitude = cast(
        float, _resolve_required(parsed.lat, config.latitude, "lat"),
    )
    longitude = cast(
        float, _resolve_required(parsed.lon, config.longitude, "lon"),
    )
    sqlite_path = Path(
        cast(str | Path, _resolve_required(parsed.sqlite, config.sqlite, "sqlite")),
    )
    granularity_values = cast(list[str], parsed.granularity)
    granularity = (
        [Granularity(item) for item in granularity_values]
        if granularity_values
        else config.granularity
    )
    providers = cast(list[ProviderId], parsed.provider) or None
    language = _resolve_optional(cast(str | None, parsed.language), config.language)
    include_raw = cast(bool, parsed.include_raw) or config.include_raw
    request = ForecastRequest(
        latitude=latitude,
        longitude=longitude,
        granularity=granularity,
        language=language,
        include_raw=include_raw,
        providers=providers,
        timeout_ms=_resolve_optional(
            cast(float | None, parsed.timeout_ms),
            config.default_timeout_ms,
        ),
    )

    log_events: list[ProviderLogEvent] = []
    log_hooks: list[LogHook] = []

    def _collector_hook(event: ProviderLogEvent) -> None:
        log_events.append(event)

    log_hooks.append(_collector_hook)

    debug: bool = cast(bool, parsed.debug) or config.debug
    if debug:
        log_path = sqlite_path.with_suffix(".log")
        loguru_hook = _setup_debug_logging(log_path)
        log_hooks.append(loguru_hook)

    async with await create_omni_weather(config, log_hooks=log_hooks) as client:
        response = await client.forecast(request)

    run_id = save_forecast_response(sqlite_path, response)
    save_provider_logs(sqlite_path, log_events, run_id=run_id)

    _print_results(response, run_id, sqlite_path)
    return 0 if response.summary.failed == 0 else 1


def _print_results(
    response: ForecastResponse, run_id: int, sqlite_path: Path,
) -> None:
    try:
        from rich.console import Console  # noqa: PLC0415
        from rich.table import Table  # noqa: PLC0415
        from rich.text import Text  # noqa: PLC0415
    except ImportError:
        _print_results_plain(response, run_id, sqlite_path)
        return

    console = Console()
    summary = response.summary

    table = Table(
        title=f"Run {run_id} — {summary.succeeded}/{summary.total} succeeded",
        caption=f"Saved to {sqlite_path} in {response.total_latency_ms:.0f}ms",
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
                    Text("OK", style="green bold"),
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
                    Text("FAIL", style="red bold"),
                    f"{result.error.latency_ms:.0f}ms",
                    "-",
                    "-",
                    "-",
                    "-",
                    Text(result.error.message, style="red"),
                )

    console.print(table)


def _print_results_plain(
    response: ForecastResponse, run_id: int, sqlite_path: Path,
) -> None:
    summary = response.summary
    print(
        f"Run {run_id}: {summary.succeeded}/{summary.total} succeeded "
        f"in {response.total_latency_ms:.0f}ms",
    )
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
