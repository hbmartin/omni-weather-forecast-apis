from __future__ import annotations

import shlex
from pathlib import Path

from omni_weather_forecast_apis import _cli_paths as paths
from omni_weather_forecast_apis import cli
from omni_weather_forecast_apis._cli_setup import InitResult
from omni_weather_forecast_apis.cli import build_parser, main
from omni_weather_forecast_apis.types import OmniWeatherConfig, ProviderId


def _init_result(path: Path, *, run_forecast: bool = True) -> InitResult:
    return InitResult(
        path=path,
        config=OmniWeatherConfig(providers=[]),
        run_forecast=run_forecast,
    )


def test_parser_routes_new_subcommands_and_keeps_root_forecast_flags() -> None:
    forecast = build_parser().parse_args(
        ["--lat", "1", "--lon", "2", "--provider", "open_meteo"],
    )
    init = build_parser().parse_args(["init", "--config", "setup.toml"])
    providers = build_parser().parse_args(["providers"])
    doctor = build_parser().parse_args(
        ["doctor", "--config", "check.toml", "--live", "--provider", "nws"],
    )

    assert forecast.command is None
    assert forecast.provider == [ProviderId.OPEN_METEO]
    assert init.command == "init"
    assert init.command_config == Path("setup.toml")
    assert providers.command == "providers"
    assert doctor.command == "doctor"
    assert doctor.live is True
    assert doctor.doctor_provider == [ProviderId.NWS]


def test_config_resolution_prefers_platform_then_legacy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    platform_path = tmp_path / "platform" / "config.toml"
    legacy_path = tmp_path / "legacy.toml"
    monkeypatch.setattr(paths, "default_config_path", lambda: platform_path)
    monkeypatch.setattr(paths, "legacy_config_path", lambda: legacy_path)

    assert paths.find_config_path(None) is None
    legacy_path.write_text("legacy")
    assert paths.find_config_path(None) == legacy_path
    platform_path.parent.mkdir()
    platform_path.write_text("platform")
    assert paths.find_config_path(None) == platform_path

    explicit = tmp_path / "missing.toml"
    assert paths.find_config_path(explicit) == explicit.resolve()
    assert paths.init_target_path(explicit) == explicit.resolve()


def test_platform_default_helpers_use_platformdirs(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    calls: list[tuple[str, bool]] = []

    def config_path(app_name, *, appauthor):
        calls.append((app_name, appauthor))
        return config_dir

    def data_path(app_name, *, appauthor):
        calls.append((app_name, appauthor))
        return data_dir

    monkeypatch.setattr(paths.platformdirs, "user_config_path", config_path)
    monkeypatch.setattr(paths.platformdirs, "user_data_path", data_path)

    assert paths.default_config_path() == config_dir / "config.toml"
    assert paths.default_sqlite_path() == data_dir / "forecasts.sqlite"
    assert calls == [("omni-weather", False), ("omni-weather", False)]


def test_explicit_missing_config_is_error_without_setup(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    called = False

    def fake_init(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(cli, "run_init", fake_init)
    missing = tmp_path / "missing.toml"

    assert main(["--config", str(missing), "--lat", "1", "--lon", "2"]) == 2
    assert called is False
    assert str(missing) in capsys.readouterr().err


def test_noninteractive_first_run_explains_platform_path(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    expected = tmp_path / "platform config" / "config.toml"
    monkeypatch.setattr(cli, "find_config_path", lambda _explicit: None)
    monkeypatch.setattr(cli, "default_config_path", lambda: expected)
    monkeypatch.setattr(cli, "_automatic_setup_available", lambda: False)

    assert main([]) == 2
    error = capsys.readouterr().err
    assert str(expected) in error
    assert (
        "run in an interactive terminal: omni-weather init --config "
        f"{shlex.quote(str(expected))}" in error.splitlines()
    )


def test_automatic_setup_runs_original_forecast_with_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    generated = tmp_path / "config.toml"
    seen = {}
    monkeypatch.setattr(cli, "find_config_path", lambda _explicit: None)
    monkeypatch.setattr(cli, "default_config_path", lambda: generated)
    monkeypatch.setattr(cli, "_automatic_setup_available", lambda: True)

    def fake_init(path, *, defaults, automatic):
        seen["target"] = path
        seen["defaults"] = defaults
        seen["automatic"] = automatic
        return _init_result(generated)

    async def fake_forecast(parsed):
        seen["parsed"] = parsed
        return 7

    monkeypatch.setattr(cli, "run_init", fake_init)
    monkeypatch.setattr(cli, "_async_main", fake_forecast)

    exit_code = main(
        [
            "--lat",
            "34.5",
            "--lon",
            "-118.5",
            "--provider",
            "open_meteo",
            "--granularity",
            "hourly",
            "--format",
            "json",
        ],
    )

    assert exit_code == 7
    assert seen["target"] == generated
    assert seen["automatic"] is True
    assert seen["defaults"].latitude == 34.5
    assert seen["defaults"].providers == (ProviderId.OPEN_METEO,)
    parsed = seen["parsed"]
    assert parsed.config == generated
    assert parsed.lat == 34.5
    assert parsed.provider == [ProviderId.OPEN_METEO]
    assert parsed.output_format == "json"


def test_automatic_setup_cancellation_is_exit_two(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "find_config_path", lambda _explicit: None)
    monkeypatch.setattr(cli, "default_config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(cli, "_automatic_setup_available", lambda: True)
    monkeypatch.setattr(cli, "run_init", lambda *_args, **_kwargs: None)

    assert main([]) == 2


def test_explicit_init_cancellation_is_success(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "run_init", lambda *_args, **_kwargs: None)

    assert main(["init", "--config", str(tmp_path / "config.toml")]) == 0


def test_explicit_init_optionally_runs_generated_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    generated = tmp_path / "config.toml"
    seen = {}
    monkeypatch.setattr(
        cli,
        "run_init",
        lambda *_args, **_kwargs: _init_result(generated, run_forecast=True),
    )

    async def fake_forecast(parsed):
        seen["parsed"] = parsed
        return 0

    monkeypatch.setattr(cli, "_async_main", fake_forecast)

    assert main(["init", "--config", str(generated)]) == 0
    assert seen["parsed"].config == generated
    assert seen["parsed"].sqlite is None


def test_subcommand_dispatch_and_unexpected_errors(monkeypatch, tmp_path: Path) -> None:
    called = {"providers": False}

    def fake_providers() -> None:
        called["providers"] = True

    monkeypatch.setattr(cli, "print_providers", fake_providers)
    assert main(["providers"]) == 0
    assert called["providers"] is True

    checked = {}

    async def fake_doctor(path, *, live, provider_filter):
        checked.update(path=path, live=live, providers=list(provider_filter))
        return 1

    monkeypatch.setattr(cli, "run_doctor", fake_doctor)
    path = tmp_path / "config.toml"
    assert main(["doctor", "--config", str(path), "--live"]) == 1
    assert checked == {"path": path.resolve(), "live": True, "providers": []}

    def fail_providers():
        raise RuntimeError("operational failure")

    monkeypatch.setattr(cli, "print_providers", fail_providers)
    assert main(["providers"]) == 2


def test_keyboard_interrupt_exits_cleanly(monkeypatch, capsys) -> None:
    async def interrupted(_parsed):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_dispatch", interrupted)

    assert main(["providers"]) == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "\nAborted.\n"
