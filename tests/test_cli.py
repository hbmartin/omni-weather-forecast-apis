from __future__ import annotations

import pytest

from omni_weather_forecast_apis.cli import (
    _resolve_optional,
    _resolve_required,
    build_parser,
)


def test_resolve_required_preserves_zero_values() -> None:
    assert _resolve_required(0.0, 51.5, "lat") == 0.0
    assert _resolve_required(0.0, -0.1, "lon") == 0.0


def test_resolve_required_exits_when_both_sources_are_missing() -> None:
    with pytest.raises(SystemExit) as exc_info:
        _resolve_required(None, None, "lat")

    assert exc_info.value.code == 2


def test_resolve_optional_preserves_explicit_values() -> None:
    assert _resolve_optional("en", "de") == "en"
    assert _resolve_optional(0.0, 5000.0) == 0.0


def test_build_parser_leaves_language_unset_until_resolution() -> None:
    parsed = build_parser().parse_args([])

    assert parsed.language is None


def test_build_parser_defaults_to_table_format() -> None:
    parsed = build_parser().parse_args([])

    assert parsed.output_format == "table"


def test_build_parser_accepts_json_format() -> None:
    parsed = build_parser().parse_args(["--format", "json"])

    assert parsed.output_format == "json"


def test_build_parser_rejects_unknown_format() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--format", "yaml"])


def test_sqlite_is_optional() -> None:
    parsed = build_parser().parse_args([])

    assert parsed.sqlite is None
