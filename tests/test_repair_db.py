from __future__ import annotations

import sqlite3

from omni_weather_forecast_apis.sqlite_store import _create_schema
from scripts import repair_db


def test_dry_run_creates_backup_before_schema_migration(tmp_path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        _create_schema(connection)
        connection.commit()
    finally:
        connection.close()

    assert repair_db.main([str(database_path), "--dry-run"]) == 0

    backups = list(tmp_path.glob("forecast.pre-repair-*.sqlite"))
    assert len(backups) == 1
    assert backups[0].stat().st_size > 0
