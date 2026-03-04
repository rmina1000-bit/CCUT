import uuid
from datetime import datetime, timezone


class EngineMeta:
    def __init__(self):
        self.engine_id = str(uuid.uuid4())
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return {
            "engine_id": self.engine_id,
            "created_at": self.created_at
        }
