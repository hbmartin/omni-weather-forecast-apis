from __future__ import annotations

import os
import re
import stat
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Protocol

import tomli_w
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax

from omni_weather_forecast_apis._cli_catalog import (
    PROVIDER_BY_ID,
    PROVIDER_CATALOG,
    supports_any,
)
from omni_weather_forecast_apis._cli_paths import default_sqlite_path, normalized_path
from omni_weather_forecast_apis._cli_scheduling import (
    ScheduleError,
    install_daily_schedule,
    scheduler_name,
)
from omni_weather_forecast_apis.plugins import get_plugin_registry
from omni_weather_forecast_apis.types import (
    Granularity,
    OmniWeatherConfig,
    ProviderId,
)


class PromptIO(Protocol):
    """Small prompt surface so the wizard can be tested without a terminal."""

    def print(self, value: object = "") -> None:
        """Write wizard output."""

    def ask(
        self,
        prompt: str,
        *,
        default: str | None = None,
        password: bool = False,
    ) -> str:
        """Ask for a text value."""

    def confirm(self, prompt: str, *, default: bool) -> bool:
        """Ask for confirmation."""


class RichPromptIO:
    """Rich-backed prompt implementation writing interactive text to stderr."""

    def __init__(self) -> None:
        self.console = Console(stderr=True)

    def print(self, value: object = "") -> None:
        self.console.print(value)

    def ask(
        self,
        prompt: str,
        *,
        default: str | None = None,
        password: bool = False,
    ) -> str:
        value = Prompt.ask(
            prompt,
            default=default,
            password=password,
            console=self.console,
        )
        return value if value is not None else ""

    def confirm(self, prompt: str, *, default: bool) -> bool:
        return Confirm.ask(prompt, default=default, console=self.console)


@dataclass(frozen=True)
class InitDefaults:
    """Optional defaults carried from an automatic forecast invocation."""

    latitude: float | None = None
    longitude: float | None = None
    sqlite: Path | None = None
    granularities: tuple[Granularity, ...] = ()
    providers: tuple[ProviderId, ...] = ()


@dataclass(frozen=True)
class InitResult:
    """Completed setup result used by the CLI router."""

    path: Path
    config: OmniWeatherConfig
    run_forecast: bool


def _prompt_coordinate(
    prompts: PromptIO,
    label: str,
    *,
    default: float | None,
    minimum: float,
    maximum: float,
) -> float:
    default_text = str(default) if default is not None else None
    while True:
        raw = prompts.ask(label, default=default_text).strip()
        try:
            value = float(raw)
        except (TypeError, ValueError):
            prompts.print(f"[red]{label} must be a number.[/red]")
            continue
        if minimum <= value <= maximum:
            return value
        prompts.print(
            f"[red]{label} must be between {minimum:g} and {maximum:g}.[/red]"
        )


def _provider_default_text(defaults: tuple[ProviderId, ...]) -> str:
    selected = defaults or (ProviderId.OPEN_METEO,)
    numbers = [
        str(index)
        for index, item in enumerate(PROVIDER_CATALOG, start=1)
        if item.provider_id in selected
    ]
    return ",".join(numbers)


def _print_provider_choices(prompts: PromptIO) -> None:
    prompts.print("[bold]Keyless providers[/bold]")
    for index, item in enumerate(PROVIDER_CATALOG[:3], start=1):
        suffix = " [green](recommended)[/green]" if item.recommended else ""
        prompts.print(
            f"  {index}. {item.name} — {item.coverage}, "
            f"{item.granularity_label}{suffix}",
        )
    prompts.print("\n[bold]Requires API key[/bold]")
    for index, item in enumerate(PROVIDER_CATALOG[3:], start=4):
        prompts.print(
            f"  {index}. {item.name} — {item.coverage}, {item.granularity_label}",
        )


def _parse_provider_selection(raw: str) -> tuple[ProviderId, ...] | None:
    tokens = [item for item in re.split(r"[\s,]+", raw.strip()) if item]
    selected: set[ProviderId] = set()
    for token in tokens:
        if token.isdigit() and 1 <= int(token) <= len(PROVIDER_CATALOG):
            selected.add(PROVIDER_CATALOG[int(token) - 1].provider_id)
            continue
        try:
            selected.add(ProviderId(token))
        except ValueError:
            return None
    if not selected:
        return None
    return tuple(
        item.provider_id for item in PROVIDER_CATALOG if item.provider_id in selected
    )


def _prompt_providers(
    prompts: PromptIO,
    defaults: tuple[ProviderId, ...],
) -> tuple[ProviderId, ...]:
    _print_provider_choices(prompts)
    while True:
        raw = prompts.ask(
            "Select providers (comma-separated numbers or IDs)",
            default=_provider_default_text(defaults),
        )
        if (selected := _parse_provider_selection(raw)) is not None:
            return selected
        prompts.print("[red]Choose at least one listed provider.[/red]")


def _prompt_nonempty(
    prompts: PromptIO,
    label: str,
    *,
    password: bool = False,
) -> str:
    while True:
        if value := prompts.ask(label, password=password).strip():
            return value
        prompts.print(f"[red]{label} is required.[/red]")


def _prompt_identity(prompts: PromptIO) -> str:
    app_name = _prompt_nonempty(prompts, "Application name")
    while "@" not in (email := _prompt_nonempty(prompts, "Contact email")):
        prompts.print("[red]Enter a contact email containing '@'.[/red]")
    return f"{app_name}/1.0 {email}"


def _prompt_provider_configs(
    prompts: PromptIO,
    providers: tuple[ProviderId, ...],
) -> dict[ProviderId, dict[str, str]]:
    configs: dict[ProviderId, dict[str, str]] = {}
    identity_ids = {
        item.provider_id
        for item in PROVIDER_CATALOG
        if item.authentication == "identity"
    }
    shared_identity = (
        _prompt_identity(prompts) if identity_ids.intersection(providers) else None
    )
    for provider_id in providers:
        setup = PROVIDER_BY_ID[provider_id]
        if setup.authentication == "identity":
            configs[provider_id] = {"user_agent": shared_identity or ""}
            continue
        configs[provider_id] = {}
        if not setup.credential_fields:
            continue
        if setup.signup_url is not None:
            prompts.print(f"[dim]{setup.name} setup: {setup.signup_url}[/dim]")
        for field in setup.credential_fields:
            configs[provider_id][field.config_key] = _prompt_nonempty(
                prompts,
                f"{setup.name} {field.prompt}",
                password=True,
            )
    return configs


def _prompt_sqlite_path(prompts: PromptIO, default: Path | None) -> Path:
    suggested = normalized_path(default or default_sqlite_path())
    while True:
        raw = prompts.ask("SQLite output path", default=str(suggested)).strip()
        if raw:
            path = normalized_path(raw)
            if path.exists() and path.is_dir():
                prompts.print("[red]SQLite output path cannot be a directory.[/red]")
                continue
            return path
        prompts.print("[red]SQLite output path is required.[/red]")


def _parse_granularities(raw: str) -> tuple[Granularity, ...] | None:
    choices = tuple(Granularity)
    tokens = [item for item in re.split(r"[\s,]+", raw.strip()) if item]
    selected: set[Granularity] = set()
    for token in tokens:
        if token.isdigit() and 1 <= int(token) <= len(choices):
            selected.add(choices[int(token) - 1])
            continue
        try:
            selected.add(Granularity(token))
        except ValueError:
            return None
    if not selected:
        return None
    return tuple(item for item in choices if item in selected)


def _granularity_default_text(defaults: tuple[Granularity, ...]) -> str:
    values = defaults or (Granularity.HOURLY, Granularity.DAILY)
    return ",".join(item.value for item in values)


def _prompt_granularities(
    prompts: PromptIO,
    defaults: tuple[Granularity, ...],
    providers: tuple[ProviderId, ...],
) -> tuple[Granularity, ...]:
    prompts.print("Granularities: 1. minutely  2. hourly  3. daily")
    while True:
        raw = prompts.ask(
            "Select granularities (comma-separated numbers or names)",
            default=_granularity_default_text(defaults),
        )
        if (selected := _parse_granularities(raw)) is None:
            prompts.print("[red]Choose at least one listed granularity.[/red]")
            continue
        incompatible = [
            PROVIDER_BY_ID[item].name
            for item in providers
            if not supports_any(item, selected)
        ]
        if not incompatible:
            return selected
        prompts.print(
            "[red]No selected granularity is supported by: "
            f"{', '.join(incompatible)}.[/red]",
        )


def _build_raw_config(
    latitude: float,
    longitude: float,
    sqlite_path: Path,
    granularities: tuple[Granularity, ...],
    providers: tuple[ProviderId, ...],
    provider_configs: dict[ProviderId, dict[str, str]],
) -> dict[str, object]:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "sqlite": str(sqlite_path),
        "granularity": [item.value for item in granularities],
        "providers": [
            {
                "plugin_id": provider_id.value,
                "config": provider_configs[provider_id],
            }
            for provider_id in providers
        ],
    }


def _validated_toml(raw_config: dict[str, object]) -> tuple[str, OmniWeatherConfig]:
    toml_text = tomli_w.dumps(raw_config)
    parsed = tomllib.loads(toml_text)
    config = OmniWeatherConfig.model_validate(parsed)
    registry = get_plugin_registry()
    for registration in config.providers:
        plugin = registry[registration.plugin_id]
        plugin.validate_config(registration.config)
    return toml_text, config


def _ensure_directory(path: Path) -> None:
    if path.exists():
        return
    path.mkdir(mode=0o700, parents=True)
    if os.name != "nt":
        path.chmod(stat.S_IRWXU)


def _atomic_write(path: Path, text: str, sqlite_path: Path) -> None:
    _ensure_directory(path.parent)
    _ensure_directory(sqlite_path.parent)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        temporary_path.replace(path)
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _parse_daily_time(raw: str) -> time | None:
    pieces = raw.strip().split(":")
    if len(pieces) != 2 or not all(piece.isdigit() for piece in pieces):
        return None
    try:
        return time(hour=int(pieces[0]), minute=int(pieces[1]))
    except ValueError:
        return None


def _prompt_daily_time(prompts: PromptIO) -> time:
    while True:
        raw = prompts.ask("Daily run time (24-hour local time)", default="06:00")
        if (run_at := _parse_daily_time(raw)) is not None:
            return run_at
        prompts.print("[red]Enter a valid local time in HH:MM format.[/red]")


def _offer_daily_schedule(prompts: PromptIO, config_path: Path) -> None:
    scheduler = scheduler_name()
    if not prompts.confirm(
        f"Set up automatic daily collection using {scheduler}?",
        default=False,
    ):
        return
    run_at = _prompt_daily_time(prompts)
    try:
        inspection = install_daily_schedule(config_path, run_at)
    except (OSError, ScheduleError) as exc:
        prompts.print(f"[red]Could not install the daily schedule: {exc}[/red]")
        prompts.print("Run omni-weather doctor after correcting the scheduler issue.")
        return
    prompts.print(f"[green]Installed {inspection.detail}[/green]")


def run_init(
    path: Path,
    *,
    defaults: InitDefaults | None = None,
    automatic: bool,
    prompts: PromptIO | None = None,
) -> InitResult | None:
    """Run the interactive setup wizard and atomically write a valid config."""

    active_defaults = defaults or InitDefaults()
    prompt_io = prompts or RichPromptIO()
    target_path = normalized_path(path)
    prompt_io.print("[bold]omni-weather setup[/bold]")
    latitude = _prompt_coordinate(
        prompt_io,
        "Default latitude",
        default=active_defaults.latitude,
        minimum=-90,
        maximum=90,
    )
    longitude = _prompt_coordinate(
        prompt_io,
        "Default longitude",
        default=active_defaults.longitude,
        minimum=-180,
        maximum=180,
    )
    providers = _prompt_providers(prompt_io, active_defaults.providers)
    provider_configs = _prompt_provider_configs(prompt_io, providers)
    sqlite_path = _prompt_sqlite_path(prompt_io, active_defaults.sqlite)
    granularities = _prompt_granularities(
        prompt_io,
        active_defaults.granularities,
        providers,
    )
    raw_config = _build_raw_config(
        latitude,
        longitude,
        sqlite_path,
        granularities,
        providers,
        provider_configs,
    )
    toml_text, config = _validated_toml(raw_config)
    prompt_io.print("\n[bold green]Configuration is valid.[/bold green]")
    prompt_io.print(
        "[yellow]Warning: credential values appear in this preview and may remain "
        "in terminal history.[/yellow]",
    )
    prompt_io.print(Syntax(toml_text, "toml", word_wrap=True))
    action = "Overwrite" if target_path.exists() else "Write"
    if not prompt_io.confirm(f"{action} {target_path}?", default=False):
        prompt_io.print("No changes made.")
        return None
    _atomic_write(target_path, toml_text, sqlite_path)
    prompt_io.print(f"[green]Saved configuration to {target_path}[/green]")
    _offer_daily_schedule(prompt_io, target_path)
    run_forecast = automatic or prompt_io.confirm(
        "Run a test forecast now?",
        default=True,
    )
    return InitResult(target_path, config, run_forecast)


__all__ = [
    "InitDefaults",
    "InitResult",
    "PromptIO",
    "RichPromptIO",
    "run_init",
]
