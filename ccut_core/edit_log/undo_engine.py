"""
undo_engine.py
--------------
Stateful undo/redo cursor over the append-only decision log.

Design rules:
  - decision_log.jsonl is NEVER mutated
  - undo = replay_until(active_seq - 1)
  - redo = replay_until(active_seq + 1)
  - new event while in undo state → redo branch discarded (in-memory only),
    log untouched
  - snapshot hook fires on every commit_hook call when seq is a multiple
    of SNAPSHOT_INTERVAL

Usage (called from decision_api or any commit path):
    engine = UndoEngine()           # one shared instance per process
    engine.commit_hook(new_seq, state)

    state_at_prev = engine.undo()
    state_forward = engine.redo()
"""

import threading
from typing import Any, Dict, Optional

from .edit_log import get_last_seq
from .replay_engine import replay_until
from .snapshot_store import should_snapshot, save_snapshot


class UndoEngine:
    """
    Thread-safe undo/redo cursor.

    active_seq : int   — seq the user is currently "viewing"
    current_seq: int   — highest seq ever committed to the log
    """

    def __init__(self) -> None:
        self._lock        = threading.Lock()
        self.current_seq: int = get_last_seq()
        self.active_seq:  int = self.current_seq

    # ── Public API ──────────────────────────────────────────

    def undo(self) -> Dict[str, Any]:
        """
        Step back one event and return the reconstructed state.
        Clamps at seq 0 (empty log state).
        """
        with self._lock:
            if self.active_seq > 0:
                self.active_seq -= 1
            target = self.active_seq
        return replay_until(target)

    def redo(self) -> Dict[str, Any]:
        """
        Step forward one event (up to current_seq) and return reconstructed state.
        """
        with self._lock:
            if self.active_seq < self.current_seq:
                self.active_seq += 1
            target = self.active_seq
        return replay_until(target)

    def commit_hook(self, new_seq: int, state: Dict[str, Any]) -> None:
        """
        Called after every successful append_event().

        - Resets active_seq = current_seq = new_seq
          (redo branch discarded in-memory; log untouched)
        - Triggers snapshot if new_seq is an interval boundary
        """
        with self._lock:
            self.current_seq = new_seq
            self.active_seq  = new_seq

        if should_snapshot(new_seq):
            save_snapshot(new_seq, state)

    # ── Introspection ────────────────────────────────────────

    @property
    def can_undo(self) -> bool:
        return self.active_seq > 0

    @property
    def can_redo(self) -> bool:
        return self.active_seq < self.current_seq

    def status(self) -> Dict[str, Any]:
        return {
            "active_seq":  self.active_seq,
            "current_seq": self.current_seq,
            "can_undo":    self.can_undo,
            "can_redo":    self.can_redo,
        }


# ── Module-level singleton ───────────────────────────────────
# Shared across the entire server process.
# Import as: from edit_log.undo_engine import undo_engine
undo_engine: Optional[UndoEngine] = None


def get_undo_engine() -> UndoEngine:
    """Lazy singleton initialiser."""
    global undo_engine
    if undo_engine is None:
        undo_engine = UndoEngine()
    return undo_engine
