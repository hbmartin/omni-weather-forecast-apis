"""Tests for list-valued ``api_key`` expansion into per-key config variants."""

from __future__ import annotations

import pytest

from omni_weather_forecast_apis.utils import (
    ApiKeyListError,
    expand_api_key_variants,
)


def test_scalar_key_passes_through_unchanged() -> None:
    config = {"api_key": "single-key", "units": "metric"}

    assert expand_api_key_variants(config) == [config]


def test_missing_api_key_field_passes_through_unchanged() -> None:
    config = {"user_agent": "MyApp/1.0 contact@example.com"}

    assert expand_api_key_variants(config) == [config]


def test_single_item_list_expands_to_one_variant() -> None:
    variants = expand_api_key_variants({"api_key": ["only-key"]})

    assert variants == [{"api_key": "only-key"}]


def test_multi_item_list_preserves_sibling_fields() -> None:
    config = {"api_key": ["k1", "k2"], "units": "metric", "extend_hourly": True}

    variants = expand_api_key_variants(config)

    assert variants == [
        {"api_key": "k1", "units": "metric", "extend_hourly": True},
        {"api_key": "k2", "units": "metric", "extend_hourly": True},
    ]


def test_duplicate_keys_are_allowed() -> None:
    variants = expand_api_key_variants({"api_key": ["same", "same"]})

    assert [variant["api_key"] for variant in variants] == ["same", "same"]


def test_empty_list_is_rejected() -> None:
    with pytest.raises(ApiKeyListError, match="must not be empty"):
        expand_api_key_variants({"api_key": []})


@pytest.mark.parametrize(
    ("entries", "positions"),
    [
        (["good", ""], "2"),
        ([None, "good"], "1"),
        (["good", 42, ""], "2, 3"),
    ],
)
def test_invalid_entries_are_rejected_with_positions(
    entries: list[object],
    positions: str,
) -> None:
    with pytest.raises(ApiKeyListError, match=rf"position\(s\): {positions}\)$"):
        expand_api_key_variants({"api_key": entries})


def test_error_message_never_contains_key_values() -> None:
    with pytest.raises(ApiKeyListError) as exc_info:
        expand_api_key_variants({"api_key": ["sk-secret-value", ""]})

    assert "sk-secret-value" not in str(exc_info.value)


def test_expansion_does_not_mutate_input() -> None:
    config = {"api_key": ["k1", "k2"], "units": "metric"}

    expand_api_key_variants(config)

    assert config == {"api_key": ["k1", "k2"], "units": "metric"}
