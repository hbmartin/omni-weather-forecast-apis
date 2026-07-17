from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts import inspect_db


def test_partial_schema_reports_skipped_checks_without_crashing(
    tmp_path: Path,
) -> None:
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
    for check in (
        "hourly bounds skipped",
        "daily precipitation probability skipped",
        "hourly_points condition vocabulary skipped",
        "daily_points condition vocabulary skipped",
        "hourly timestamp order skipped",
        "hourly horizon consistency skipped",
    ):
        assert any(check in item for item in failures)


def test_sanity_failures_report_each_offending_data_class() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            CREATE TABLE provider_results (
                id INTEGER PRIMARY KEY,
                fetched_at_unix INTEGER
            );
            CREATE TABLE source_forecasts (
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_result_id INTEGER NOT NULL
            );
            CREATE TABLE hourly_points (
                source_forecast_id INTEGER NOT NULL,
                timestamp_unix INTEGER NOT NULL,
                horizon_hours REAL,
                temperature REAL,
                condition TEXT
            );
            CREATE TABLE daily_points (
                source_forecast_id INTEGER NOT NULL,
                precipitation_probability_max REAL,
                condition TEXT
            );
            INSERT INTO provider_results VALUES (1, 1000);
            INSERT INTO source_forecasts VALUES (1, 'example', 1);
            INSERT INTO hourly_points VALUES (1, 4600, 2.0, 200.0, 'bad-hourly');
            INSERT INTO hourly_points VALUES (1, 3500, NULL, NULL, 'clear');
            INSERT INTO daily_points VALUES (1, 2.0, 'bad-daily');
            """,
        )

        failures = inspect_db._sanity_failures(connection)
    finally:
        connection.close()

    assert any("hourly temperature out of" in item for item in failures)
    assert any(
        "daily precipitation_probability_max out of" in item for item in failures
    )
    assert "hourly_points.condition outside vocabulary: 'bad-hourly'" in failures
    assert "daily_points.condition outside vocabulary: 'bad-daily'" in failures
    assert any("hourly timestamps not strictly increasing" in item for item in failures)
    assert any(
        "horizon_hours inconsistent with timestamps" in item for item in failures
    )


@pytest.mark.parametrize(
    "schema",
    [
        """
        CREATE TABLE hourly_points (
            source_forecast_id INTEGER NOT NULL,
            timestamp_unix INTEGER NOT NULL,
            PRIMARY KEY (source_forecast_id, timestamp_unix)
        ) WITHOUT ROWID;
        """,
        """
        CREATE TABLE hourly_backing (
            source_forecast_id INTEGER NOT NULL,
            timestamp_unix INTEGER NOT NULL
        );
        CREATE VIEW hourly_points AS SELECT * FROM hourly_backing;
        """,
    ],
)
def test_timestamp_check_skips_non_rowid_inputs(schema: str) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(schema)
        failures = inspect_db._timestamp_order_failures(connection)
    finally:
        connection.close()

    assert failures == [
        "hourly timestamp order skipped: hourly_points is not a rowid-backed table",
    ]


def test_timestamp_check_uses_metadata_when_ddl_mentions_without_rowid() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            CREATE TABLE hourly_points (
                source_forecast_id INTEGER NOT NULL,
                timestamp_unix INTEGER NOT NULL,
                note TEXT CHECK (note <> 'WITHOUT ROWID')
            );
            INSERT INTO hourly_points VALUES (1, 200, NULL);
            INSERT INTO hourly_points VALUES (1, 100, NULL);
            """,
        )

        failures = inspect_db._timestamp_order_failures(connection)
    finally:
        connection.close()

    assert failures == [
        "hourly timestamps not strictly increasing for source 1: 1 rows",
    ]


def test_main_reports_missing_columns_without_crashing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "partial-columns.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY);
            CREATE TABLE forecast_runs (id INTEGER PRIMARY KEY);
            CREATE TABLE provider_results (id INTEGER PRIMARY KEY);
            CREATE TABLE source_forecasts (id INTEGER PRIMARY KEY);
            CREATE TABLE hourly_points (source_forecast_id INTEGER);
            CREATE TABLE daily_points (condition TEXT);
            """,
        )
    finally:
        connection.close()

    assert inspect_db.main([str(database_path)]) == 1

    output = capsys.readouterr().out
    assert "version: unknown (missing schema_version column)" in output
    assert "unavailable: forecast_runs missing columns" in output
    assert "unavailable: provider_results missing columns" in output
    assert "unavailable: missing join columns provider" in output
    assert "FAIL: hourly bounds skipped: missing source_forecasts table" not in output
    assert (
        "FAIL: hourly bounds skipped: source_forecasts missing columns provider"
        in output
    )


def test_main_handles_empty_database_as_failed_inspection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "empty.sqlite"
    sqlite3.connect(database_path).close()

    assert inspect_db.main([str(database_path)]) == 1

    output = capsys.readouterr().out
    assert "version: legacy/unversioned" in output
    assert "unavailable: missing forecast_runs table" in output
    assert "FAIL: hourly bounds skipped: missing hourly_points table" in output
