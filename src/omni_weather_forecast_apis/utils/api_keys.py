"""Expansion of list-valued ``api_key`` provider configs into per-key variants.

A provider ``config`` block may set ``api_key`` to either a single string or a
list of strings. Expansion happens after environment placeholder resolution and
before per-provider validation, so provider config models keep a plain
``api_key: str`` field and never see lists.
"""

from __future__ import annotations

from typing import Any

type ProviderConfigDict = dict[str, Any]


class ApiKeyListError(ValueError):
    """Raised when a list-valued ``api_key`` cannot be expanded."""


def expand_api_key_variants(config: ProviderConfigDict) -> list[ProviderConfigDict]:
    """Split a list-valued ``api_key`` into single-key config variants.

    Configs without an ``api_key`` field, or with a non-list value, pass
    through unchanged as a single variant. Error messages name 1-based list
    positions only, never key values.
    """

    match config.get("api_key"):
        case []:
            msg = "api_key list must not be empty"
            raise ApiKeyListError(msg)
        case list() as keys:
            invalid_positions = [
                str(position)
                for position, key in enumerate(keys, start=1)
                if not isinstance(key, str) or not key
            ]
            if invalid_positions:
                msg = (
                    "api_key list entries must be non-empty strings "
                    f"(invalid at position(s): {', '.join(invalid_positions)})"
                )
                raise ApiKeyListError(msg)
            return [{**config, "api_key": key} for key in keys]
        case _:
            return [config]


__all__ = ["ApiKeyListError", "ProviderConfigDict", "expand_api_key_variants"]
