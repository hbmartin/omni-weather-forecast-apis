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
