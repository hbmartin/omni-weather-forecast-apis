"""CLI entry point for omni-weather-forecast-apis."""

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

from omni_weather_forecast_apis.client import OmniWeatherClient
from omni_weather_forecast_apis.types.config import (
    OmniWeatherConfig,
    ProviderRegistration,
    RateLimitConfig,
)
from omni_weather_forecast_apis.types.schema import (
    ForecastRequest,
    ForecastResponse,
    Granularity,
    ProviderId,
    ProviderSuccess,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni-weather",
        description="Fetch weather forecasts from multiple providers.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to JSON configuration file.",
    )
    parser.add_argument(
        "--lat",
        type=float,
        required=True,
        help="Latitude in decimal degrees.",
    )
    parser.add_argument(
        "--lon",
        type=float,
        required=True,
        help="Longitude in decimal degrees.",
    )
    parser.add_argument(
        "--granularity",
        nargs="+",
        choices=["minutely", "hourly", "daily"],
        default=["hourly", "daily"],
        help="Granularities to request (default: hourly daily).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to SQLite database for saving results.",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include raw API responses in output.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10000,
        help="Timeout per provider in milliseconds (default: 10000).",
    )
    parser.add_argument(
        "--providers",
        nargs="*",
        help="Only fetch from these providers (space-separated IDs).",
    )
    return parser


def load_config(config_path: Path) -> OmniWeatherConfig:
    """Load OmniWeatherConfig from a JSON file."""
    with config_path.open() as f:
        raw = json.load(f)

    providers = [ProviderRegistration(**p) for p in raw.get("providers", [])]
    rate_limiting = RateLimitConfig(**raw.get("rate_limiting", {}))
    default_timeout_ms = raw.get("default_timeout_ms", 10_000)

    return OmniWeatherConfig(
        providers=providers,
        rate_limiting=rate_limiting,
        default_timeout_ms=default_timeout_ms,
    )


def save_to_sqlite(db_path: Path, response: ForecastResponse) -> None:
    """Save forecast response to a SQLite database."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS forecast_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                granularity TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                total_latency_ms REAL NOT NULL,
                total_providers INTEGER NOT NULL,
                succeeded INTEGER NOT NULL,
                failed INTEGER NOT NULL,
                response_json TEXT NOT NULL
            )""")
        conn.execute(
            """INSERT INTO forecast_runs
                (latitude, longitude, granularity, completed_at,
                 total_latency_ms, total_providers, succeeded, failed,
                 response_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                response.request.latitude,
                response.request.longitude,
                json.dumps([g.value for g in response.request.granularity]),
                response.completed_at.isoformat(),
                response.total_latency_ms,
                response.summary.total,
                response.summary.succeeded,
                response.summary.failed,
                response.model_dump_json(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def async_main(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    granularity = [Granularity(g) for g in args.granularity]
    providers = [ProviderId(p) for p in args.providers] if args.providers else None

    request = ForecastRequest(
        latitude=args.lat,
        longitude=args.lon,
        granularity=granularity,
        include_raw=args.include_raw,
        timeout_ms=args.timeout,
        providers=providers,
    )

    async with OmniWeatherClient(config) as client:
        response = await client.forecast(request)

    print(
        f"{response.summary.succeeded}/{response.summary.total} "
        f"providers succeeded in {response.total_latency_ms:.0f}ms",
    )

    for result in response.results:
        if isinstance(result, ProviderSuccess):
            for forecast in result.forecasts:
                print(
                    f"  [{forecast.source.provider.value}/{forecast.source.model}]"
                    f" {len(forecast.hourly)} hourly,"
                    f" {len(forecast.daily)} daily points",
                )
        else:
            print(
                f"  [{result.provider.value}] FAILED:"
                f" {result.error.code.value} — {result.error.message}",
            )

    if args.output:
        save_to_sqlite(args.output, response)
        print(f"Results saved to {args.output}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
