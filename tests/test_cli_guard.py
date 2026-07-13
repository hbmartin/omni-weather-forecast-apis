from __future__ import annotations

import importlib

from omni_weather_forecast_apis import __main__ as cli_guard


def test_cli_guard_prints_install_hint_when_extra_is_missing(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(cli_guard, "_missing_cli_modules", lambda: ["rich"])

    assert cli_guard.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error: omni-weather CLI dependencies are not installed" in captured.err
    assert 'pip install "omni-weather-forecast-apis[cli]"' in captured.err


def test_cli_guard_delegates_when_extra_is_installed(monkeypatch) -> None:
    seen = {}

    class FakeCli:
        @staticmethod
        def main(argv):
            seen["argv"] = argv
            return 17

    real_import = importlib.import_module

    def fake_import(name):
        if name == "omni_weather_forecast_apis.cli":
            return FakeCli
        return real_import(name)

    monkeypatch.setattr(cli_guard, "_missing_cli_modules", list)
    monkeypatch.setattr(cli_guard.importlib, "import_module", fake_import)

    assert cli_guard.main(["providers"]) == 17
    assert seen["argv"] == ["providers"]


def test_cli_guard_detects_missing_modules(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_guard.importlib.util,
        "find_spec",
        lambda name: None if name in {"rich", "tomli_w"} else object(),
    )

    assert cli_guard._missing_cli_modules() == ["rich", "tomli_w"]
