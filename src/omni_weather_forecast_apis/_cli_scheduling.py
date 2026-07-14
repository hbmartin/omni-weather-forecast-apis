from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Literal, cast

import platformdirs

from omni_weather_forecast_apis._cli_paths import normalized_path

type SchedulerKind = Literal["cron", "launchd", "task-scheduler"]

_APP_NAME = "omni-weather"
_MODULE_NAME = "omni_weather_forecast_apis"
_MANIFEST_VERSION = 1


class ScheduleError(RuntimeError):
    """Raised when a platform scheduler cannot install a daily job."""


@dataclass(frozen=True)
class ScheduleSpec:
    """Stable platform scheduling details for one configuration file."""

    kind: SchedulerKind
    key: str
    config_path: Path
    run_at: time
    command: tuple[str, ...]
    log_path: Path


@dataclass(frozen=True)
class ScheduleInspection:
    """Doctor-facing status for a configured daily schedule."""

    installed: bool
    detail: str


def scheduler_kind(
    *,
    platform: str | None = None,
    operating_system: str | None = None,
) -> SchedulerKind:
    """Return the scheduler native to the current platform."""

    selected_platform = platform or sys.platform
    selected_os = operating_system or os.name
    match selected_platform, selected_os:
        case "darwin", _:
            return "launchd"
        case _, "nt":
            return "task-scheduler"
        case _:
            return "cron"


def scheduler_name(kind: SchedulerKind | None = None) -> str:
    """Return a user-facing platform scheduler name."""

    match kind or scheduler_kind():
        case "launchd":
            return "launchd"
        case "task-scheduler":
            return "Windows Task Scheduler"
        case "cron":
            return "cron"


def _schedule_key(config_path: Path) -> str:
    digest = hashlib.sha256(str(config_path).encode()).hexdigest()[:12]
    return f"omni-weather-{digest}"


def _log_directory() -> Path:
    return platformdirs.user_log_path(_APP_NAME, appauthor=False)


def _schedule_directory() -> Path:
    return platformdirs.user_data_path(_APP_NAME, appauthor=False) / "schedules"


def build_schedule_spec(
    config_path: Path,
    run_at: time,
    *,
    kind: SchedulerKind | None = None,
) -> ScheduleSpec:
    """Build a platform schedule without changing external state."""

    resolved_path = normalized_path(config_path)
    key = _schedule_key(resolved_path)
    return ScheduleSpec(
        kind=kind or scheduler_kind(),
        key=key,
        config_path=resolved_path,
        run_at=run_at,
        command=(
            sys.executable,
            "-m",
            _MODULE_NAME,
            "--config",
            str(resolved_path),
        ),
        log_path=_log_directory() / f"{key}.log",
    )


def _manifest_path(config_path: Path) -> Path:
    return _schedule_directory() / f"{_schedule_key(normalized_path(config_path))}.json"


def _launchd_label(spec: ScheduleSpec) -> str:
    return f"io.github.hbmartin.{spec.key}"


def _launchd_path(spec: ScheduleSpec) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_launchd_label(spec)}.plist"


def _task_name(spec: ScheduleSpec) -> str:
    return f"OmniWeather Daily {spec.key.removeprefix('omni-weather-')}"


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(0o600)
        temporary_path.replace(path)
        path.chmod(0o600)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _run_command(
    command: tuple[str, ...],
    *,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which(command[0])
    if executable is None:
        raise ScheduleError(f"{command[0]} is not available")
    resolved_command = (executable, *command[1:])
    try:
        result = subprocess.run(  # noqa: S603 - executable is resolved above.
            resolved_command,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ScheduleError(f"could not run {command[0]}: {exc}") from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise ScheduleError(f"{command[0]}: {detail}")
    return result


def _install_launchd(spec: ScheduleSpec) -> str:
    label = _launchd_label(spec)
    plist_path = _launchd_path(spec)
    error_log = spec.log_path.with_suffix(".error.log")
    payload = plistlib.dumps(
        {
            "Label": label,
            "ProgramArguments": list(spec.command),
            "StartCalendarInterval": {
                "Hour": spec.run_at.hour,
                "Minute": spec.run_at.minute,
            },
            "StandardOutPath": str(spec.log_path),
            "StandardErrorPath": str(error_log),
        },
    )
    _atomic_write(plist_path, payload)
    domain = f"gui/{os.getuid()}"
    _run_command(("launchctl", "bootout", f"{domain}/{label}"), check=False)
    _run_command(("launchctl", "bootstrap", domain, str(plist_path)))
    return str(plist_path)


def _cron_markers(spec: ScheduleSpec) -> tuple[str, str]:
    return f"# BEGIN {spec.key}", f"# END {spec.key}"


def _without_managed_cron_block(crontab: str, spec: ScheduleSpec) -> str:
    begin, end = _cron_markers(spec)
    lines = crontab.splitlines()
    try:
        start = lines.index(begin)
    except ValueError:
        return crontab.rstrip()
    try:
        stop = lines.index(end, start + 1)
    except ValueError as exc:
        raise ScheduleError(f"managed cron block for {spec.key} is incomplete") from exc
    return "\n".join((*lines[:start], *lines[stop + 1 :])).rstrip()


def _managed_crontab(crontab: str, spec: ScheduleSpec) -> str:
    existing = _without_managed_cron_block(crontab, spec)
    begin, end = _cron_markers(spec)
    command = shlex.join(spec.command)
    cron_line = (
        f"{spec.run_at.minute} {spec.run_at.hour} * * * {command} "
        f">> {shlex.quote(str(spec.log_path))} 2>&1"
    )
    prefix = f"{existing}\n" if existing else ""
    return f"{prefix}{begin}\n{cron_line}\n{end}\n"


def _install_cron(spec: ScheduleSpec) -> str:
    current = _run_command(("crontab", "-l"), check=False)
    if current.returncode not in {0, 1}:
        detail = current.stderr.strip() or "could not read the user crontab"
        raise ScheduleError(f"crontab: {detail}")
    updated = _managed_crontab(current.stdout if current.returncode == 0 else "", spec)
    _run_command(("crontab", "-"), input_text=updated)
    return spec.key


def _install_task_scheduler(spec: ScheduleSpec) -> str:
    task_name = _task_name(spec)
    command_line = subprocess.list2cmdline(spec.command)
    run_at = spec.run_at.strftime("%H:%M")
    _run_command(
        (
            "schtasks",
            "/Create",
            "/TN",
            task_name,
            "/TR",
            command_line,
            "/SC",
            "DAILY",
            "/ST",
            run_at,
            "/F",
        ),
    )
    return task_name


def _write_manifest(spec: ScheduleSpec, artifact: str) -> None:
    payload = json.dumps(
        {
            "version": _MANIFEST_VERSION,
            "kind": spec.kind,
            "key": spec.key,
            "config_path": str(spec.config_path),
            "hour": spec.run_at.hour,
            "minute": spec.run_at.minute,
            "artifact": artifact,
        },
        indent=2,
        sort_keys=True,
    ).encode()
    _atomic_write(_manifest_path(spec.config_path), payload)


def _schedule_detail(spec: ScheduleSpec) -> str:
    clock = spec.run_at.strftime("%H:%M")
    return f"{scheduler_name(spec.kind)} daily at {clock} local time"


def install_daily_schedule(config_path: Path, run_at: time) -> ScheduleInspection:
    """Install or replace a daily platform-native schedule for a config."""

    spec = build_schedule_spec(config_path, run_at)
    spec.log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    match spec.kind:
        case "launchd":
            artifact = _install_launchd(spec)
        case "task-scheduler":
            artifact = _install_task_scheduler(spec)
        case "cron":
            artifact = _install_cron(spec)
    _write_manifest(spec, artifact)
    return ScheduleInspection(installed=True, detail=_schedule_detail(spec))


def _load_manifest(config_path: Path) -> dict[str, object] | None:
    path = _manifest_path(config_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _spec_from_manifest(
    config_path: Path,
    payload: dict[str, object],
) -> ScheduleSpec | None:
    version = payload.get("version")
    kind_value = payload.get("kind")
    key = payload.get("key")
    stored_value = payload.get("config_path")
    hour = payload.get("hour")
    minute = payload.get("minute")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or not isinstance(key, str)
        or not isinstance(stored_value, str)
        or not isinstance(hour, int)
        or isinstance(hour, bool)
        or not isinstance(minute, int)
        or isinstance(minute, bool)
    ):
        return None
    match kind_value:
        case "cron" | "launchd" | "task-scheduler":
            kind = cast(SchedulerKind, kind_value)
        case _:
            return None
    try:
        stored_path = normalized_path(stored_value)
        run_at = time(hour=hour, minute=minute)
    except ValueError:
        return None
    if (
        version != _MANIFEST_VERSION
        or stored_path != normalized_path(config_path)
        or key != _schedule_key(stored_path)
    ):
        return None
    return build_schedule_spec(stored_path, run_at, kind=kind)


def _launchd_is_installed(spec: ScheduleSpec) -> bool:
    if not _launchd_path(spec).is_file():
        return False
    domain = f"gui/{os.getuid()}"
    result = _run_command(
        ("launchctl", "print", f"{domain}/{_launchd_label(spec)}"),
        check=False,
    )
    return result.returncode == 0


def _cron_is_installed(spec: ScheduleSpec) -> bool:
    result = _run_command(("crontab", "-l"), check=False)
    begin, end = _cron_markers(spec)
    return result.returncode == 0 and begin in result.stdout and end in result.stdout


def _task_is_installed(spec: ScheduleSpec) -> bool:
    result = _run_command(
        ("schtasks", "/Query", "/TN", _task_name(spec)),
        check=False,
    )
    return result.returncode == 0


def _backend_is_installed(spec: ScheduleSpec) -> bool:
    match spec.kind:
        case "launchd":
            return _launchd_is_installed(spec)
        case "task-scheduler":
            return _task_is_installed(spec)
        case "cron":
            return _cron_is_installed(spec)


def _missing_detail(config_path: Path) -> str:
    return f"not configured; rerun omni-weather init --config {config_path}"


def inspect_daily_schedule(config_path: Path) -> ScheduleInspection:
    """Inspect scheduler state without contacting weather providers."""

    resolved_path = normalized_path(config_path)
    payload = _load_manifest(resolved_path)
    if payload is None:
        return ScheduleInspection(
            installed=False,
            detail=_missing_detail(resolved_path),
        )
    if (spec := _spec_from_manifest(resolved_path, payload)) is None:
        return ScheduleInspection(
            installed=False,
            detail="schedule metadata is invalid; rerun omni-weather init",
        )
    if spec.kind != scheduler_kind():
        return ScheduleInspection(
            installed=False,
            detail="schedule belongs to a different platform; rerun omni-weather init",
        )
    try:
        installed = _backend_is_installed(spec)
    except ScheduleError as exc:
        return ScheduleInspection(
            installed=False,
            detail=f"could not inspect {scheduler_name()}: {exc}",
        )
    if not installed:
        return ScheduleInspection(
            installed=False,
            detail=(
                f"{scheduler_name(spec.kind)} job is missing or inactive; rerun init"
            ),
        )
    return ScheduleInspection(installed=True, detail=_schedule_detail(spec))


__all__ = [
    "ScheduleError",
    "ScheduleInspection",
    "ScheduleSpec",
    "build_schedule_spec",
    "inspect_daily_schedule",
    "install_daily_schedule",
    "scheduler_kind",
    "scheduler_name",
]
