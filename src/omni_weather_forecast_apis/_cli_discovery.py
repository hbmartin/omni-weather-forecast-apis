from __future__ import annotations

import os
import re
import stat
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from omni_weather_forecast_apis._cli_catalog import (
    PROVIDER_CATALOG,
    supports_any,
)
from omni_weather_forecast_apis._cli_scheduling import inspect_daily_schedule
from omni_weather_forecast_apis.client import create_omni_weather
from omni_weather_forecast_apis.plugins import get_plugin_registry
from omni_weather_forecast_apis.types import (
    ForecastRequest,
    OmniWeatherConfig,
    ProviderError,
    ProviderId,
    ProviderRegistration,
)
from omni_weather_forecast_apis.utils import resolve_env_placeholders

type CheckStatus = Literal["pass", "warning", "failure"]

_ENV_REFERENCE = re.compile(r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}$")


@dataclass(frozen=True)
class DoctorCheck:
    """One safe-to-display diagnostic result."""

    status: CheckStatus
    check: str
    detail: str


@dataclass
class _DoctorState:
    """Validated state shared by static and optional live checks."""

    checks: list[DoctorCheck]
    config: OmniWeatherConfig | None = None
    invalid_providers: set[ProviderId] = field(default_factory=set)


def print_providers(*, console: Console | None = None) -> None:
    """Render the internal provider setup catalog."""

    output = console or Console()
    table = Table(title="omni-weather providers")
    table.add_column("Provider / ID", style="bold", overflow="fold")
    table.add_column("Coverage")
    table.add_column("Granularities")
    table.add_column("Authentication")
    table.add_column("Signup / setup", overflow="fold")
    for item in PROVIDER_CATALOG:
        recommendation = " [green](recommended)[/green]" if item.recommended else ""
        table.add_row(
            f"{item.name}{recommendation}\n[dim]{item.provider_id.value}[/dim]",
            item.coverage,
            item.granularity_label,
            item.authentication_label,
            item.signup_url or "—",
        )
    output.print(table)


def _safe_validation_detail(error: ValidationError) -> str:
    details: list[str] = []
    for item in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in item["loc"]) or "configuration"
        details.append(f"{location}: {item['msg']}")
    return "; ".join(details)


def _nearest_existing(path: Path) -> Path | None:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate if candidate.exists() else None


def _check_writable_path(
    checks: list[DoctorCheck],
    path: Path,
    *,
    label: str,
) -> None:
    if path.exists() and path.is_dir():
        checks.append(DoctorCheck("failure", label, f"{path} is a directory"))
        return
    if path.exists() and not os.access(path, os.W_OK):
        checks.append(DoctorCheck("failure", label, f"{path} is not writable"))
        return
    ancestor = _nearest_existing(path.parent)
    if ancestor is None or not ancestor.is_dir():
        checks.append(
            DoctorCheck("failure", label, "no existing parent directory was found"),
        )
        return
    if not os.access(ancestor, os.W_OK):
        checks.append(
            DoctorCheck("failure", label, f"parent {ancestor} is not writable"),
        )
        return
    checks.append(DoctorCheck("pass", label, str(path)))


def _check_config_path(checks: list[DoctorCheck], path: Path) -> None:
    if not path.exists():
        checks.append(DoctorCheck("failure", "Config file", f"not found: {path}"))
        return
    if not path.is_file():
        checks.append(DoctorCheck("failure", "Config file", f"not a file: {path}"))
        return
    _check_writable_path(checks, path, label="Config path")
    if os.name == "nt":
        return
    permissions = stat.S_IMODE(path.stat().st_mode)
    if permissions & (stat.S_IRWXG | stat.S_IRWXO):
        checks.append(
            DoctorCheck(
                "warning",
                "Config permissions",
                f"{path} has mode {permissions:04o}; recommended 0600",
            ),
        )
    else:
        checks.append(DoctorCheck("pass", "Config permissions", "owner-only"))


def _environment_references(value: object) -> set[str]:
    match value:
        case str() as text:
            match = _ENV_REFERENCE.fullmatch(text)
            return {match.group("name")} if match is not None else set()
        case {"env": str() as variable_name} if len(value) == 1:
            return {variable_name}
        case Mapping() as mapping:
            references: set[str] = set()
            for item in mapping.values():
                references.update(_environment_references(item))
            return references
        case list() | tuple() as items:
            references = set()
            for item in items:
                references.update(_environment_references(item))
            return references
        case _:
            return set()


def _raw_provider_entries(raw: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    providers = raw.get("providers")
    if not isinstance(providers, list):
        return []
    return [item for item in providers if isinstance(item, Mapping)]


def _selected_raw_entries(
    raw: Mapping[str, Any],
    provider_filter: frozenset[ProviderId],
) -> list[Mapping[str, Any]]:
    entries = _raw_provider_entries(raw)
    if not provider_filter:
        return entries
    selected = {item.value for item in provider_filter}
    return [item for item in entries if item.get("plugin_id") in selected]


def _check_environment(
    checks: list[DoctorCheck],
    raw: Mapping[str, Any],
    provider_filter: frozenset[ProviderId],
) -> None:
    references: set[str] = set()
    for entry in _selected_raw_entries(raw, provider_filter):
        if entry.get("enabled", True) is False:
            continue
        references.update(_environment_references(entry.get("config", {})))
    if not references:
        checks.append(DoctorCheck("pass", "Environment", "no references"))
        return
    for variable_name in sorted(references):
        status: CheckStatus = "pass" if variable_name in os.environ else "failure"
        detail = "set" if status == "pass" else "not set"
        checks.append(DoctorCheck(status, f"Environment {variable_name}", detail))


def _check_duplicates(checks: list[DoctorCheck], raw: Mapping[str, Any]) -> None:
    plugin_ids = [str(item.get("plugin_id")) for item in _raw_provider_entries(raw)]
    duplicates = sorted(item for item in set(plugin_ids) if plugin_ids.count(item) > 1)
    if duplicates:
        checks.append(
            DoctorCheck(
                "failure",
                "Provider registrations",
                f"duplicates: {', '.join(duplicates)}",
            ),
        )
    else:
        checks.append(DoctorCheck("pass", "Provider registrations", "no duplicates"))


def _enabled_registrations(
    config: OmniWeatherConfig,
    provider_filter: frozenset[ProviderId],
) -> list[ProviderRegistration]:
    return [
        registration
        for registration in config.providers
        if registration.enabled
        and (not provider_filter or registration.plugin_id in provider_filter)
    ]


def _check_provider_filter(
    checks: list[DoctorCheck],
    entries: Iterable[Mapping[str, Any]],
    provider_filter: frozenset[ProviderId],
) -> None:
    configured = {
        str(item.get("plugin_id"))
        for item in entries
        if item.get("enabled", True) is not False
    }
    for provider_id in sorted(
        (item for item in provider_filter if item.value not in configured),
        key=lambda item: item.value,
    ):
        checks.append(
            DoctorCheck(
                "failure",
                f"Provider {provider_id.value}",
                "not enabled in the configuration",
            ),
        )


def _raw_granularities(raw: Mapping[str, Any]) -> list[Any]:
    value = raw.get("granularity", ["hourly", "daily"])
    return value if isinstance(value, list) else []


def _provider_registrations(
    state: _DoctorState,
    raw: Mapping[str, Any],
    provider_filter: frozenset[ProviderId],
) -> list[ProviderRegistration]:
    entries = _raw_provider_entries(raw)
    _check_provider_filter(state.checks, entries, provider_filter)
    registrations: list[ProviderRegistration] = []
    selected = {item.value for item in provider_filter}
    for index, entry in enumerate(entries, start=1):
        if entry.get("enabled", True) is False:
            continue
        if selected and entry.get("plugin_id") not in selected:
            continue
        try:
            registration = ProviderRegistration.model_validate(entry)
        except ValidationError as exc:
            state.checks.append(
                DoctorCheck(
                    "failure",
                    f"Provider registration {index}",
                    _safe_validation_detail(exc),
                ),
            )
            continue
        registrations.append(registration)
    return registrations


def _check_provider_settings(
    state: _DoctorState,
    raw: Mapping[str, Any],
    provider_filter: frozenset[ProviderId],
) -> None:
    registry = get_plugin_registry()
    granularities = _raw_granularities(raw)
    for registration in _provider_registrations(state, raw, provider_filter):
        provider_id = registration.plugin_id
        plugin = registry.get(provider_id)
        if plugin is None:
            state.checks.append(
                DoctorCheck(
                    "failure", f"Provider {provider_id.value}", "not registered"
                ),
            )
            state.invalid_providers.add(provider_id)
            continue
        try:
            resolved = resolve_env_placeholders(registration.config)
            plugin.validate_config(resolved)
        except ValidationError as exc:
            state.checks.append(
                DoctorCheck(
                    "failure",
                    f"Provider {provider_id.value}",
                    _safe_validation_detail(exc),
                ),
            )
            state.invalid_providers.add(provider_id)
            continue
        except LookupError:
            state.checks.append(
                DoctorCheck(
                    "failure",
                    f"Provider {provider_id.value}",
                    "an environment reference is not set",
                ),
            )
            state.invalid_providers.add(provider_id)
            continue
        except (TypeError, ValueError) as exc:
            state.checks.append(
                DoctorCheck(
                    "failure",
                    f"Provider {provider_id.value}",
                    f"invalid settings ({type(exc).__name__})",
                ),
            )
            state.invalid_providers.add(provider_id)
            continue
        try:
            supported = supports_any(provider_id, granularities)
        except KeyError:
            supported = False
        if not supported:
            requested = ", ".join(str(item) for item in granularities) or "none"
            state.checks.append(
                DoctorCheck(
                    "failure",
                    f"Provider {provider_id.value} granularities",
                    f"none supported from: {requested}",
                ),
            )
            state.invalid_providers.add(provider_id)
            continue
        state.checks.append(
            DoctorCheck("pass", f"Provider {provider_id.value}", "settings valid"),
        )


def _check_coordinates(checks: list[DoctorCheck], raw: Mapping[str, Any]) -> None:
    latitude = raw.get("latitude")
    longitude = raw.get("longitude")
    if latitude is None or longitude is None:
        checks.append(
            DoctorCheck(
                "failure", "Coordinates", "latitude and longitude are required"
            ),
        )
        return
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, int | float)
        or not -90 <= latitude <= 90
        or isinstance(longitude, bool)
        or not isinstance(longitude, int | float)
        or not -180 <= longitude <= 180
    ):
        checks.append(DoctorCheck("failure", "Coordinates", "values are out of range"))
        return
    checks.append(DoctorCheck("pass", "Coordinates", f"{latitude:g}, {longitude:g}"))


def _check_sqlite_path(checks: list[DoctorCheck], raw: Mapping[str, Any]) -> None:
    sqlite_value = raw.get("sqlite")
    if sqlite_value is None:
        checks.append(
            DoctorCheck(
                "warning", "SQLite path", "not configured; output is not persisted"
            ),
        )
        return
    if not isinstance(sqlite_value, str):
        checks.append(DoctorCheck("failure", "SQLite path", "must be a string path"))
        return
    _check_writable_path(
        checks,
        Path(sqlite_value).expanduser().resolve(),
        label="SQLite path",
    )


def _check_top_level(state: _DoctorState, raw: Mapping[str, Any]) -> None:
    try:
        state.config = OmniWeatherConfig.model_validate(raw)
    except ValidationError as exc:
        state.checks.append(
            DoctorCheck(
                "failure", "Configuration schema", _safe_validation_detail(exc)
            ),
        )
        return
    state.checks.append(DoctorCheck("pass", "Configuration schema", "valid"))


def _check_daily_schedule(checks: list[DoctorCheck], path: Path) -> None:
    inspection = inspect_daily_schedule(path)
    status: CheckStatus = "pass" if inspection.installed else "warning"
    checks.append(DoctorCheck(status, "Daily schedule", inspection.detail))


def _static_checks(
    path: Path,
    provider_filter: frozenset[ProviderId],
) -> _DoctorState:
    path = path.expanduser().resolve()
    state = _DoctorState(checks=[])
    _check_config_path(state.checks, path)
    if not path.is_file():
        return state
    _check_daily_schedule(state.checks, path)
    try:
        with path.open("rb") as file_pointer:
            raw = tomllib.load(file_pointer)
    except tomllib.TOMLDecodeError:
        state.checks.append(
            DoctorCheck("failure", "TOML", "could not be parsed"),
        )
        return state
    except OSError as exc:
        state.checks.append(
            DoctorCheck("failure", "TOML", f"could not read ({type(exc).__name__})"),
        )
        return state
    state.checks.append(DoctorCheck("pass", "TOML", "parsed"))
    _check_duplicates(state.checks, raw)
    _check_environment(state.checks, raw, provider_filter)
    _check_coordinates(state.checks, raw)
    _check_sqlite_path(state.checks, raw)
    _check_top_level(state, raw)
    _check_provider_settings(state, raw, provider_filter)
    return state


async def _live_checks(
    state: _DoctorState,
    provider_filter: frozenset[ProviderId],
) -> None:
    config = state.config
    if config is None or config.latitude is None or config.longitude is None:
        state.checks.append(
            DoctorCheck("failure", "Live checks", "valid coordinates are required"),
        )
        return
    registrations = [
        item
        for item in _enabled_registrations(config, provider_filter)
        if item.plugin_id not in state.invalid_providers
    ]
    if not registrations:
        state.checks.append(
            DoctorCheck(
                "failure", "Live checks", "no statically valid providers selected"
            ),
        )
        return
    live_config = config.model_copy(update={"providers": registrations, "sqlite": None})
    request = ForecastRequest(
        latitude=config.latitude,
        longitude=config.longitude,
        granularity=config.granularity,
        language=config.language,
        include_raw=False,
        providers=[item.plugin_id for item in registrations],
        timeout_ms=config.default_timeout_ms,
    )
    async with await create_omni_weather(live_config) as client:
        response = await client.forecast(request)
    for result in response.results:
        if isinstance(result, ProviderError):
            state.checks.append(
                DoctorCheck(
                    "failure",
                    f"Live {result.provider.value}",
                    f"{result.error.code.value}: {result.error.message}",
                ),
            )
        else:
            state.checks.append(
                DoctorCheck(
                    "pass", f"Live {result.provider.value}", "forecast succeeded"
                ),
            )


def _print_doctor(checks: Iterable[DoctorCheck], console: Console) -> None:
    table = Table(title="omni-weather doctor")
    table.add_column("Status", justify="center")
    table.add_column("Check", style="bold")
    table.add_column("Detail")
    labels = {
        "pass": "[green]PASS[/green]",
        "warning": "[yellow]WARN[/yellow]",
        "failure": "[red]FAIL[/red]",
    }
    for check in checks:
        table.add_row(labels[check.status], check.check, check.detail)
    console.print(table)


async def run_doctor(
    path: Path,
    *,
    live: bool,
    provider_filter: Iterable[ProviderId] = (),
    console: Console | None = None,
) -> int:
    """Run aggregated static diagnostics and optional provider API checks."""

    selected = frozenset(provider_filter)
    state = _static_checks(path, selected)
    if live:
        await _live_checks(state, selected)
    _print_doctor(state.checks, console or Console())
    return 1 if any(item.status == "failure" for item in state.checks) else 0


__all__ = ["DoctorCheck", "print_providers", "run_doctor"]
