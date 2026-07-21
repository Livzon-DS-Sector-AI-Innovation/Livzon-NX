import uuid
from typing import Any


def normalize_correlation_id(value: Any = None) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if value:
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            pass
    return uuid.uuid4()
