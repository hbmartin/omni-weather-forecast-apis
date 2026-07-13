"""Inspect an omni-weather forecast SQLite database.

Prints run/provider/row summaries, per-provider column statistics, and a
set of data-quality sanity checks. Exits 1 when any sanity check fails so
the script can gate automation.

Usage: uv run python scripts/inspect_db.py <database.sqlite>
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from omni_weather_forecast_apis.types import WeatherCondition

_HOURLY_STAT_COLUMNS = (
    "temperature",
    "apparent_temperature",
    "dew_point",
    "humidity",
    "wind_speed",
    "wind_gust",
    "pressure_sea",
    "precipitation",
    "precipitation_probability",
    "rain",
    "snow",
    "snowfall_depth",
    "cloud_cover",
    "visibility",
    "uv_index",
    "solar_radiation_ghi",
    "solar_radiation_dni",
    "solar_radiation_dhi",
)

# Plausible physical bounds per column (inclusive), used by sanity checks.
_HOURLY_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature": (-60.0, 60.0),
    "apparent_temperature": (-80.0, 70.0),
    "dew_point": (-70.0, 40.0),
    "humidity": (0.0, 100.0),
    "wind_speed": (0.0, 120.0),
    "wind_gust": (0.0, 150.0),
    "pressure_sea": (850.0, 1100.0),
    "precipitation": (0.0, 500.0),
    "precipitation_probability": (0.0, 1.0),
    "cloud_cover": (0.0, 100.0),
    "visibility": (0.0, 500.0),
    "uv_index": (0.0, 20.0),
    "solar_radiation_ghi": (0.0, 1500.0),
    "solar_radiation_dni": (0.0, 1500.0),
}


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _print_runs(connection: sqlite3.Connection) -> None:
    print("== Runs ==")
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(forecast_runs)")
    }
    extra = (
        ", raw_archive_path, app_version"
        if {"raw_archive_path", "app_version"} <= columns
        else ""
    )
    for row in connection.execute(
        f"SELECT id, completed_at, total_results, succeeded, failed{extra} "
        "FROM forecast_runs ORDER BY id",
    ):
        print(f"  run {row[0]}: {row[1]} results={row[2]} ok={row[3]} fail={row[4]}", end="")
        if extra:
            print(f" archive={row[5] or '-'} version={row[6] or '-'}", end="")
        print()


def _print_provider_results(connection: sqlite3.Connection) -> None:
    print("== Provider results ==")
    for provider, status, count in connection.execute(
        "SELECT provider, status, COUNT(*) FROM provider_results "
        "GROUP BY provider, status ORDER BY provider",
    ):
        print(f"  {provider}: {status} x{count}")


def _print_row_counts(connection: sqlite3.Connection) -> None:
    print("== Row counts ==")
    for table in (
        "source_forecasts",
        "minutely_points",
        "hourly_points",
        "daily_points",
        "alerts",
        "provider_logs",
    ):
        if not _table_exists(connection, table):
            continue
        (count,) = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        print(f"  {table}: {count}")


def _print_hourly_stats(connection: sqlite3.Connection) -> None:
    print("== Hourly column stats (per provider: min..max, null%) ==")
    present = {
        row[1] for row in connection.execute("PRAGMA table_info(hourly_points)")
    }
    providers = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT provider FROM source_forecasts ORDER BY provider",
        )
    ]
    for provider in providers:
        print(f"  [{provider}]")
        for column in _HOURLY_STAT_COLUMNS:
            if column not in present:
                continue
            row = connection.execute(
                f"""
                SELECT MIN(hp.{column}), MAX(hp.{column}),
                       SUM(hp.{column} IS NULL), COUNT(*)
                FROM hourly_points hp
                JOIN source_forecasts sf ON hp.source_forecast_id = sf.id
                WHERE sf.provider = ?
                """,
                (provider,),
            ).fetchone()
            minimum, maximum, nulls, total = row
            if total == 0:
                continue
            null_pct = 100.0 * (nulls or 0) / total
            if minimum is None:
                print(f"    {column:<28} all NULL")
            else:
                print(
                    f"    {column:<28} {minimum:>10.3f} .. {maximum:>10.3f}"
                    f"  null {null_pct:.0f}%",
                )


def _sanity_failures(connection: sqlite3.Connection) -> list[str]:
    failures: list[str] = []

    for column, (low, high) in _HOURLY_BOUNDS.items():
        rows = connection.execute(
            f"""
            SELECT sf.provider, COUNT(*)
            FROM hourly_points hp
            JOIN source_forecasts sf ON hp.source_forecast_id = sf.id
            WHERE hp.{column} IS NOT NULL AND (hp.{column} < ? OR hp.{column} > ?)
            GROUP BY sf.provider
            """,
            (low, high),
        ).fetchall()
        failures.extend(
            f"hourly {column} out of [{low}, {high}] for {provider}: {count} rows"
            for provider, count in rows
        )

    rows = connection.execute(
        """
        SELECT sf.provider, COUNT(*)
        FROM daily_points dp
        JOIN source_forecasts sf ON dp.source_forecast_id = sf.id
        WHERE dp.precipitation_probability_max IS NOT NULL
          AND (dp.precipitation_probability_max < 0
               OR dp.precipitation_probability_max > 1)
        GROUP BY sf.provider
        """,
    ).fetchall()
    failures.extend(
        f"daily precipitation_probability_max out of [0, 1] for {provider}: "
        f"{count} rows"
        for provider, count in rows
    )

    known_conditions = {item.value for item in WeatherCondition}
    for table, column in (("hourly_points", "condition"), ("daily_points", "condition")):
        rows = connection.execute(
            f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL",
        ).fetchall()
        failures.extend(
            f"{table}.{column} outside vocabulary: {value!r}"
            for (value,) in rows
            if value not in known_conditions
        )

    rows = connection.execute(
        """
        SELECT source_forecast_id, COUNT(*)
        FROM (
            SELECT source_forecast_id, timestamp_unix,
                   LAG(timestamp_unix) OVER (
                       PARTITION BY source_forecast_id ORDER BY rowid
                   ) AS previous_unix
            FROM hourly_points
        )
        WHERE previous_unix IS NOT NULL AND timestamp_unix <= previous_unix
        GROUP BY source_forecast_id
        """,
    ).fetchall()
    failures.extend(
        f"hourly timestamps not strictly increasing for source {source_id}: "
        f"{count} rows"
        for source_id, count in rows
    )

    provider_result_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(provider_results)")
    }
    hourly_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(hourly_points)")
    }
    if "fetched_at_unix" in provider_result_columns and "horizon_hours" in hourly_columns:
        rows = connection.execute(
            """
            SELECT sf.provider, COUNT(*)
            FROM hourly_points hp
            JOIN source_forecasts sf ON hp.source_forecast_id = sf.id
            JOIN provider_results pr ON sf.provider_result_id = pr.id
            WHERE hp.horizon_hours IS NOT NULL
              AND pr.fetched_at_unix IS NOT NULL
              AND ABS(hp.horizon_hours
                      - (hp.timestamp_unix - pr.fetched_at_unix) / 3600.0) > 1e-6
            GROUP BY sf.provider
            """,
        ).fetchall()
        failures.extend(
            f"horizon_hours inconsistent with timestamps for {provider}: {count} rows"
            for provider, count in rows
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()

    if not arguments.database.exists():
        print(f"error: {arguments.database} does not exist", file=sys.stderr)
        return 2

    connection = sqlite3.connect(arguments.database)
    try:
        _print_runs(connection)
        _print_provider_results(connection)
        _print_row_counts(connection)
        _print_hourly_stats(connection)
        failures = _sanity_failures(connection)
    finally:
        connection.close()

    print("== Sanity checks ==")
    if not failures:
        print("  all checks passed")
        return 0
    for failure in failures:
        print(f"  FAIL: {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
