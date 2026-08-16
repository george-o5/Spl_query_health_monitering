# SPL validation helpers, timestamp utils
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_spl(value: float) -> bool:
    """Validate an SPL (sound pressure level) value is within acceptable range."""
    return 0.0 <= value <= 200.0


def parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts)
