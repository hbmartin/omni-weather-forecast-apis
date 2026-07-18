from __future__ import annotations

import stat
import tomllib
from dataclasses import replace
from datetime import time
from pathlib import Path

from rich.syntax import Syntax

from omni_weather_forecast_apis import _cli_setup as setup
from omni_weather_forecast_apis._cli_catalog import PROVIDER_BY_ID
from omni_weather_forecast_apis._cli_scheduling import (
    ScheduleError,
    ScheduleInspection,
)
from omni_weather_forecast_apis._cli_setup import InitDefaults, run_init
from omni_weather_forecast_apis.types import Granularity, ProviderId


class FakePrompts:
    def __init__(self, answers, confirmations) -> None:
        self.answers = iter(answers)
        self.confirmations = iter(confirmations)
        self.printed: list[object] = []
        self.questions: list[tuple[str, bool]] = []

    def print(self, value: object = "") -> None:
        self.printed.append(value)

    def ask(
        self,
        prompt: str,
        *,
        default: str | None = None,
        password: bool = False,
    ) -> str:
        self.questions.append((prompt, password))
        value = next(self.answers)
        return default or "" if value is None else value

    def confirm(self, prompt: str, *, default: bool) -> bool:
        del prompt, default
        return next(self.confirmations)


def _syntax_text(prompts: FakePrompts) -> str:
    preview = next(item for item in prompts.printed if isinstance(item, Syntax))
    return preview.code


def test_wizard_defaults_to_open_meteo_and_writes_exact_preview(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "private" / "config.toml"
    sqlite_path = tmp_path / "data" / "forecasts.sqlite"
    prompts = FakePrompts(
        ["34.2", "-117.2", None, str(sqlite_path), None],
        [True, False, False],
    )

    result = run_init(config_path, automatic=False, prompts=prompts)

    assert result is not None
    assert result.run_forecast is False
    assert config_path.read_text() == _syntax_text(prompts)
    raw = tomllib.loads(config_path.read_text())
    assert raw["providers"] == [{"plugin_id": "open_meteo", "config": {}}]
    assert raw["granularity"] == ["hourly", "daily"]
    assert raw["sqlite"] == str(sqlite_path.resolve())
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(config_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(sqlite_path.parent.stat().st_mode) == 0o700
    assert any("credential values" in str(item) for item in prompts.printed)


def test_wizard_uses_one_identity_for_met_norway_and_nws(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    prompts = FakePrompts(
        [
            "59.9",
            "10.7",
            "2,3",
            "WeatherLab",
            "ops@example.org",
            str(tmp_path / "forecast.sqlite"),
            "hourly",
        ],
        [True, False, False],
    )

    result = run_init(config_path, automatic=False, prompts=prompts)

    assert result is not None
    configs = {item.plugin_id: item.config for item in result.config.providers}
    expected = "WeatherLab/1.0 ops@example.org"
    assert configs[ProviderId.MET_NORWAY]["user_agent"] == expected
    assert configs[ProviderId.NWS]["user_agent"] == expected
    assert sum(question == "Application name" for question, _ in prompts.questions) == 1
    assert sum(question == "Contact email" for question, _ in prompts.questions) == 1


def test_wizard_collects_visible_nbm_station_id(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "forecast.sqlite"
    prompts = FakePrompts(
        ["34.2", "-117.2", "4", "KSBD", str(sqlite_path), "hourly"],
        [True, False, False],
    )

    result = run_init(tmp_path / "config.toml", automatic=False, prompts=prompts)

    assert result is not None
    assert result.config.providers[0].plugin_id == ProviderId.NBM
    assert result.config.providers[0].config == {"station_id": "KSBD"}
    assert ("NOAA NBM Station ID", False) in prompts.questions


def test_wizard_groups_catalog_without_positional_assumptions() -> None:
    prompts = FakePrompts([], [])

    setup._print_provider_choices(prompts)

    output = "\n".join(str(item) for item in prompts.printed)
    assert "4. NOAA NBM — US only, hourly" in output
    assert "5. OpenWeather — Global, minutely, hourly, daily" in output
    assert output.index("NOAA NBM") < output.index("Requires credentials")
    assert output.index("Requires credentials") < output.index("OpenWeather")


def test_wizard_collects_every_keyed_credential_shape(tmp_path: Path) -> None:
    keyed_ids = tuple(
        ProviderId(item)
        for item in [
            "openweather",
            "weatherapi",
            "tomorrow_io",
            "visual_crossing",
            "weatherbit",
            "meteosource",
            "pirate_weather",
            "stormglass",
            "google_weather",
            "met_office",
            "xweather",
        ]
    )
    secrets = [f"secret-{index}" for index in range(1, 13)]
    prompts = FakePrompts(
        [
            "1",
            "2",
            ",".join(str(index) for index in range(5, 16)),
            *secrets,
            str(tmp_path / "forecast.sqlite"),
            "hourly,daily",
        ],
        [True, False, False],
    )

    result = run_init(tmp_path / "config.toml", automatic=False, prompts=prompts)

    assert result is not None
    configs = {item.plugin_id: item.config for item in result.config.providers}
    assert set(configs) == set(keyed_ids)
    assert configs[ProviderId.MET_OFFICE] == {"api_key": secrets[9]}
    assert configs[ProviderId.XWEATHER] == {
        "client_id": secrets[10],
        "client_secret": secrets[11],
    }
    credential_questions = [item for item in prompts.questions if item[1]]
    assert len(credential_questions) == 12
    preview = _syntax_text(prompts)
    assert all(secret in preview for secret in secrets)


def test_wizard_reprompts_for_invalid_required_values(tmp_path: Path) -> None:
    directory_path = tmp_path / "not-a-database"
    directory_path.mkdir()
    prompts = FakePrompts(
        [
            "north",
            "91",
            "40",
            "west",
            "-75",
            "2",
            "WeatherLab",
            "invalid-email",
            "weather@example.org",
            str(directory_path),
            str(tmp_path / "forecast.sqlite"),
            "daily",
            "hourly",
        ],
        [True, False, False],
    )

    result = run_init(tmp_path / "config.toml", automatic=False, prompts=prompts)

    assert result is not None
    assert result.config.latitude == 40
    assert result.config.longitude == -75
    assert result.config.granularity == [Granularity.HOURLY]
    output = "\n".join(str(item) for item in prompts.printed)
    assert "must be a number" in output
    assert "must be between -90 and 90" in output
    assert "containing '@'" in output
    assert "cannot be a directory" in output
    assert "No selected granularity is supported by" in output


def test_cancelled_overwrite_leaves_everything_unchanged(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("keep me")
    sqlite_path = tmp_path / "not-created" / "forecast.sqlite"
    prompts = FakePrompts(
        ["0", "0", "1", str(sqlite_path), "hourly"],
        [False],
    )

    result = run_init(config_path, automatic=True, prompts=prompts)

    assert result is None
    assert config_path.read_text() == "keep me"
    assert not sqlite_path.parent.exists()
    assert any("No changes made" in str(item) for item in prompts.printed)


def test_confirmed_overwrite_reprompts_empty_choices_and_defaults_test_to_yes(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("old configuration")
    sqlite_path = tmp_path / "forecast.sqlite"
    prompts = FakePrompts(
        [
            "0",
            "0",
            "",
            "1",
            "",
            str(sqlite_path),
            "",
            "hourly",
        ],
        [True, False, True],
    )

    result = run_init(config_path, automatic=False, prompts=prompts)

    assert result is not None
    assert result.run_forecast is True
    assert "old configuration" not in config_path.read_text()
    output = "\n".join(str(item) for item in prompts.printed)
    assert "Choose at least one listed provider" in output
    assert "SQLite output path is required" in output
    assert "Choose at least one listed granularity" in output


def test_automatic_wizard_carries_forecast_overrides(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "override.sqlite"
    defaults = InitDefaults(
        latitude=12.5,
        longitude=-13.5,
        sqlite=sqlite_path,
        granularities=(Granularity.MINUTELY,),
        providers=(ProviderId.OPEN_METEO,),
    )
    prompts = FakePrompts([None, None, None, None, None], [True, False])

    result = run_init(
        tmp_path / "config.toml",
        defaults=defaults,
        automatic=True,
        prompts=prompts,
    )

    assert result is not None
    assert result.run_forecast is True
    assert result.config.latitude == 12.5
    assert result.config.longitude == -13.5
    assert result.config.sqlite == str(sqlite_path.resolve())
    assert result.config.granularity == [Granularity.MINUTELY]


def test_identity_prompts_follow_catalog_authentication(monkeypatch) -> None:
    provider = replace(
        PROVIDER_BY_ID[ProviderId.OPEN_METEO],
        authentication="identity",
    )
    monkeypatch.setattr(setup, "PROVIDER_CATALOG", (provider,))
    monkeypatch.setattr(setup, "PROVIDER_BY_ID", {ProviderId.OPEN_METEO: provider})
    prompts = FakePrompts(["WeatherLab", "ops@example.org"], [])

    configs = setup._prompt_provider_configs(prompts, (ProviderId.OPEN_METEO,))

    assert configs == {
        ProviderId.OPEN_METEO: {
            "user_agent": "WeatherLab/1.0 ops@example.org",
        },
    }


def test_wizard_offers_platform_schedule_and_reprompts_for_time(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    sqlite_path = tmp_path / "forecast.sqlite"
    prompts = FakePrompts(
        [
            "34.2",
            "-117.2",
            "1",
            str(sqlite_path),
            "hourly",
            "25:00",
            "07:30",
        ],
        [True, True, False],
    )
    seen = {}

    def fake_install(path, run_at):
        seen.update(path=path, run_at=run_at)
        return ScheduleInspection(installed=True, detail="test schedule")

    monkeypatch.setattr(setup, "scheduler_name", lambda: "test scheduler")
    monkeypatch.setattr(setup, "install_daily_schedule", fake_install)

    result = run_init(config_path, automatic=False, prompts=prompts)

    assert result is not None
    assert result.run_forecast is False
    assert seen == {"path": config_path, "run_at": time(hour=7, minute=30)}
    output = "\n".join(str(item) for item in prompts.printed)
    assert "valid local time" in output
    assert "Installed test schedule" in output


def test_wizard_reports_schedule_install_failure(monkeypatch, tmp_path: Path) -> None:
    prompts = FakePrompts(
        ["0", "0", "1", str(tmp_path / "forecast.sqlite"), "hourly", "06:00"],
        [True, True, False],
    )

    def fail_install(path, run_at):
        del path, run_at
        raise ScheduleError("scheduler unavailable")

    monkeypatch.setattr(setup, "install_daily_schedule", fail_install)

    result = run_init(
        tmp_path / "config.toml",
        automatic=False,
        prompts=prompts,
    )

    assert result is not None
    output = "\n".join(str(item) for item in prompts.printed)
    assert "Could not install the daily schedule" in output
    assert "omni-weather doctor" in output


def test_atomic_write_cleans_temporary_file_on_replace_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    def fail_replace(self, target):
        del self, target
        raise OSError("replace failed")

    monkeypatch.setattr(setup.Path, "replace", fail_replace)

    try:
        setup._atomic_write(config_path, "value = 1\n", tmp_path / "data.sqlite")
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError")

    assert not config_path.exists()
    assert list(tmp_path.glob(".config.toml.*.tmp")) == []
