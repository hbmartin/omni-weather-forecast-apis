from __future__ import annotations

import argparse
import asyncio
import sys
import tomllib
from pathlib import Path

from omni_weather_forecast_apis.client import create_omni_weather
from omni_weather_forecast_apis.sqlite_store import save_forecast_response
from omni_weather_forecast_apis.types import (
    ForecastRequest,
    Granularity,
    OmniWeatherConfig,
)


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
        default=10_000,
        help="Per-provider timeout in milliseconds",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the async CLI entrypoint."""

    parsed = build_parser().parse_args(argv)
    return asyncio.run(_async_main(parsed))


async def _async_main(parsed: argparse.Namespace) -> int:
    config = _load_config(parsed.config)
    granularity = (
        [Granularity(item) for item in parsed.granularity]
        if parsed.granularity
        else [Granularity.HOURLY, Granularity.DAILY]
    )
    providers = parsed.provider or None
    async with await create_omni_weather(config) as client:
        response = await client.forecast(
            ForecastRequest(
                latitude=parsed.lat,
                longitude=parsed.lon,
                granularity=granularity,
                language=parsed.language,
                include_raw=parsed.include_raw,
                timeout_ms=parsed.timeout_ms,
                providers=providers,
            ),
        )
    run_id = save_forecast_response(parsed.sqlite, response)
    print(
        (
            f"saved run {run_id} to {parsed.sqlite} "
            f"({response.summary.succeeded}/{response.summary.total} succeeded)"
        ),
        file=sys.stdout,
    )
    return 0 if response.summary.failed == 0 else 1


def _load_config(path: Path) -> OmniWeatherConfig:
    with path.open("rb") as file_pointer:
        raw_config = tomllib.load(file_pointer)
    return OmniWeatherConfig.model_validate(raw_config)
