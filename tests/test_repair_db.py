from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

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


def test_write_backup_does_not_replace_existing_file(tmp_path: Path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    sqlite3.connect(database_path).close()
    backup_path = tmp_path / "backup.sqlite"
    backup_path.write_bytes(b"owned by another process")

    with pytest.raises(FileExistsError):
        repair_db._write_backup(database_path, backup_path)

    assert backup_path.read_bytes() == b"owned by another process"


def test_write_backup_removes_owned_reservation_after_failure(
    tmp_path: Path,
) -> None:
    backup_path = tmp_path / "backup.sqlite"

    with pytest.raises(sqlite3.OperationalError):
        repair_db._write_backup(tmp_path, backup_path)

    assert not backup_path.exists()


def test_main_reports_backup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "forecast.sqlite"
    sqlite3.connect(database_path).close()

    def fail_backup(_database: Path, _backup: Path) -> None:
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(repair_db, "_write_backup", fail_backup)

    assert repair_db.main([str(database_path)]) == 2
    assert "error: backup failed: disk full" in capsys.readouterr().err
