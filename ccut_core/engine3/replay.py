from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ccut_core.engine3.decision_log import DecisionLog
from ccut_core.engine3.event_types import EventType


@dataclass
class ReplayResult:
    ok: bool
    state: dict[str, Any]
    error: str | None = None


def replay_events(events: list[dict[str, Any]]) -> ReplayResult:
    state: dict[str, Any] = {"commits": [], "last_pointer": None, "utterances": []}
    previous_hash = ""

    for idx, event in enumerate(events):
        expected_index = idx
        if event["event_index"] != expected_index:
            return ReplayResult(False, {}, f"event_index mismatch at {idx}")

        base_event = {k: v for k, v in event.items() if k != "event_hash"}
        computed_hash = DecisionLog.compute_event_hash(previous_hash, base_event)
        if event["event_hash"] != computed_hash:
            return ReplayResult(False, {}, f"hash mismatch at {idx}")
        if event["previous_hash"] != previous_hash:
            return ReplayResult(False, {}, f"previous_hash mismatch at {idx}")

        event_type = EventType(event["event_type"])
        payload = event.get("payload", {})
        if event_type == EventType.USER_UTTERANCE:
            state["utterances"].append(payload)
        elif event_type == EventType.POINTER_SELECTION:
            state["last_pointer"] = payload
        elif event_type == EventType.DECISION_COMMIT:
            state["commits"].append(payload)

        previous_hash = event["event_hash"]

    return ReplayResult(True, state)
