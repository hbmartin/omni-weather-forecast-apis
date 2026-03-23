from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from omni_weather_forecast_apis.sqlite_store import (
    save_forecast_response,
    save_provider_logs,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    ModelSource,
    ProviderId,
    ProviderLogEvent,
    ProviderSuccess,
    SourceForecast,
    WeatherCondition,
    WeatherDataPoint,
)


def test_save_forecast_response_persists_rows(tmp_path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    response = ForecastResponse(
        request=ForecastResponseRequest(
            latitude=34.0,
            longitude=-118.0,
            granularity=[],
            language="en",
        ),
        results=[
            ProviderSuccess(
                provider=ProviderId.OPEN_METEO,
                forecasts=[
                    SourceForecast(
                        source=ModelSource(
                            provider=ProviderId.OPEN_METEO,
                            model="best_match",
                        ),
                        hourly=[
                            WeatherDataPoint(
                                timestamp=datetime(2026, 3, 12, 12, tzinfo=UTC),
                                timestamp_unix=int(
                                    datetime(2026, 3, 12, 12, tzinfo=UTC).timestamp(),
                                ),
                                temperature=18.2,
                                condition=WeatherCondition.CLEAR,
                            ),
                        ],
                        daily=[],
                    ),
                ],
                fetched_at=datetime(2026, 3, 12, 12, tzinfo=UTC),
                latency_ms=12.3,
            ),
        ],
        summary=ForecastResponseSummary(total=1, succeeded=1, failed=0),
        completed_at=datetime(2026, 3, 12, 12, 1, tzinfo=UTC),
        total_latency_ms=20.1,
    )

    run_id = save_forecast_response(database_path, response)

    connection = sqlite3.connect(database_path)
    try:
        run_count = connection.execute("SELECT COUNT(*) FROM forecast_runs").fetchone()
        provider_count = connection.execute(
            "SELECT COUNT(*) FROM provider_results",
        ).fetchone()
        hourly_count = connection.execute(
            "SELECT COUNT(*) FROM hourly_points",
        ).fetchone()
    finally:
        connection.close()

    assert run_id == 1
    assert run_count == (1,)
    assert provider_count == (1,)
    assert hourly_count == (1,)

    # Verify new schema columns
    connection = sqlite3.connect(database_path)
    try:
        pr_row = connection.execute(
            "SELECT fetched_at_unix, run_cycle FROM provider_results WHERE id = 1",
        ).fetchone()
        hp_row = connection.execute(
            "SELECT horizon_hours FROM hourly_points LIMIT 1",
        ).fetchone()
    finally:
        connection.close()

    fetched_ts = int(datetime(2026, 3, 12, 12, tzinfo=UTC).timestamp())
    point_ts = int(datetime(2026, 3, 12, 12, tzinfo=UTC).timestamp())
    assert pr_row is not None
    assert pr_row[0] == fetched_ts
    assert pr_row[1] == "2026-03-12T12:00:00+00:00"
    assert hp_row is not None
    assert hp_row[0] == (point_ts - fetched_ts) / 3600.0


def test_save_forecast_response_uses_foreign_keys(tmp_path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    response = ForecastResponse(
        request=ForecastResponseRequest(
            latitude=34.0,
            longitude=-118.0,
            granularity=[],
            language="en",
        ),
        results=[
            ProviderSuccess(
                provider=ProviderId.OPEN_METEO,
                forecasts=[
                    SourceForecast(
                        source=ModelSource(
                            provider=ProviderId.OPEN_METEO,
                            model="best_match",
                        ),
                        hourly=[
                            WeatherDataPoint(
                                timestamp=datetime(2026, 3, 12, 12, tzinfo=UTC),
                                timestamp_unix=int(
                                    datetime(2026, 3, 12, 12, tzinfo=UTC).timestamp(),
                                ),
                                temperature=18.2,
                                condition=WeatherCondition.CLEAR,
                            ),
                        ],
                        daily=[],
                    ),
                ],
                fetched_at=datetime(2026, 3, 12, 12, tzinfo=UTC),
                latency_ms=12.3,
            ),
        ],
        summary=ForecastResponseSummary(total=1, succeeded=1, failed=0),
        completed_at=datetime(2026, 3, 12, 12, 1, tzinfo=UTC),
        total_latency_ms=20.1,
    )

    run_id = save_forecast_response(database_path, response)

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DELETE FROM forecast_runs WHERE id = ?", (run_id,))
        provider_count = connection.execute(
            "SELECT COUNT(*) FROM provider_results",
        ).fetchone()
        hourly_count = connection.execute(
            "SELECT COUNT(*) FROM hourly_points",
        ).fetchone()
    finally:
        connection.close()

    assert provider_count == (0,)
    assert hourly_count == (0,)


def test_save_provider_logs_migrates_schema_and_persists_metadata(tmp_path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE provider_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                provider TEXT NOT NULL,
                phase TEXT NOT NULL,
                message TEXT NOT NULL,
                latency_ms REAL NOT NULL DEFAULT 0,
                error_code TEXT,
                http_status INTEGER,
                logged_at TEXT NOT NULL
            )
            """,
        )
        connection.commit()
    finally:
        connection.close()

    event_timestamp = datetime(2026, 3, 12, 12, 30, tzinfo=UTC)
    save_provider_logs(
        database_path,
        [
            ProviderLogEvent(
                provider=ProviderId.OPEN_METEO,
                phase="error",
                message="network failed",
                timestamp=event_timestamp,
                latency_ms=12.5,
                error_code=ErrorCode.NETWORK,
                http_status=502,
                extra={"attempt": 1},
            ),
        ],
        run_id=7,
    )

    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(provider_logs)").fetchall()
        }
        row = connection.execute(
            """
            SELECT
                run_id,
                provider,
                phase,
                message,
                latency_ms,
                error_code,
                http_status,
                extra_json,
                logged_at
            FROM provider_logs
            """,
        ).fetchone()
    finally:
        connection.close()

    assert "extra_json" in columns
    assert row == (
        7,
        ProviderId.OPEN_METEO.value,
        "error",
        "network failed",
        12.5,
        ErrorCode.NETWORK.value,
        502,
        json.dumps({"attempt": 1}, sort_keys=True),
        event_timestamp.isoformat(),
    )


def test_stacking_features_view_returns_joined_data(tmp_path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    fetched = datetime(2026, 3, 12, 14, 23, tzinfo=UTC)
    response = ForecastResponse(
        request=ForecastResponseRequest(
            latitude=52.5,
            longitude=13.4,
            granularity=[],
            language="en",
        ),
        results=[
            ProviderSuccess(
                provider=ProviderId.OPEN_METEO,
                forecasts=[
                    SourceForecast(
                        source=ModelSource(
                            provider=ProviderId.OPEN_METEO,
                            model="icon_seamless",
                        ),
                        hourly=[
                            WeatherDataPoint(
                                timestamp=datetime(2026, 3, 12, 20, tzinfo=UTC),
                                timestamp_unix=int(
                                    datetime(2026, 3, 12, 20, tzinfo=UTC).timestamp(),
                                ),
                                temperature=7.5,
                            ),
                        ],
                        daily=[],
                    ),
                ],
                fetched_at=fetched,
                latency_ms=50.0,
            ),
        ],
        summary=ForecastResponseSummary(total=1, succeeded=1, failed=0),
        completed_at=datetime(2026, 3, 12, 14, 24, tzinfo=UTC),
        total_latency_ms=55.0,
    )
    save_forecast_response(database_path, response)

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT valid_time_unix, horizon_hours, run_cycle, provider, model, "
            "latitude, longitude, temperature FROM stacking_features",
        ).fetchone()
    finally:
        connection.close()

    point_unix = int(datetime(2026, 3, 12, 20, tzinfo=UTC).timestamp())
    fetched_unix = int(fetched.timestamp())
    assert row is not None
    assert row[0] == point_unix
    assert row[1] == (point_unix - fetched_unix) / 3600.0
    # run_cycle should bucket 14:23 → 12:00
    assert row[2] == "2026-03-12T12:00:00+00:00"
    assert row[3] == "open_meteo"
    assert row[4] == "icon_seamless"
    assert row[5] == 52.5
    assert row[6] == 13.4
    assert row[7] == 7.5


def test_run_cycle_buckets_to_six_hour_boundaries(tmp_path) -> None:
    database_path = tmp_path / "forecast.sqlite"
    # fetched_at at 05:59 should bucket to 00:00
    fetched = datetime(2026, 6, 15, 5, 59, tzinfo=UTC)
    response = ForecastResponse(
        request=ForecastResponseRequest(
            latitude=0.0,
            longitude=0.0,
            granularity=[],
            language="en",
        ),
        results=[
            ProviderSuccess(
                provider=ProviderId.NWS,
                forecasts=[
                    SourceForecast(
                        source=ModelSource(provider=ProviderId.NWS, model="gfs"),
                        hourly=[],
                        daily=[],
                    ),
                ],
                fetched_at=fetched,
                latency_ms=10.0,
            ),
        ],
        summary=ForecastResponseSummary(total=1, succeeded=1, failed=0),
        completed_at=datetime(2026, 6, 15, 6, 0, tzinfo=UTC),
        total_latency_ms=10.0,
    )
    save_forecast_response(database_path, response)

    connection = sqlite3.connect(database_path)
    try:
        run_cycle = connection.execute(
            "SELECT run_cycle FROM provider_results WHERE id = 1",
        ).fetchone()
    finally:
        connection.close()

    assert run_cycle is not None
    assert run_cycle[0] == "2026-06-15T00:00:00+00:00"
