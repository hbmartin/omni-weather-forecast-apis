from __future__ import annotations

import sqlite3

from scripts import inspect_db


def test_partial_schema_reports_skipped_checks_without_crashing(tmp_path) -> None:
    database_path = tmp_path / "partial.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE hourly_points (temperature REAL)")
        connection.commit()
    finally:
        connection.close()

    connection = sqlite3.connect(database_path)
    try:
        failures = inspect_db._sanity_failures(connection)
    finally:
        connection.close()

    assert failures
    assert any("skipped: missing source_forecasts table" in item for item in failures)
    assert any("daily_points table" in item for item in failures)


def test_main_handles_empty_database_as_failed_inspection(tmp_path, capsys) -> None:
    database_path = tmp_path / "empty.sqlite"
    sqlite3.connect(database_path).close()

    assert inspect_db.main([str(database_path)]) == 1

    output = capsys.readouterr().out
    assert "unavailable: missing forecast_runs table" in output
    assert "FAIL: hourly bounds skipped: missing hourly_points table" in output
