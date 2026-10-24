"""Small helpers shared by the API layer."""
from datetime import datetime, timezone

from bson import ObjectId


def _jsonable(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def public(doc: dict) -> dict:
    """A link document safe to send to the browser: no embedding, JSON-friendly values."""
    return _jsonable({k: v for k, v in doc.items() if k != "embedding"})


def as_utc(value: datetime) -> datetime:
    """MongoDB returns naive datetimes by default; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
