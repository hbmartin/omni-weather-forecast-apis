"""ISO/Unix timestamp helpers."""

from datetime import UTC, datetime


def datetime_from_unix(ts: float) -> datetime:
    """Convert Unix timestamp (seconds) to timezone-aware UTC datetime."""
    return datetime.fromtimestamp(ts, tz=UTC)


def unix_from_datetime(dt: datetime) -> int:
    """Convert datetime to Unix timestamp (seconds)."""
    return int(dt.timestamp())


def parse_iso_datetime(s: str) -> datetime:
    """Parse an ISO 8601 datetime string to timezone-aware UTC datetime.

    If the string has no timezone info, assumes UTC.
    """
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
