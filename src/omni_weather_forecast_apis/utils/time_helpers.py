from __future__ import annotations

from datetime import UTC, date, datetime


def utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(tz=UTC)


def ensure_utc(value: datetime) -> datetime:
    """Attach UTC when naive and convert aware values to UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def unix_timestamp(value: datetime) -> int:
    """Convert a datetime to whole-second Unix time."""

    return int(ensure_utc(value).timestamp())


def datetime_from_unix(value: float) -> datetime:
    """Parse Unix seconds into a UTC datetime."""

    return datetime.fromtimestamp(value, tz=UTC)


def parse_datetime(
    value: str | float | datetime | None,
) -> datetime | None:
    """Parse provider timestamps into UTC datetimes."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, (int, float)):
        return datetime_from_unix(value)

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T", 1)
    parsed = datetime.fromisoformat(normalized)
    return ensure_utc(parsed)


def parse_date(value: str | date | datetime | None) -> date | None:
    """Parse provider dates into `date` objects."""

    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return ensure_utc(value).date()
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T", 1)
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return ensure_utc(datetime.fromisoformat(normalized)).date()
