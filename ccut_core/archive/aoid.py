from __future__ import annotations

import uuid


def create_aoid() -> str:
    return str(uuid.uuid4())


def validate_aoid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
