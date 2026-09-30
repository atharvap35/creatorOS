from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Type, TypeVar

E = TypeVar("E", bound=Enum)


def utcnow() -> datetime:
    """Naive UTC timestamp, matching how the DB columns store datetimes."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_enum(enum_cls: Type[E], raw: Optional[str], fallback: Optional[E] = None) -> Optional[E]:
    """Tolerant form-input parsing: fall back instead of raising a 500."""
    if raw is None or raw == "":
        return fallback
    if isinstance(raw, enum_cls):
        return raw
    try:
        return enum_cls(raw)
    except ValueError:
        pass
    try:
        return enum_cls[str(raw)]
    except KeyError:
        return fallback


def parse_optional_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    cleaned = raw.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def parse_optional_float(raw: Optional[str], fallback: float = 0.0) -> float:
    if raw is None or raw == "":
        return fallback
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def parse_optional_int(raw: Optional[str], fallback: Optional[int] = None) -> Optional[int]:
    if raw is None or raw == "":
        return fallback
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return fallback


def clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
