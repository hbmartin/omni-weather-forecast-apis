"""Follow-up repair for databases already repaired by ``repair_db.py`` v1.

This script assumes the v1 repair completed successfully. It only repairs the
later Weatherbit snow/rain findings and Pirate Weather daily precipitation.

Usage: uv run scripts/repair_db_v2.py <database.sqlite> [--dry-run]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_VERSION = "2.0"


class RepairConflictError(RuntimeError):
    """A corrected destination already contains a different value."""


class Repairer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.actions: list[tuple[str, int]] = []

    def record(self, action: str, rows: int) -> None:
        self.actions.append((action, rows))
        print(f"  {action}: {rows} rows")

    def execute(self, action: str, sql: str) -> None:
        cursor = self.connection.execute(sql)
        self.record(action, cursor.rowcount)

    def assert_no_snow_conflicts(self) -> None:
        checks = (
            (
                "Weatherbit hourly snow",
                """
                SELECT COUNT(*)
                FROM hourly_points hp
                JOIN source_forecasts sf ON hp.source_forecast_id = sf.id
                WHERE sf.provider = 'weatherbit'
                  AND hp.snow IS NOT NULL
                  AND hp.snowfall_depth IS NOT NULL
                  AND hp.snowfall_depth <> hp.snow
                """,
            ),
            (
                "Weatherbit daily snow",
                """
                SELECT COUNT(*)
                FROM daily_points dp
                JOIN source_forecasts sf ON dp.source_forecast_id = sf.id
                WHERE sf.provider = 'weatherbit'
                  AND dp.snowfall_sum IS NOT NULL
                  AND dp.snowfall_depth_sum IS NOT NULL
                  AND dp.snowfall_depth_sum <> dp.snowfall_sum
                """,
            ),
        )
        conflicts = []
        for label, sql in checks:
            row = self.connection.execute(sql).fetchone()
            count = int(row[0]) if row is not None else 0
            if count:
                conflicts.append(f"{label}: {count} row(s)")
        if conflicts:
            details = "; ".join(conflicts)
            raise RepairConflictError(
                f"conflicting corrected snow values ({details})",
            )

    def repair_weatherbit(self) -> None:
        self.execute(
            "move Weatherbit hourly snow depth to snowfall_depth",
            """
            UPDATE hourly_points
            SET snowfall_depth = snow,
                snow = NULL
            WHERE snow IS NOT NULL
              AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'weatherbit'
              )
            """,
        )
        self.execute(
            "move Weatherbit daily snow depth to snowfall_depth_sum",
            """
            UPDATE daily_points
            SET snowfall_depth_sum = snowfall_sum,
                snowfall_sum = NULL
            WHERE snowfall_sum IS NOT NULL
              AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'weatherbit'
              )
            """,
        )
        self.execute(
            "clear Weatherbit hourly rain copied from generic precipitation",
            """
            UPDATE hourly_points
            SET rain = CASE WHEN rain = 0 THEN 0 END
            WHERE rain IS NOT NULL
              AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'weatherbit'
              )
            """,
        )
        self.execute(
            "clear Weatherbit daily rain copied from generic precipitation",
            """
            UPDATE daily_points
            SET rain_sum = CASE WHEN rain_sum = 0 THEN 0 END
            WHERE rain_sum IS NOT NULL
              AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'weatherbit'
              )
            """,
        )

    def repair_pirate_weather_daily(self) -> None:
        self.execute(
            "clear ambiguous Pirate Weather daily precipitation (keep zeros)",
            """
            UPDATE daily_points
            SET precipitation_sum = CASE WHEN precipitation_sum = 0 THEN 0 END
            WHERE precipitation_sum IS NOT NULL
              AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'pirate_weather'
              )
            """,
        )

    def log_actions(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS db_repairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_version TEXT NOT NULL,
                action TEXT NOT NULL,
                rows_affected INTEGER NOT NULL,
                executed_at TEXT NOT NULL
            )
            """,
        )
        now = datetime.now(tz=UTC).isoformat()
        self.connection.executemany(
            """
            INSERT INTO db_repairs (
                script_version, action, rows_affected, executed_at
            ) VALUES (?, ?, ?, ?)
            """,
            [(SCRIPT_VERSION, action, rows, now) for action, rows in self.actions],
        )


def _backup_path(database: Path) -> Path:
    return database.with_name(
        f"{database.stem}.pre-repair-v2-{datetime.now(tz=UTC):%Y%m%dT%H%M%S%fZ}.sqlite",
    )


def _write_backup(database: Path, backup: Path) -> None:
    try:
        with (
            closing(sqlite3.connect(database)) as source,
            closing(sqlite3.connect(backup)) as destination,
        ):
            source.backup(destination)
    except (OSError, sqlite3.Error):
        backup.unlink(missing_ok=True)
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report would-be changes and roll everything back",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    database: Path = arguments.database
    if not database.exists():
        print(f"error: {database} does not exist", file=sys.stderr)
        return 2

    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        if not arguments.dry_run:
            backup = _backup_path(database)
            if backup.exists():
                print(
                    f"error: backup {backup} already exists; aborting",
                    file=sys.stderr,
                )
                return 2
            _write_backup(database, backup)
            print(f"backup written to {backup}")

        repairer = Repairer(connection)
        print("dry run" if arguments.dry_run else "repairing")
        repairer.assert_no_snow_conflicts()
        repairer.repair_weatherbit()
        repairer.repair_pirate_weather_daily()
        if arguments.dry_run:
            connection.rollback()
            print("rolled back (dry run)")
        else:
            repairer.log_actions()
            connection.commit()
            print("committed")
    except (OSError, RepairConflictError, sqlite3.Error) as exc:
        connection.rollback()
        print(f"error: repair aborted: {exc}", file=sys.stderr)
        return 2
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
