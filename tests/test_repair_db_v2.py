from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts import repair_db_v2


def _create_database(path: Path, *, conflict: bool = False) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE source_forecasts (
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL
            );
            CREATE TABLE hourly_points (
                source_forecast_id INTEGER NOT NULL,
                rain REAL,
                snow REAL,
                snowfall_depth REAL
            );
            CREATE TABLE daily_points (
                source_forecast_id INTEGER NOT NULL,
                precipitation_sum REAL,
                rain_sum REAL,
                snowfall_sum REAL,
                snowfall_depth_sum REAL
            );
            INSERT INTO source_forecasts VALUES (1, 'weatherbit');
            INSERT INTO source_forecasts VALUES (2, 'pirate_weather');
            """,
        )
        connection.executemany(
            """
            INSERT INTO hourly_points (
                source_forecast_id, rain, snow, snowfall_depth
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (1, 2.0, 5.0, 6.0 if conflict else None),
                (1, 0.0, 3.0, 3.0),
            ],
        )
        connection.executemany(
            """
            INSERT INTO daily_points (
                source_forecast_id, precipitation_sum, rain_sum,
                snowfall_sum, snowfall_depth_sum
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, 2.0, 2.0, 4.0, None),
                (2, 2.0, 9.0, None, None),
                (2, 0.0, 0.0, None, None),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_repair_moves_weatherbit_values_and_clears_ambiguous_amounts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "forecast.sqlite"
    _create_database(database_path)

    wal_connection = sqlite3.connect(database_path)
    try:
        assert wal_connection.execute("PRAGMA journal_mode = WAL").fetchone() == (
            "wal",
        )
        wal_connection.execute("INSERT INTO source_forecasts VALUES (3, 'sentinel')")
        wal_connection.commit()
        assert database_path.with_name(f"{database_path.name}-wal").exists()

        assert repair_db_v2.main([str(database_path)]) == 0
    finally:
        wal_connection.close()

    connection = sqlite3.connect(database_path)
    try:
        hourly = connection.execute(
            "SELECT rain, snow, snowfall_depth FROM hourly_points ORDER BY rowid",
        ).fetchall()
        daily = connection.execute(
            """
            SELECT precipitation_sum, rain_sum, snowfall_sum, snowfall_depth_sum
            FROM daily_points ORDER BY rowid
            """,
        ).fetchall()
        repairs = connection.execute(
            "SELECT script_version, rows_affected FROM db_repairs ORDER BY id",
        ).fetchall()
    finally:
        connection.close()

    assert hourly == [(None, None, 5.0), (0.0, None, 3.0)]
    assert daily == [
        (2.0, None, None, 4.0),
        (None, 9.0, None, None),
        (0.0, 0.0, None, None),
    ]
    assert repairs == [("2.0", 2), ("2.0", 1), ("2.0", 2), ("2.0", 1), ("2.0", 2)]
    backups = list(tmp_path.glob("forecast.pre-repair-v2-*.sqlite"))
    assert len(backups) == 1
    backup_connection = sqlite3.connect(backups[0])
    try:
        integrity = backup_connection.execute("PRAGMA integrity_check").fetchone()
        sentinel = backup_connection.execute(
            "SELECT provider FROM source_forecasts WHERE id = 3",
        ).fetchone()
        original = backup_connection.execute(
            "SELECT rain, snow, snowfall_depth FROM hourly_points ORDER BY rowid LIMIT 1",
        ).fetchone()
    finally:
        backup_connection.close()
    assert integrity == ("ok",)
    assert sentinel == ("sentinel",)
    assert original == (2.0, 5.0, None)


def test_repair_dry_run_rolls_back_without_backup(tmp_path: Path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    _create_database(database_path)

    assert repair_db_v2.main([str(database_path), "--dry-run"]) == 0

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT rain, snow, snowfall_depth FROM hourly_points LIMIT 1",
        ).fetchone()
        repair_table = connection.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name = 'db_repairs'
            """,
        ).fetchone()
    finally:
        connection.close()

    assert row == (2.0, 5.0, None)
    assert repair_table == (0,)
    assert list(tmp_path.glob("*.pre-repair-v2-*.sqlite")) == []


def test_repair_aborts_transaction_on_conflicting_snow_values(
    tmp_path: Path,
    capsys,
) -> None:
    database_path = tmp_path / "forecast.sqlite"
    _create_database(database_path, conflict=True)

    assert repair_db_v2.main([str(database_path)]) == 2

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT rain, snow, snowfall_depth FROM hourly_points LIMIT 1",
        ).fetchone()
    finally:
        connection.close()

    assert row == (2.0, 5.0, 6.0)
    assert "conflicting corrected snow values" in capsys.readouterr().err


def test_write_backup_does_not_replace_existing_file(tmp_path: Path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    sqlite3.connect(database_path).close()
    backup_path = tmp_path / "backup.sqlite"
    backup_path.write_bytes(b"owned by another process")

    with pytest.raises(FileExistsError):
        repair_db_v2._write_backup(database_path, backup_path)

    assert backup_path.read_bytes() == b"owned by another process"


def test_write_backup_removes_owned_reservation_after_failure(
    tmp_path: Path,
) -> None:
    backup_path = tmp_path / "backup.sqlite"

    with pytest.raises(sqlite3.OperationalError):
        repair_db_v2._write_backup(tmp_path, backup_path)

    assert not backup_path.exists()
