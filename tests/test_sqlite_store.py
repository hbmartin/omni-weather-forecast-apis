from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime

from omni_weather_forecast_apis.sqlite_store import save_forecast_response
from omni_weather_forecast_apis.types import (
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    ModelSource,
    ProviderId,
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
                                timestamp_unix=1710244800,
                                temperature=18.2,
                                condition=WeatherCondition.CLEAR,
                            )
                        ],
                        daily=[],
                    )
                ],
                fetched_at=datetime(2026, 3, 12, 12, tzinfo=UTC),
                latency_ms=12.3,
            )
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
        hourly_count = connection.execute("SELECT COUNT(*) FROM hourly_points").fetchone()
    finally:
        connection.close()

    assert run_id == 1
    assert run_count == (1,)
    assert provider_count == (1,)
    assert hourly_count == (1,)
