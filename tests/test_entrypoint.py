from __future__ import annotations

import runpy

import pytest

from omni_weather_forecast_apis import cli


def test_module_entrypoint_propagates_main_exit_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "main", lambda: 23)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module(
            "omni_weather_forecast_apis.__main__",
            run_name="__main__",
        )

    assert exc_info.value.code == 23
