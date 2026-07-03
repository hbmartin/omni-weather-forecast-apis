"""Environment-variable placeholder resolution for provider configs.

Keeps secrets such as API keys out of TOML files. Two placeholder forms are
supported inside a provider ``config`` block:

- a whole-string reference: ``api_key = "${OPENWEATHER_API_KEY}"``
- an explicit marker table: ``api_key = { env = "OPENWEATHER_API_KEY" }``

Resolution is recursive through nested tables and arrays. A placeholder that
names an unset environment variable raises :class:`EnvVarNotSetError`, which
surfaces as a per-provider initialization error.
"""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_PLACEHOLDER = re.compile(r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}$")


class EnvVarNotSetError(LookupError):
    """Raised when a config placeholder references an unset variable."""

    def __init__(self, variable_name: str) -> None:
        super().__init__(
            f"Environment variable {variable_name!r} referenced in provider "
            "config is not set.",
        )
        self.variable_name = variable_name


def _lookup(variable_name: str) -> str:
    value = os.environ.get(variable_name)
    if value is None:
        raise EnvVarNotSetError(variable_name)
    return value


def resolve_env_placeholders(value: Any) -> Any:
    """Recursively resolve ``${VAR}`` and ``{env = "VAR"}`` placeholders."""

    match value:
        case str() as text:
            if (placeholder := _ENV_PLACEHOLDER.match(text)) is not None:
                return _lookup(placeholder.group("name"))
            return text
        case {"env": str() as variable_name} if len(value) == 1:
            return _lookup(variable_name)
        case dict() as mapping:
            return {
                key: resolve_env_placeholders(item) for key, item in mapping.items()
            }
        case list() as items:
            return [resolve_env_placeholders(item) for item in items]
        case _:
            return value


__all__ = ["EnvVarNotSetError", "resolve_env_placeholders"]
