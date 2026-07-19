"""Shared UTC helpers for the event dataclasses and Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_utc_datetime(value: datetime) -> datetime:
    """Assume UTC for naive input; convert aware input to UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
