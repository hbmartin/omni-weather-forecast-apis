"""Shared UTC helpers for the event dataclasses and Pydantic models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any, cast

type EventState = Mapping[str, Any] | list[Any] | tuple[Any, ...]


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_utc_datetime(value: datetime) -> datetime:
    """Assume UTC for naive input; convert aware input to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def restore_utc_event_state(event: Any, state: EventState) -> None:
    """Restore frozen slot values and enforce the event timestamp contract."""

    event_fields = fields(event)
    if isinstance(state, Mapping):
        mapping_state = cast(Mapping[str, Any], state)
        values = tuple(mapping_state[event_field.name] for event_field in event_fields)
    elif isinstance(state, (list, tuple)):
        values = tuple(state)
    else:
        msg = "invalid event pickle state type"
        raise TypeError(msg)
    if len(values) != len(event_fields):
        msg = "invalid event pickle state"
        raise ValueError(msg)
    for event_field, value in zip(event_fields, values, strict=True):
        object.__setattr__(event, event_field.name, value)
    object.__setattr__(
        event,
        "timestamp",
        normalize_utc_datetime(event.timestamp),
    )
