from __future__ import annotations

import argparse
import asyncio
import sys
import tomllib
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from omni_weather_forecast_apis.client import create_omni_weather
from omni_weather_forecast_apis.sqlite_store import save_forecast_response
from omni_weather_forecast_apis.types import (
    ForecastRequest,
    Granularity,
    OmniWeatherConfig,
    ProviderId,
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
        required=True,
        type=float,
        help="Latitude in decimal degrees",
    )
    parser.add_argument(
        "--lon",
        required=True,
        type=float,
        help="Longitude in decimal degrees",
    )
    parser.add_argument(
        "--sqlite",
        required=True,
        type=Path,
        help="Path to the SQLite database output file",
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
        help="Override per-provider timeout in milliseconds",
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


async def _async_main(parsed: argparse.Namespace) -> int:
    config = _load_config(parsed.config)
    granularity_values = cast(list[str], parsed.granularity)
    granularity = (
        [Granularity(item) for item in granularity_values]
        if granularity_values
        else [Granularity.HOURLY, Granularity.DAILY]
    )
    providers = cast(list[ProviderId], parsed.provider) or None
    request = ForecastRequest(
        latitude=cast(float, parsed.lat),
        longitude=cast(float, parsed.lon),
        granularity=granularity,
        language=cast(str, parsed.language),
        include_raw=cast(bool, parsed.include_raw),
        providers=providers,
        timeout_ms=cast(float | None, parsed.timeout_ms),
    )
    async with await create_omni_weather(config) as client:
        response = await client.forecast(request)
    sqlite_path = cast(Path, parsed.sqlite)
    run_id = save_forecast_response(sqlite_path, response)
    print(
        (
            f"saved run {run_id} to {sqlite_path} "
            f"({response.summary.succeeded}/{response.summary.total} succeeded)"
        ),
        file=sys.stdout,
    )
    return 0 if response.summary.failed == 0 else 1


def _load_config(path: Path) -> OmniWeatherConfig:
    with path.open("rb") as file_pointer:
        raw_config = tomllib.load(file_pointer)
    return OmniWeatherConfig.model_validate(raw_config)
