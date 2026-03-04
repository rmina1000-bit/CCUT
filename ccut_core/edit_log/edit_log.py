"""
edit_log.py
-----------
Append-only JSONL event store for user editing decisions.

Schema (one JSON object per line):
    {
      "seq":       int,      -- monotone, persists across restarts
      "type":      str,      -- event type constant
      "timestamp": float,    -- Unix epoch seconds
      "payload":   dict      -- event-specific data
    }

Storage: storage/decision_log.jsonl  (relative to server CWD = ccut_core/)
Rules:
  - append-only: existing lines are never modified or deleted
  - thread-safe: file lock protects concurrent writes
  - restart-safe: seq continues from last stored value
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

_LOG_PATH = Path("storage/decision_log.jsonl")
_LOCK = threading.Lock()

# Cached seq counter; initialized lazily on first write
_seq: int = 0
_seq_loaded: bool = False


def _ensure_dir() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_seq() -> int:
    """Read the last seq value from the tail of the log file."""
    if not _LOG_PATH.exists():
        return 0
    try:
        # Read tail efficiently (last ~4 KB)
        with open(_LOG_PATH, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size == 0:
                return 0
            fh.seek(-min(4096, size), 2)
            tail = fh.read().decode("utf-8", errors="ignore")

        last_seq = 0
        for line in reversed(tail.splitlines()):
            line = line.strip()
            if line:
                try:
                    last_seq = json.loads(line).get("seq", 0)
                    break
                except json.JSONDecodeError:
                    continue
        return last_seq
    except OSError:
        return 0


def _next_seq() -> int:
    global _seq, _seq_loaded
    if not _seq_loaded:
        _seq = _load_seq()
        _seq_loaded = True
    _seq += 1
    return _seq


def append_event(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Append one event to the log.

    Parameters
    ----------
    event_type : str   e.g. "FRAGMENTS_GENERATED"
    payload    : dict  event-specific data

    Returns
    -------
    The written entry dict.
    """
    _ensure_dir()
    with _LOCK:
        entry = {
            "seq":       _next_seq(),
            "type":      event_type,
            "timestamp": time.time(),
            "payload":   payload,
        }
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def get_last_seq() -> int:
    """Return the highest seq currently in the log (0 if empty)."""
    with _LOCK:
        return _load_seq()


def get_log(limit: int = 500) -> List[Dict[str, Any]]:
    """
    Read up to *limit* most-recent entries from the log.

    Returns [] if the log file does not yet exist.
    """
    _ensure_dir()
    if not _LOG_PATH.exists():
        return []

    entries: List[Dict[str, Any]] = []
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        return []

    return entries[-limit:] if limit else entries
