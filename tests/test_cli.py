from __future__ import annotations

import pytest

from omni_weather_forecast_apis.cli import _resolve_required


def test_resolve_required_preserves_zero_values() -> None:
    assert _resolve_required(0.0, 51.5, "lat") == 0.0
    assert _resolve_required(0.0, -0.1, "lon") == 0.0


def test_resolve_required_exits_when_both_sources_are_missing() -> None:
    with pytest.raises(SystemExit) as exc_info:
        _resolve_required(None, None, "lat")

    assert exc_info.value.code == 2
