"""
decision_reducer.py
-------------------
Acts as a bridge between the lightweight EditLog (append-only JSONL) and
the strict, immutable DecisionLog (hash chain).
Evaluates UI events and commits only meaningful state changes to the DecisionLog.
"""
import threading

_engine_log = None
_lock = threading.Lock()

def _get_engine_log():
    global _engine_log
    if _engine_log is None:
        with _lock:
            if _engine_log is None:
                from decision_log import DecisionLog
                _engine_log = DecisionLog()
    return _engine_log

def process_event(entry: dict):
    """
    Process an event dictionary from EditLog.
    If it's a meaningful change, forward it to DecisionLog as DECISION_COMMIT.
    """
    event_type = entry.get("type", "")
    payload = entry.get("payload", {})
    
    # Define what constitutes a "meaningful" state change from the UI log
    meaningful_types = {
        "FRAGMENTS_GENERATED",
        "MERGE",
        "SPLIT",
        "CREATE_CUT",
        "DELETE_CUT",
        "UPDATE_LAYOUT"
    }
    
    if event_type in meaningful_types:
        try:
            engine_log = _get_engine_log()
            engine_log.append("DECISION_COMMIT", {
                "action": event_type,
                "data": payload
            })
        except Exception as e:
            # Fallback for protected mode or hashing errors, shouldn't crash the UI log
            pass
