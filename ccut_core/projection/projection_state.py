from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class ProjectionState:
    last_seq: int = 0
    status: str = "INIT"
    meta: Dict[str, Any] = field(default_factory=dict)

    def apply(self, event: Dict[str, Any]):
        self.last_seq = event["seq"]

        if event["type"] == "GENESIS":
            self.status = "READY"

        elif event["type"] == "STATUS_CHANGE":
            self.status = event["payload"].get("status", self.status)

        elif event["type"] == "META_UPDATE":
            self.meta.update(event["payload"])
