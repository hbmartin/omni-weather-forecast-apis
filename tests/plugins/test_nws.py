"""Tests for NWS parsing helpers."""

from omni_weather_forecast_apis.plugins.nws import _alert_url, _local_start_date


def test_local_start_date_rejects_boolean_values() -> None:
    assert _local_start_date({"startTime": True}) is None


def test_alert_url_strips_whitespace() -> None:
    assert _alert_url({"id": "  https://example.com/alert  "}, {}) == (
        "https://example.com/alert"
    )
