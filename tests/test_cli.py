"""Tests for CLI module."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from omni_weather_forecast_apis.cli import build_parser, load_config, save_to_sqlite
from omni_weather_forecast_apis.types.schema import (
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    Granularity,
)


class TestBuildParser:
    def test_required_args(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_valid_args(self):
        parser = build_parser()
        args = parser.parse_args([
            "--config", "config.json",
            "--lat", "34.0",
            "--lon", "-117.0",
        ])
        assert args.lat == 34.0
        assert args.lon == -117.0
        assert args.config == Path("config.json")

    def test_optional_args(self):
        parser = build_parser()
        args = parser.parse_args([
            "--config", "config.json",
            "--lat", "34.0",
            "--lon", "-117.0",
            "--granularity", "hourly",
            "--include-raw",
            "--timeout", "5000",
            "--output", "results.db",
        ])
        assert args.granularity == ["hourly"]
        assert args.include_raw is True
        assert args.timeout == 5000


class TestLoadConfig:
    def test_load_valid_config(self, tmp_path):
        config_data = {
            "providers": [
                {
                    "plugin_id": "open_meteo",
                    "config": {},
                }
            ],
            "default_timeout_ms": 5000,
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        config = load_config(config_file)
        assert len(config.providers) == 1
        assert config.default_timeout_ms == 5000


class TestSaveToSqlite:
    def test_save_response(self, tmp_path):
        db_path = tmp_path / "test.db"
        response = ForecastResponse(
            request=ForecastResponseRequest(
                latitude=34.0,
                longitude=-117.0,
                granularity=[Granularity.HOURLY],
            ),
            results=[],
            summary=ForecastResponseSummary(total=0, succeeded=0, failed=0),
            completed_at=datetime.now(UTC),
            total_latency_ms=100.0,
        )

        save_to_sqlite(db_path, response)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT * FROM forecast_runs")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0][1] == 34.0  # latitude
        assert rows[0][2] == -117.0  # longitude
