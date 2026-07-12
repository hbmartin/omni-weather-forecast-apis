"""Tests for the csv and ndjson CLI output formats."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import pytest

from omni_weather_forecast_apis import cli
from omni_weather_forecast_apis.cli import (
    _csv_field_names,
    _print_csv,
    _print_ndjson,
    build_parser,
    main,
)
from omni_weather_forecast_apis.plugins._base import (
    build_alert,
    build_daily_point,
    build_hourly_point,
    build_minutely_point,
    build_source_forecast,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    Granularity,
    ProviderError,
    ProviderErrorDetail,
    ProviderId,
    ProviderSuccess,
)


def _sample_response(*, with_alert: bool = True) -> ForecastResponse:
    forecast = build_source_forecast(
        ProviderId.OPEN_METEO,
        model="best_match",
        minutely=[
            build_minutely_point(
                "2026-07-12T18:00:00+00:00",
                precipitation_intensity=0.4,
            ),
        ],
        hourly=[
            build_hourly_point(
                "2026-07-12T18:00:00+00:00",
                temperature=21.5,
                wind_speed=3.2,
            ),
        ],
        daily=[
            build_daily_point(
                "2026-07-12",
                temperature_max=28.0,
                temperature_min=17.0,
            ),
        ],
        alerts=(
            [
                build_alert(
                    sender_name="NWS",
                    event="Heat Advisory",
                    start="2026-07-12T18:00:00+00:00",
                    end="2026-07-13T00:00:00+00:00",
                    description="It is hot.",
                    severity="Severe",
                ),
            ]
            if with_alert
            else []
        ),
    )
    success = ProviderSuccess(
        provider=ProviderId.OPEN_METEO,
        forecasts=[forecast],
        fetched_at=datetime(2026, 7, 12, 18, 0, tzinfo=UTC),
        latency_ms=120.0,
    )
    failure = ProviderError(
        provider=ProviderId.OPENWEATHER,
        error=ProviderErrorDetail(
            code=ErrorCode.AUTH_FAILED,
            message="bad key",
            http_status=401,
            latency_ms=45.0,
        ),
    )
    return ForecastResponse(
        request=ForecastResponseRequest(
            latitude=34.0,
            longitude=-118.0,
            granularity=[Granularity.HOURLY, Granularity.DAILY],
            language="en",
        ),
        results=[success, failure],
        summary=ForecastResponseSummary(total=2, succeeded=1, failed=1),
        completed_at=datetime(2026, 7, 12, 18, 0, 1, tzinfo=UTC),
        total_latency_ms=1000.0,
    )


def test_build_parser_accepts_csv_and_ndjson_formats() -> None:
    assert build_parser().parse_args(["--format", "csv"]).output_format == "csv"
    assert build_parser().parse_args(["--format", "ndjson"]).output_format == "ndjson"


def test_csv_field_names_start_with_row_identity() -> None:
    names = _csv_field_names()

    assert names[:3] == ["provider", "model", "granularity"]
    assert "temperature" in names
    assert "temperature_max" in names
    assert "precipitation_intensity" in names
    assert len(names) == len(set(names))


def test_csv_output_has_one_row_per_point(capsys: pytest.CaptureFixture[str]) -> None:
    _print_csv(_sample_response())

    captured = capsys.readouterr()
    rows = list(csv.DictReader(io.StringIO(captured.out)))

    assert [row["granularity"] for row in rows] == ["minutely", "hourly", "daily"]
    assert all(row["provider"] == "open_meteo" for row in rows)
    assert all(row["model"] == "best_match" for row in rows)

    hourly_row = rows[1]
    assert hourly_row["temperature"] == "21.5"
    assert hourly_row["temperature_max"] == ""

    daily_row = rows[2]
    assert daily_row["temperature_max"] == "28.0"
    assert daily_row["temperature"] == ""


def test_csv_reports_alerts_and_errors_on_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_csv(_sample_response())

    captured = capsys.readouterr()
    assert "1 alert(s) omitted" in captured.err
    assert "provider openweather failed: auth_failed: bad key" in captured.err
    assert "bad key" not in captured.out
    assert "Heat Advisory" not in captured.out


def test_csv_without_alerts_prints_no_alert_note(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_csv(_sample_response(with_alert=False))

    captured = capsys.readouterr()
    assert "omitted" not in captured.err


def test_ndjson_lines_are_typed_json_objects(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_ndjson(_sample_response())

    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.splitlines()]

    by_type: dict[str, list[dict]] = {}
    for line in lines:
        by_type.setdefault(line["type"], []).append(line)

    assert len(by_type["forecast_point"]) == 3
    assert {point["granularity"] for point in by_type["forecast_point"]} == {
        "minutely",
        "hourly",
        "daily",
    }
    (alert,) = by_type["alert"]
    assert alert["event"] == "Heat Advisory"
    assert alert["provider"] == "open_meteo"
    (error,) = by_type["provider_error"]
    assert error["provider"] == "openweather"
    assert error["code"] == "auth_failed"
    assert error["http_status"] == 401
    assert captured.err == ""


class _StubClient:
    def __init__(self, response: ForecastResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _StubClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def forecast(self, request: object) -> ForecastResponse:
        del request
        return self._response


def test_main_end_to_end_ndjson(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = _sample_response()

    async def fake_create(config: object, **kwargs: object) -> _StubClient:
        del config, kwargs
        return _StubClient(response)

    monkeypatch.setattr(cli, "create_omni_weather", fake_create)
    config_path = tmp_path / "config.toml"
    config_path.write_text('[[providers]]\nplugin_id = "open_meteo"\nconfig = {}\n')

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--lat",
            "34.0",
            "--lon",
            "-118.0",
            "--format",
            "ndjson",
        ],
    )

    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.splitlines()]
    assert {line["type"] for line in lines} == {
        "forecast_point",
        "alert",
        "provider_error",
    }
    assert exit_code == 1
