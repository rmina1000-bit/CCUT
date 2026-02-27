from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccut_core.engine3.event_types import EventType


@dataclass(frozen=True)
class DecisionEvent:
    schema_version: str
    event_id: str
    timestamp: str
    aoid: str
    session_id: str
    event_index: int
    event_type: EventType
    actor: dict[str, str]
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "aoid": self.aoid,
            "session_id": self.session_id,
            "event_index": self.event_index,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }


class DecisionLog:
    def __init__(self, path: Path):
        self.path = path

    def init_if_missing(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict[str, Any]]:
        self.init_if_missing()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, events: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _canonical_json(data: dict[str, Any]) -> str:
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def compute_event_hash(cls, previous_hash: str, base_event: dict[str, Any]) -> str:
        canonical = cls._canonical_json(base_event)
        return hashlib.sha256(f"{previous_hash}{canonical}".encode("utf-8")).hexdigest()

    def append(
        self,
        aoid: str,
        session_id: str,
        event_type: EventType,
        payload: dict[str, Any],
        actor: dict[str, str] | None = None,
    ) -> DecisionEvent:
        events = self._read()
        previous_hash = events[-1]["event_hash"] if events else ""
        event_index = len(events)
        base_event = {
            "schema_version": "1.0.0",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "aoid": aoid,
            "session_id": session_id,
            "event_index": event_index,
            "event_type": event_type.value,
            "actor": actor or {"type": "user", "id": "local-user"},
            "payload": payload,
            "previous_hash": previous_hash,
        }
        event_hash = self.compute_event_hash(previous_hash, base_event)
        event = {**base_event, "event_hash": event_hash}
        events.append(event)
        self._write(events)
        return DecisionEvent(
            schema_version=event["schema_version"],
            event_id=event["event_id"],
            timestamp=event["timestamp"],
            aoid=event["aoid"],
            session_id=event["session_id"],
            event_index=event["event_index"],
            event_type=EventType(event["event_type"]),
            actor=event["actor"],
            payload=event["payload"],
            previous_hash=event["previous_hash"],
            event_hash=event["event_hash"],
        )

    def load(self) -> list[dict[str, Any]]:
        return self._read()
