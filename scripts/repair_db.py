"""One-shot repair for databases written by pre-fix parsers.

Repairs (see docs/data-corrections.md for the full rationale):

1. Recompute normalized conditions from the stored originals using the
   corrected Meteosource icon table and keyword ordering (text providers:
   nws, weatherapi, visual_crossing, pirate_weather, weatherbit fallback).
2. Move snow depth values into the new ``snowfall_depth`` columns
   (open_meteo values are depth-mm; pirate_weather values are raw cm and
   are multiplied by 10 first) and NULL the liquid ``snow`` fields.
3. NULL pirate_weather ``precipitation``/``rain`` amounts (the old parser
   mixed cm accumulations with mm/h rates; zeros are kept — zero is zero
   in every unit).
4. NULL open_meteo ``solar_radiation_dni`` (the column held horizontal
   direct radiation, recoverable as GHI - DHI, not true DNI).
5. NULL probability values of exactly 1.0 for percent-scale providers
   (the old scaling collapsed raw 1 (1%) and raw 100 into 1.0).
6. NULL weatherapi daily ``apparent_temperature_max/min`` (they were
   copies of the air temperature) and ``visibility_min`` (it held a daily
   average).

Weather Unlocked timestamps were also wrong (local time stored as UTC);
this database has no Weather Unlocked rows, so no shift is implemented.
Repairing another database with Weather Unlocked data requires shifting
hourly timestamps by the location's UTC offset.

Every action is recorded in a ``db_repairs`` table.

Usage: uv run scripts/repair_db.py <database.sqlite> [--dry-run]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from omni_weather_forecast_apis.mapping import WMO_CODE_MAP, condition_from_text
from omni_weather_forecast_apis.plugins.meteosource import condition_from_icon_num
from omni_weather_forecast_apis.sqlite_store import _create_schema
from omni_weather_forecast_apis.types import WeatherCondition

SCRIPT_VERSION = "1.0"

_TEXT_PROVIDERS = ("nws", "weatherapi", "visual_crossing")
_PERCENT_PROVIDERS = (
    "nws",
    "open_meteo",
    "google_weather",
    "meteosource",
    "weatherapi",
    "visual_crossing",
    "tomorrow_io",
    "weatherbit",
    "weather_unlocked",
)

# Frozen copy of the pre-fix keyword table, used to detect rows whose stored
# condition was text-derived (needed where the source code is not stored).
_OLD_KEYWORD_MAP: tuple[tuple[tuple[str, ...], WeatherCondition], ...] = (
    (("tornado",), WeatherCondition.TORNADO),
    (("hurricane", "tropical storm"), WeatherCondition.HURRICANE),
    (("thunder", "lightning"), WeatherCondition.THUNDERSTORM),
    (("freezing rain",), WeatherCondition.FREEZING_RAIN),
    (("drizzle",), WeatherCondition.DRIZZLE),
    (("light rain",), WeatherCondition.LIGHT_RAIN),
    (("heavy rain", "downpour"), WeatherCondition.HEAVY_RAIN),
    (("rain shower", "showers"), WeatherCondition.RAIN),
    (("rain",), WeatherCondition.RAIN),
    (("hail",), WeatherCondition.HAIL),
    (("light snow",), WeatherCondition.LIGHT_SNOW),
    (("heavy snow", "blizzard"), WeatherCondition.HEAVY_SNOW),
    (("snow shower",), WeatherCondition.SNOW),
    (("snow",), WeatherCondition.SNOW),
    (("sleet", "ice pellets"), WeatherCondition.SLEET),
    (("fog",), WeatherCondition.FOG),
    (("smoke",), WeatherCondition.SMOKE),
    (("dust",), WeatherCondition.DUST),
    (("sand",), WeatherCondition.SAND),
    (("haze", "mist"), WeatherCondition.HAZE),
    (("overcast",), WeatherCondition.OVERCAST),
    (("mostly cloudy",), WeatherCondition.MOSTLY_CLOUDY),
    (("partly cloudy", "partly cloud"), WeatherCondition.PARTLY_CLOUDY),
    (("mostly clear",), WeatherCondition.MOSTLY_CLEAR),
    (("clear", "sunny"), WeatherCondition.CLEAR),
)


def _old_condition_from_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip().lower()
    if not normalized:
        return None
    for keywords, condition in _OLD_KEYWORD_MAP:
        if any(keyword in normalized for keyword in keywords):
            return condition.value
    return WeatherCondition.UNKNOWN.value


def _new_condition_from_text(text: str | None) -> str | None:
    condition = condition_from_text(text)
    return condition.value if condition is not None else None


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


class Repairer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.actions: list[tuple[str, int]] = []

    def record(self, action: str, rows: int) -> None:
        self.actions.append((action, rows))
        print(f"  {action}: {rows} rows")

    def execute(self, action: str, sql: str, params: tuple = ()) -> None:
        cursor = self.connection.execute(sql, params)
        self.record(action, cursor.rowcount)

    # -- 1. conditions ----------------------------------------------------

    def repair_hourly_conditions(self) -> None:
        rows = self.connection.execute(
            """
            SELECT hp.rowid, sf.provider, hp.condition, hp.condition_original,
                   hp.condition_code_original
            FROM hourly_points hp
            JOIN source_forecasts sf ON hp.source_forecast_id = sf.id
            WHERE sf.provider IN (
                'nws', 'weatherapi', 'visual_crossing', 'pirate_weather',
                'weatherbit', 'meteosource'
            )
            """,
        ).fetchall()
        updates: list[tuple[str | None, int]] = []
        for rowid, provider, stored, text, code_text in rows:
            new = self._recomputed_hourly_condition(provider, stored, text, code_text)
            if new != stored:
                updates.append((new, rowid))
        self.connection.executemany(
            "UPDATE hourly_points SET condition = ? WHERE rowid = ?",
            updates,
        )
        self.record("recompute hourly conditions", len(updates))

    def _recomputed_hourly_condition(
        self,
        provider: str,
        stored: str | None,
        text: str | None,
        code_text: object,
    ) -> str | None:
        code = _as_int(code_text)
        if provider == "meteosource":
            if (mapped := condition_from_icon_num(code)) is not None:
                return mapped.value
            return _new_condition_from_text(text)
        if provider == "pirate_weather":
            if code is not None:
                mapped_wmo = WMO_CODE_MAP.get(code)
                return mapped_wmo.value if mapped_wmo is not None else stored
            return _new_condition_from_text(text)
        if provider == "weatherbit":
            # The Weatherbit code map is unchanged; only text-derived rows
            # (where the old text mapping produced the stored value) move.
            if stored == _old_condition_from_text(text):
                return _new_condition_from_text(text)
            return stored
        # nws / weatherapi / visual_crossing derive purely from text.
        return _new_condition_from_text(text)

    def repair_daily_conditions(self) -> None:
        rows = self.connection.execute(
            """
            SELECT dp.rowid, sf.provider, dp.condition, dp.summary
            FROM daily_points dp
            JOIN source_forecasts sf ON dp.source_forecast_id = sf.id
            WHERE sf.provider IN (
                'nws', 'weatherapi', 'visual_crossing', 'pirate_weather',
                'weatherbit', 'meteosource'
            )
            """,
        ).fetchall()
        updates: list[tuple[str | None, int]] = []
        for rowid, provider, stored, summary in rows:
            new = self._recomputed_daily_condition(provider, stored, summary)
            if new != stored:
                updates.append((new, rowid))
        self.connection.executemany(
            "UPDATE daily_points SET condition = ? WHERE rowid = ?",
            updates,
        )
        self.record("recompute daily conditions", len(updates))

    def _recomputed_daily_condition(
        self,
        provider: str,
        stored: str | None,
        summary: str | None,
    ) -> str | None:
        if provider in _TEXT_PROVIDERS:
            return _new_condition_from_text(summary)
        # Daily rows store no source code, so only rows provably derived from
        # the old text mapping are touched. Inferring an icon from a normalized
        # condition is ambiguous because multiple icons share conditions.
        if stored is not None and stored == _old_condition_from_text(summary):
            return _new_condition_from_text(summary)
        return stored

    # -- 2/3. snow and pirate precipitation --------------------------------

    def repair_snow_columns(self) -> None:
        self.execute(
            "move open_meteo hourly snow (depth mm) to snowfall_depth",
            """
            UPDATE hourly_points
            SET snowfall_depth = snow, snow = NULL
            WHERE snow IS NOT NULL AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'open_meteo'
            )
            """,
        )
        self.execute(
            "move open_meteo daily snowfall_sum (depth mm) to snowfall_depth_sum",
            """
            UPDATE daily_points
            SET snowfall_depth_sum = snowfall_sum, snowfall_sum = NULL
            WHERE snowfall_sum IS NOT NULL AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'open_meteo'
            )
            """,
        )
        self.execute(
            "move pirate_weather hourly snow (cm) to snowfall_depth (mm)",
            """
            UPDATE hourly_points
            SET snowfall_depth = snow * 10.0, snow = NULL
            WHERE snow IS NOT NULL AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'pirate_weather'
            )
            """,
        )
        self.execute(
            "move pirate_weather daily snowfall_sum (cm) to snowfall_depth_sum (mm)",
            """
            UPDATE daily_points
            SET snowfall_depth_sum = snowfall_sum * 10.0, snowfall_sum = NULL
            WHERE snowfall_sum IS NOT NULL AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'pirate_weather'
            )
            """,
        )
        self.execute(
            "NULL ambiguous pirate_weather precipitation/rain amounts (keep zeros)",
            """
            UPDATE hourly_points
            SET precipitation = CASE WHEN precipitation = 0 THEN 0 END,
                rain = CASE WHEN rain = 0 THEN 0 END
            WHERE (precipitation IS NOT NULL OR rain IS NOT NULL)
              AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'pirate_weather'
            )
            """,
        )

    # -- 4. open_meteo DNI --------------------------------------------------

    def repair_dni(self) -> None:
        self.execute(
            "NULL open_meteo solar_radiation_dni (was horizontal direct)",
            """
            UPDATE hourly_points
            SET solar_radiation_dni = NULL
            WHERE solar_radiation_dni IS NOT NULL AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'open_meteo'
            )
            """,
        )

    # -- 5. ambiguous probabilities ------------------------------------------

    def repair_probabilities(self) -> None:
        placeholders = ",".join("?" for _ in _PERCENT_PROVIDERS)
        for table, column in (
            ("minutely_points", "precipitation_probability"),
            ("hourly_points", "precipitation_probability"),
            ("daily_points", "precipitation_probability_max"),
        ):
            self.execute(
                f"NULL ambiguous {table}.{column} = 1.0 (1% vs 100%)",
                f"""
                UPDATE {table}
                SET {column} = NULL
                WHERE {column} = 1.0 AND source_forecast_id IN (
                    SELECT id FROM source_forecasts
                    WHERE provider IN ({placeholders})
                )
                """,
                tuple(_PERCENT_PROVIDERS),
            )

    # -- 6. weatherapi daily fabrications -------------------------------------

    def repair_weatherapi_daily(self) -> None:
        self.execute(
            "NULL weatherapi fabricated daily feels-like and avg-as-min visibility",
            """
            UPDATE daily_points
            SET apparent_temperature_max = NULL,
                apparent_temperature_min = NULL,
                visibility_min = NULL
            WHERE (apparent_temperature_max IS NOT NULL
                   OR apparent_temperature_min IS NOT NULL
                   OR visibility_min IS NOT NULL)
              AND source_forecast_id IN (
                SELECT id FROM source_forecasts WHERE provider = 'weatherapi'
            )
            """,
        )

    # -- bookkeeping -----------------------------------------------------------

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
            INSERT INTO db_repairs (script_version, action, rows_affected, executed_at)
            VALUES (?, ?, ?, ?)
            """,
            [(SCRIPT_VERSION, action, rows, now) for action, rows in self.actions],
        )


def _backup_path(database: Path) -> Path:
    return database.with_name(
        f"{database.stem}.pre-repair-{datetime.now(tz=UTC):%Y%m%dT%H%M%S%fZ}.sqlite",
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
        backup = _backup_path(database)
        if backup.exists():
            print(f"error: backup {backup} already exists; aborting", file=sys.stderr)
            return 2
        _write_backup(database, backup)
        print(f"backup written to {backup}")

        # Bring the schema current first (adds snowfall_depth columns and
        # refreshes the stacking_features view). executescript() commits the
        # snapshot transaction, so reacquire the write reservation afterward.
        _create_schema(connection)
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")

        repairer = Repairer(connection)
        if arguments.dry_run:
            print(
                "dry run — data changes roll back (schema columns/views may "
                "still be added by the migration step)",
            )
        else:
            print("repairing")
        repairer.repair_hourly_conditions()
        repairer.repair_daily_conditions()
        repairer.repair_snow_columns()
        repairer.repair_dni()
        repairer.repair_probabilities()
        repairer.repair_weatherapi_daily()

        if arguments.dry_run:
            connection.rollback()
            print("rolled back (dry run)")
        else:
            repairer.log_actions()
            connection.commit()
            print("committed")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
