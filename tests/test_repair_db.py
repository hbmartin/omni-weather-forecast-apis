from __future__ import annotations

import sqlite3
from pathlib import Path

from omni_weather_forecast_apis.sqlite_store import _create_schema
from scripts import repair_db


def test_repairs_create_unique_readable_backups_with_wal_data(tmp_path: Path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
        _create_schema(connection)
        connection.execute(
            """
            INSERT INTO forecast_runs (
                latitude, longitude, granularity, language, completed_at,
                total_latency_ms, total_results, succeeded, failed
            ) VALUES (34.0, -118.0, '[]', 'en', '2026-01-01T00:00:00Z',
                      1.0, 0, 0, 0)
            """,
        )
        connection.commit()
        assert database_path.with_name(f"{database_path.name}-wal").exists()

        assert repair_db.main([str(database_path), "--dry-run"]) == 0
        assert repair_db.main([str(database_path)]) == 0
    finally:
        connection.close()

    backups = sorted(tmp_path.glob("forecast.pre-repair-*.sqlite"))
    assert len(backups) == 2
    for backup in backups:
        backup_connection = sqlite3.connect(backup)
        try:
            integrity = backup_connection.execute("PRAGMA integrity_check").fetchone()
            run = backup_connection.execute(
                "SELECT latitude, longitude FROM forecast_runs",
            ).fetchone()
            schema_version = backup_connection.execute(
                "SELECT schema_version FROM schema_metadata WHERE id = 1",
            ).fetchone()
        finally:
            backup_connection.close()
        assert integrity == ("ok",)
        assert run == (34.0, -118.0)
        assert schema_version == (2,)


def test_meteosource_daily_repair_preserves_ambiguous_condition() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        repairer = repair_db.Repairer(connection)
        condition = repairer._recomputed_daily_condition(
            "meteosource",
            "thunderstorm",
            None,
        )
    finally:
        connection.close()

    assert condition == "thunderstorm"
