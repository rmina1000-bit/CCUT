from pathlib import Path

from ccut_core.engine3.decision_log import DecisionLog
from ccut_core.engine3.event_types import EventType
from ccut_core.engine3.replay import replay_events


def test_append_and_replay(tmp_path: Path):
    path = tmp_path / "decisions" / "a1" / "decision_log.json"
    log = DecisionLog(path)
    log.append("aoid-1", "session-1", EventType.USER_UTTERANCE, {"text": "hello"})
    log.append("aoid-1", "session-1", EventType.POINTER_SELECTION, {"start": 1.0, "end": 2.0})
    log.append("aoid-1", "session-1", EventType.DECISION_COMMIT, {"segments": [{"start": 1.0, "end": 2.0}]})

    events = log.load()
    result = replay_events(events)

    assert result.ok is True
    assert len(result.state["utterances"]) == 1
    assert len(result.state["commits"]) == 1


def test_replay_detects_tamper(tmp_path: Path):
    path = tmp_path / "decisions" / "a1" / "decision_log.json"
    log = DecisionLog(path)
    log.append("aoid-1", "session-1", EventType.USER_UTTERANCE, {"text": "hello"})
    events = log.load()
    events[0]["payload"]["text"] = "hacked"

    result = replay_events(events)
    assert result.ok is False
