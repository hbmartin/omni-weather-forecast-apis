from __future__ import annotations

import argparse
import asyncio
import sys
import tomllib
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from omni_weather_forecast_apis.client import create_omni_weather
from omni_weather_forecast_apis.sqlite_store import (
    save_forecast_response,
    save_provider_logs,
)
from omni_weather_forecast_apis.types import (
    ForecastRequest,
    Granularity,
    LogHook,
    OmniWeatherConfig,
    ProviderError,
    ProviderId,
    ProviderLogEvent,
)


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
        required=True,
        type=Path,
        help="Path to TOML config",
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
        default="en",
        help="Provider language preference",
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
    if (resolved := cli_value or config_value) is not None:
        return resolved
    print(f"error: --{name} is required (via CLI flag or config file)", file=sys.stderr)
    sys.exit(2)


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
        cast(str, _resolve_required(parsed.sqlite, config.sqlite, "sqlite")),
    )
    granularity_values = cast(list[str], parsed.granularity)
    granularity = (
        [Granularity(item) for item in granularity_values]
        if granularity_values
        else [Granularity.HOURLY, Granularity.DAILY]
    )
    providers = cast(list[ProviderId], parsed.provider) or None
    request = ForecastRequest(
        latitude=latitude,
        longitude=longitude,
        granularity=granularity,
        language=cast(str, parsed.language),
        include_raw=cast(bool, parsed.include_raw),
        providers=providers,
        timeout_ms=cast(float | None, parsed.timeout_ms),
    )

    log_events: list[ProviderLogEvent] = []
    log_hooks: list[LogHook] = []

    def _collector_hook(event: ProviderLogEvent) -> None:
        log_events.append(event)

    log_hooks.append(_collector_hook)

    debug: bool = cast(bool, parsed.debug)
    if debug:
        log_path = sqlite_path.with_suffix(".log")
        loguru_hook = _setup_debug_logging(log_path)
        log_hooks.append(loguru_hook)

    async with await create_omni_weather(config, log_hooks=log_hooks) as client:
        response = await client.forecast(request)

    run_id = save_forecast_response(sqlite_path, response)
    save_provider_logs(sqlite_path, log_events, run_id=run_id)

    print(
        (
            f"saved run {run_id} to {sqlite_path} "
            f"({response.summary.succeeded}/{response.summary.total} succeeded)"
        ),
        file=sys.stdout,
    )
    for result in response.results:
        if isinstance(result, ProviderError):
            print(
                f"Provider {result.provider.value} returned error: {result.error.message}",
                file=sys.stderr,
            )
    return 0 if response.summary.failed == 0 else 1


def _load_config(path: Path) -> OmniWeatherConfig:
    with path.open("rb") as file_pointer:
        raw_config = tomllib.load(file_pointer)
    return OmniWeatherConfig.model_validate(raw_config)
