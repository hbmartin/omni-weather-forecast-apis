from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omni_weather_forecast_apis.types import (
    ForecastResponse,
    ProviderError,
    ProviderLogEvent,
    ProviderSuccess,
)


def save_forecast_response(
    database_path: str | Path,
    response: ForecastResponse,
) -> int:
    """Persist one normalized forecast response into SQLite."""

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _create_schema(connection)
        run_id = _insert_run(connection, response)
        for result in response.results:
            provider_result_id = _insert_provider_result(connection, run_id, result)
            if isinstance(result, ProviderSuccess):
                _insert_forecasts(connection, provider_result_id, result)
        connection.commit()
        return run_id
    finally:
        connection.close()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS forecast_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            granularity TEXT NOT NULL,
            language TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            total_latency_ms REAL NOT NULL,
            total_results INTEGER NOT NULL,
            succeeded INTEGER NOT NULL,
            failed INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS provider_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            status TEXT NOT NULL,
            fetched_at TEXT,
            fetched_at_unix INTEGER,
            run_cycle TEXT,
            latency_ms REAL NOT NULL,
            error_code TEXT,
            error_message TEXT,
            http_status INTEGER,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS source_forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_result_id INTEGER NOT NULL REFERENCES provider_results(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            model TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS minutely_points (
            source_forecast_id INTEGER NOT NULL REFERENCES source_forecasts(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            timestamp_unix INTEGER NOT NULL,
            precipitation_intensity REAL,
            precipitation_probability REAL
        );

        CREATE TABLE IF NOT EXISTS hourly_points (
            source_forecast_id INTEGER NOT NULL REFERENCES source_forecasts(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            timestamp_unix INTEGER NOT NULL,
            horizon_hours REAL,
            temperature REAL,
            apparent_temperature REAL,
            dew_point REAL,
            humidity REAL,
            wind_speed REAL,
            wind_gust REAL,
            wind_direction REAL,
            pressure_sea REAL,
            pressure_surface REAL,
            precipitation REAL,
            precipitation_probability REAL,
            rain REAL,
            snow REAL,
            snow_depth REAL,
            cloud_cover REAL,
            cloud_cover_low REAL,
            cloud_cover_mid REAL,
            cloud_cover_high REAL,
            visibility REAL,
            uv_index REAL,
            solar_radiation_ghi REAL,
            solar_radiation_dni REAL,
            solar_radiation_dhi REAL,
            condition TEXT,
            condition_original TEXT,
            condition_code_original TEXT,
            is_day INTEGER
        );

        CREATE TABLE IF NOT EXISTS daily_points (
            source_forecast_id INTEGER NOT NULL REFERENCES source_forecasts(id) ON DELETE CASCADE,
            forecast_date TEXT NOT NULL,
            temperature_max REAL,
            temperature_min REAL,
            apparent_temperature_max REAL,
            apparent_temperature_min REAL,
            wind_speed_max REAL,
            wind_gust_max REAL,
            wind_direction_dominant REAL,
            precipitation_sum REAL,
            precipitation_probability_max REAL,
            rain_sum REAL,
            snowfall_sum REAL,
            cloud_cover_mean REAL,
            uv_index_max REAL,
            visibility_min REAL,
            humidity_mean REAL,
            pressure_sea_mean REAL,
            condition TEXT,
            summary TEXT,
            sunrise TEXT,
            sunset TEXT,
            moonrise TEXT,
            moonset TEXT,
            moon_phase REAL,
            daylight_duration REAL,
            solar_radiation_sum REAL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            source_forecast_id INTEGER NOT NULL REFERENCES source_forecasts(id) ON DELETE CASCADE,
            sender_name TEXT NOT NULL,
            event TEXT NOT NULL,
            start TEXT NOT NULL,
            end TEXT,
            description TEXT NOT NULL,
            severity TEXT,
            url TEXT
        );

        CREATE TABLE IF NOT EXISTS provider_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES forecast_runs(id) ON DELETE SET NULL,
            provider TEXT NOT NULL,
            phase TEXT NOT NULL,
            message TEXT NOT NULL,
            latency_ms REAL NOT NULL DEFAULT 0,
            error_code TEXT,
            http_status INTEGER,
            extra_json TEXT,
            logged_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_provider_results_run_provider
            ON provider_results(run_id, provider);
        CREATE INDEX IF NOT EXISTS idx_provider_results_run_cycle
            ON provider_results(run_cycle);
        CREATE INDEX IF NOT EXISTS idx_source_forecasts_provider_result
            ON source_forecasts(provider_result_id);
        CREATE INDEX IF NOT EXISTS idx_hourly_points_source
            ON hourly_points(source_forecast_id);
        CREATE INDEX IF NOT EXISTS idx_hourly_points_horizon
            ON hourly_points(horizon_hours);
        CREATE INDEX IF NOT EXISTS idx_hourly_points_timestamp
            ON hourly_points(timestamp_unix);
        CREATE INDEX IF NOT EXISTS idx_hourly_points_horizon_timestamp
            ON hourly_points(horizon_hours, timestamp_unix);
        CREATE INDEX IF NOT EXISTS idx_minutely_points_source_timestamp
            ON minutely_points(source_forecast_id, timestamp_unix);
        CREATE INDEX IF NOT EXISTS idx_daily_points_source_date
            ON daily_points(source_forecast_id, forecast_date);

        CREATE VIEW IF NOT EXISTS stacking_features AS
        SELECT
            hp.timestamp                    AS valid_time,
            hp.timestamp_unix               AS valid_time_unix,
            hp.horizon_hours,
            pr.run_cycle,
            pr.fetched_at,
            pr.fetched_at_unix,
            sf.provider,
            sf.model,
            fr.latitude,
            fr.longitude,
            hp.temperature,
            hp.apparent_temperature,
            hp.dew_point,
            hp.humidity,
            hp.wind_speed,
            hp.wind_gust,
            hp.wind_direction,
            hp.pressure_sea,
            hp.pressure_surface,
            hp.precipitation,
            hp.precipitation_probability,
            hp.rain,
            hp.snow,
            hp.snow_depth,
            hp.cloud_cover,
            hp.cloud_cover_low,
            hp.cloud_cover_mid,
            hp.cloud_cover_high,
            hp.visibility,
            hp.uv_index,
            hp.solar_radiation_ghi,
            hp.solar_radiation_dni,
            hp.solar_radiation_dhi,
            hp.condition,
            hp.is_day
        FROM hourly_points hp
        JOIN source_forecasts sf ON hp.source_forecast_id = sf.id
        JOIN provider_results pr ON sf.provider_result_id = pr.id
        JOIN forecast_runs fr    ON pr.run_id = fr.id
        WHERE pr.status = 'success';
        """,
    )
    _ensure_provider_logs_columns(connection)


def _ensure_provider_logs_columns(connection: sqlite3.Connection) -> None:
    provider_log_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(provider_logs)")
    }
    if "extra_json" not in provider_log_columns:
        connection.execute("ALTER TABLE provider_logs ADD COLUMN extra_json TEXT")


def _insert_run(connection: sqlite3.Connection, response: ForecastResponse) -> int:
    cursor = connection.execute(
        """
        INSERT INTO forecast_runs (
            latitude,
            longitude,
            granularity,
            language,
            completed_at,
            total_latency_ms,
            total_results,
            succeeded,
            failed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            response.request.latitude,
            response.request.longitude,
            json.dumps([item.value for item in response.request.granularity]),
            response.request.language,
            response.completed_at.isoformat(),
            response.total_latency_ms,
            response.summary.total,
            response.summary.succeeded,
            response.summary.failed,
        ),
    )
    return _lastrowid(cursor)


def _insert_provider_result(
    connection: sqlite3.Connection,
    run_id: int,
    result: ProviderSuccess | ProviderError,
) -> int:
    if isinstance(result, ProviderSuccess):
        fetched_at_unix = int(result.fetched_at.timestamp())
        payload = (
            run_id,
            result.provider.value,
            result.status,
            result.fetched_at.isoformat(),
            fetched_at_unix,
            _compute_run_cycle(result.fetched_at),
            result.latency_ms,
            None,
            None,
            None,
            _json_dump(result.raw),
        )
    else:
        payload = (
            run_id,
            result.provider.value,
            result.status,
            None,
            None,
            None,
            result.error.latency_ms,
            result.error.code.value,
            result.error.message,
            result.error.http_status,
            _json_dump(result.error.raw),
        )
    cursor = connection.execute(
        """
        INSERT INTO provider_results (
            run_id,
            provider,
            status,
            fetched_at,
            fetched_at_unix,
            run_cycle,
            latency_ms,
            error_code,
            error_message,
            http_status,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )
    return _lastrowid(cursor)


def _insert_forecasts(
    connection: sqlite3.Connection,
    provider_result_id: int,
    result: ProviderSuccess,
) -> None:
    fetched_at_unix = int(result.fetched_at.timestamp())
    for forecast in result.forecasts:
        cursor = connection.execute(
            """
            INSERT INTO source_forecasts (provider_result_id, provider, model)
            VALUES (?, ?, ?)
            """,
            (
                provider_result_id,
                forecast.source.provider.value,
                forecast.source.model,
            ),
        )
        source_forecast_id = _lastrowid(cursor)
        _insert_minutely(connection, source_forecast_id, forecast.minutely)
        _insert_hourly(connection, source_forecast_id, fetched_at_unix, forecast.hourly)
        _insert_daily(connection, source_forecast_id, forecast.daily)
        _insert_alerts(connection, source_forecast_id, forecast.alerts)


def _insert_minutely(
    connection: sqlite3.Connection,
    source_forecast_id: int,
    points: list[Any],
) -> None:
    connection.executemany(
        """
        INSERT INTO minutely_points (
            source_forecast_id,
            timestamp,
            timestamp_unix,
            precipitation_intensity,
            precipitation_probability
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                source_forecast_id,
                point.timestamp.isoformat(),
                point.timestamp_unix,
                point.precipitation_intensity,
                point.precipitation_probability,
            )
            for point in points
        ],
    )


def _insert_hourly(
    connection: sqlite3.Connection,
    source_forecast_id: int,
    fetched_at_unix: int,
    points: list[Any],
) -> None:
    connection.executemany(
        """
        INSERT INTO hourly_points (
            source_forecast_id,
            timestamp,
            timestamp_unix,
            horizon_hours,
            temperature,
            apparent_temperature,
            dew_point,
            humidity,
            wind_speed,
            wind_gust,
            wind_direction,
            pressure_sea,
            pressure_surface,
            precipitation,
            precipitation_probability,
            rain,
            snow,
            snow_depth,
            cloud_cover,
            cloud_cover_low,
            cloud_cover_mid,
            cloud_cover_high,
            visibility,
            uv_index,
            solar_radiation_ghi,
            solar_radiation_dni,
            solar_radiation_dhi,
            condition,
            condition_original,
            condition_code_original,
            is_day
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                source_forecast_id,
                point.timestamp.isoformat(),
                point.timestamp_unix,
                (point.timestamp_unix - fetched_at_unix) / 3600.0,
                point.temperature,
                point.apparent_temperature,
                point.dew_point,
                point.humidity,
                point.wind_speed,
                point.wind_gust,
                point.wind_direction,
                point.pressure_sea,
                point.pressure_surface,
                point.precipitation,
                point.precipitation_probability,
                point.rain,
                point.snow,
                point.snow_depth,
                point.cloud_cover,
                point.cloud_cover_low,
                point.cloud_cover_mid,
                point.cloud_cover_high,
                point.visibility,
                point.uv_index,
                point.solar_radiation_ghi,
                point.solar_radiation_dni,
                point.solar_radiation_dhi,
                point.condition.value if point.condition is not None else None,
                point.condition_original,
                (
                    str(point.condition_code_original)
                    if point.condition_code_original is not None
                    else None
                ),
                None if point.is_day is None else int(point.is_day),
            )
            for point in points
        ],
    )


def _insert_daily(
    connection: sqlite3.Connection,
    source_forecast_id: int,
    points: list[Any],
) -> None:
    connection.executemany(
        """
        INSERT INTO daily_points (
            source_forecast_id,
            forecast_date,
            temperature_max,
            temperature_min,
            apparent_temperature_max,
            apparent_temperature_min,
            wind_speed_max,
            wind_gust_max,
            wind_direction_dominant,
            precipitation_sum,
            precipitation_probability_max,
            rain_sum,
            snowfall_sum,
            cloud_cover_mean,
            uv_index_max,
            visibility_min,
            humidity_mean,
            pressure_sea_mean,
            condition,
            summary,
            sunrise,
            sunset,
            moonrise,
            moonset,
            moon_phase,
            daylight_duration,
            solar_radiation_sum
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                source_forecast_id,
                point.date.isoformat(),
                point.temperature_max,
                point.temperature_min,
                point.apparent_temperature_max,
                point.apparent_temperature_min,
                point.wind_speed_max,
                point.wind_gust_max,
                point.wind_direction_dominant,
                point.precipitation_sum,
                point.precipitation_probability_max,
                point.rain_sum,
                point.snowfall_sum,
                point.cloud_cover_mean,
                point.uv_index_max,
                point.visibility_min,
                point.humidity_mean,
                point.pressure_sea_mean,
                point.condition.value if point.condition is not None else None,
                point.summary,
                _optional_isoformat(point.sunrise),
                _optional_isoformat(point.sunset),
                _optional_isoformat(point.moonrise),
                _optional_isoformat(point.moonset),
                point.moon_phase,
                point.daylight_duration,
                point.solar_radiation_sum,
            )
            for point in points
        ],
    )


def _insert_alerts(
    connection: sqlite3.Connection,
    source_forecast_id: int,
    alerts: list[Any],
) -> None:
    connection.executemany(
        """
        INSERT INTO alerts (
            source_forecast_id,
            sender_name,
            event,
            start,
            end,
            description,
            severity,
            url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                source_forecast_id,
                alert.sender_name,
                alert.event,
                alert.start.isoformat(),
                _optional_isoformat(alert.end),
                alert.description,
                alert.severity.value if alert.severity is not None else None,
                alert.url,
            )
            for alert in alerts
        ],
    )


def save_provider_logs(
    database_path: str | Path,
    events: list[ProviderLogEvent],
    run_id: int | None = None,
) -> None:
    """Persist provider log events into the provider_logs table."""

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _create_schema(connection)
        connection.executemany(
            """
            INSERT INTO provider_logs (
                run_id, provider, phase, message,
                latency_ms, error_code, http_status, extra_json, logged_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    event.provider.value,
                    event.phase,
                    event.message,
                    event.latency_ms,
                    event.error_code.value if event.error_code is not None else None,
                    event.http_status,
                    _json_dump(event.extra) if event.extra else None,
                    event.timestamp.isoformat(),
                )
                for event in events
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _compute_run_cycle(fetched_at: datetime) -> str:
    """Bucket fetched_at into the nearest 6-hour NWP cycle (00/06/12/18 UTC)."""
    hour_bucket = (fetched_at.hour // 6) * 6
    return fetched_at.replace(
        hour=hour_bucket, minute=0, second=0, microsecond=0, tzinfo=UTC,
    ).isoformat()


def _optional_isoformat(value: Any) -> str | None:
    return None if value is None else value.isoformat()


def _json_dump(payload: Any) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True, default=str)


def _lastrowid(cursor: sqlite3.Cursor) -> int:
    lastrowid = cursor.lastrowid
    if lastrowid is None:
        msg = "SQLite cursor did not expose a lastrowid."
        raise RuntimeError(msg)
    return int(lastrowid)
