from __future__ import annotations

import json
import plistlib
import stat
import subprocess
from datetime import time
from pathlib import Path

import pytest

from omni_weather_forecast_apis import _cli_scheduling as scheduling
from omni_weather_forecast_apis._cli_scheduling import (
    ScheduleError,
    build_schedule_spec,
    inspect_daily_schedule,
    install_daily_schedule,
    scheduler_kind,
    scheduler_name,
)


def _completed(
    command: tuple[str, ...],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def _redirect_platform_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(scheduling, "_log_directory", lambda: tmp_path / "logs")
    monkeypatch.setattr(
        scheduling,
        "_schedule_directory",
        lambda: tmp_path / "schedules",
    )


def test_scheduler_selection_and_stable_spec(monkeypatch, tmp_path: Path) -> None:
    _redirect_platform_paths(monkeypatch, tmp_path)
    config_path = tmp_path / "config.toml"

    assert scheduler_kind(platform="darwin", operating_system="posix") == "launchd"
    assert scheduler_kind(platform="win32", operating_system="nt") == "task-scheduler"
    assert scheduler_kind(platform="linux", operating_system="posix") == "cron"
    assert scheduler_name("launchd") == "launchd"
    assert scheduler_name("task-scheduler") == "Windows Task Scheduler"
    assert scheduler_name("cron") == "cron"

    first = build_schedule_spec(config_path, time(hour=6), kind="cron")
    second = build_schedule_spec(config_path, time(hour=7), kind="cron")

    assert first.key == second.key
    assert first.config_path == config_path.resolve()
    assert first.command[-2:] == ("--config", str(config_path.resolve()))
    assert first.log_path.parent == tmp_path / "logs"


def test_cron_install_replaces_managed_block_and_inspects(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _redirect_platform_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduling, "scheduler_kind", lambda: "cron")
    crontab = {"text": "MAILTO=ops@example.org\n"}

    def fake_run(command, *, input_text=None, check=True):
        del check
        if command == ("crontab", "-l"):
            return _completed(command, stdout=crontab["text"])
        assert command == ("crontab", "-")
        assert input_text is not None
        crontab["text"] = input_text
        return _completed(command)

    monkeypatch.setattr(scheduling, "_run_command", fake_run)
    config_path = tmp_path / "config.toml"

    first = install_daily_schedule(config_path, time(hour=6, minute=15))
    second = install_daily_schedule(config_path, time(hour=7, minute=45))

    assert first.installed is True
    assert second.detail == "cron daily at 07:45 local time"
    assert crontab["text"].startswith("MAILTO=ops@example.org\n")
    assert "45 7 * * *" in crontab["text"]
    assert crontab["text"].count("# BEGIN omni-weather-") == 1
    assert inspect_daily_schedule(config_path).installed is True
    manifest = scheduling._manifest_path(config_path)
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600

    crontab["text"] = "MAILTO=ops@example.org\n"
    missing = inspect_daily_schedule(config_path)
    assert missing.installed is False
    assert "missing or inactive" in missing.detail


def test_cron_install_handles_empty_crontab_and_read_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _redirect_platform_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduling, "scheduler_kind", lambda: "cron")
    installed = {}

    def no_crontab(command, *, input_text=None, check=True):
        del check
        if command == ("crontab", "-l"):
            return _completed(command, returncode=1, stderr="no crontab")
        installed["text"] = input_text
        return _completed(command)

    monkeypatch.setattr(scheduling, "_run_command", no_crontab)
    install_daily_schedule(tmp_path / "config.toml", time(hour=0))
    assert str(installed["text"]).startswith("# BEGIN omni-weather-")

    monkeypatch.setattr(
        scheduling,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ("crontab", "-l"),
            returncode=2,
            stderr="permission denied",
        ),
    )
    with pytest.raises(ScheduleError, match="permission denied"):
        install_daily_schedule(tmp_path / "other.toml", time(hour=0))


def test_incomplete_managed_cron_block_is_rejected(monkeypatch, tmp_path: Path) -> None:
    _redirect_platform_paths(monkeypatch, tmp_path)
    spec = build_schedule_spec(tmp_path / "config.toml", time(hour=6), kind="cron")
    begin, _end = scheduling._cron_markers(spec)

    with pytest.raises(ScheduleError, match="incomplete"):
        scheduling._managed_crontab(f"{begin}\n0 6 * * * command\n", spec)


def test_launchd_install_writes_plist_loads_and_inspects(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _redirect_platform_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduling, "scheduler_kind", lambda: "launchd")
    plist_path = tmp_path / "LaunchAgents" / "omni-weather.plist"
    monkeypatch.setattr(scheduling, "_launchd_path", lambda _spec: plist_path)
    commands = []

    def fake_run(command, *, input_text=None, check=True):
        del input_text, check
        commands.append(command)
        return _completed(command)

    monkeypatch.setattr(scheduling, "_run_command", fake_run)
    config_path = tmp_path / "config.toml"

    installed = install_daily_schedule(config_path, time(hour=8, minute=5))

    payload = plistlib.loads(plist_path.read_bytes())
    assert installed.detail == "launchd daily at 08:05 local time"
    assert payload["StartCalendarInterval"] == {"Hour": 8, "Minute": 5}
    assert payload["ProgramArguments"][-1] == str(config_path.resolve())
    assert commands[0][1] == "bootout"
    assert commands[1][1] == "bootstrap"
    assert inspect_daily_schedule(config_path).installed is True
    assert commands[-1][1] == "print"

    plist_path.unlink()
    assert inspect_daily_schedule(config_path).installed is False


def test_task_scheduler_install_and_inspection(monkeypatch, tmp_path: Path) -> None:
    _redirect_platform_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduling, "scheduler_kind", lambda: "task-scheduler")
    commands = []

    def fake_run(command, *, input_text=None, check=True):
        del input_text, check
        commands.append(command)
        return _completed(command)

    monkeypatch.setattr(scheduling, "_run_command", fake_run)
    config_path = tmp_path / "config.toml"

    installed = install_daily_schedule(config_path, time(hour=9, minute=30))
    inspection = inspect_daily_schedule(config_path)

    assert installed.detail == "Windows Task Scheduler daily at 09:30 local time"
    assert inspection.installed is True
    assert commands[0][0:2] == ("schtasks", "/Create")
    assert commands[0][commands[0].index("/ST") + 1] == "09:30"
    assert commands[-1][0:2] == ("schtasks", "/Query")


def test_schedule_inspection_handles_missing_invalid_and_foreign_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _redirect_platform_paths(monkeypatch, tmp_path)
    config_path = tmp_path / "config.toml"

    missing = inspect_daily_schedule(config_path)
    assert missing.installed is False
    assert "not configured" in missing.detail

    manifest = scheduling._manifest_path(config_path)
    manifest.parent.mkdir(parents=True)
    manifest.write_text("not json")
    invalid = inspect_daily_schedule(config_path)
    assert invalid.installed is False
    assert "metadata is invalid" in invalid.detail

    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "cron",
                "key": scheduling._schedule_key(config_path.resolve()),
                "config_path": str(config_path.resolve()),
                "hour": 6,
                "minute": 0,
                "artifact": "unused",
            },
        ),
    )
    monkeypatch.setattr(scheduling, "scheduler_kind", lambda: "launchd")
    foreign = inspect_daily_schedule(config_path)
    assert foreign.installed is False
    assert "different platform" in foreign.detail


def test_schedule_inspection_reports_backend_errors(
    monkeypatch, tmp_path: Path
) -> None:
    _redirect_platform_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduling, "scheduler_kind", lambda: "cron")
    config_path = tmp_path / "config.toml"
    spec = build_schedule_spec(config_path, time(hour=6), kind="cron")
    scheduling._write_manifest(spec, spec.key)
    monkeypatch.setattr(
        scheduling,
        "_run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ScheduleError("crontab unavailable"),
        ),
    )

    inspection = inspect_daily_schedule(config_path)

    assert inspection.installed is False
    assert "could not inspect cron" in inspection.detail


def test_run_command_reports_missing_and_failed_executables(monkeypatch) -> None:
    monkeypatch.setattr(scheduling.shutil, "which", lambda _name: None)
    with pytest.raises(ScheduleError, match="not available"):
        scheduling._run_command(("missing-scheduler", "--version"))

    monkeypatch.setattr(scheduling.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        scheduling.subprocess,
        "run",
        lambda *_args, **_kwargs: _completed(
            ("scheduler",),
            returncode=1,
            stderr="failed",
        ),
    )
    with pytest.raises(ScheduleError, match="failed"):
        scheduling._run_command(("scheduler", "--install"))
