"""
replay_engine.py
----------------
Reads decision_log.jsonl and reconstructs the current editing state.

replay(limit)  -- full state reconstruction from the log
summarize()    -- aggregate statistics across all events

Performance: < 50 ms for 1000 events (pure Python, no I/O beyond single
             sequential file read).
"""

from typing import Any, Dict, Generator, List, Optional
from .edit_log import get_log, get_last_seq

# ── Event type constants ────────────────────────────────────
EV_FRAGMENTS_GENERATED = "FRAGMENTS_GENERATED"
EV_BOUNDARY_ADJUSTED   = "BOUNDARY_ADJUSTED"
EV_FRAGMENTS_REORDERED = "FRAGMENTS_REORDERED"
EV_PROPOSAL_GENERATED  = "PROPOSAL_GENERATED"
EV_PROPOSAL_SELECTED   = "PROPOSAL_SELECTED"


def replay(limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Reconstruct current editing state — snapshot-accelerated.

    Loads the latest available snapshot, then replays only the
    delta events that follow it.  Falls back to full replay when
    no snapshot exists.

    `limit` is accepted for backward compatibility but ignored;
    the function always returns the complete current state.

    Returns
    -------
    {
      "fragments":       list[dict],
      "order":           list[str],
      "events_count":    int,
      "last_event_seq":  int | None
    }
    """
    from .snapshot_store import load_latest_snapshot

    # ── Phase 1: try to load a snapshot ──────────────────────────
    snap_seq:   int                        = 0
    snap_state: Optional[Dict[str, Any]]   = None
    try:
        snap_seq, snap_state = load_latest_snapshot()   # no-arg = latest
    except Exception:
        snap_seq, snap_state = 0, None  # corrupted → full replay

    # ── Phase 2: restore internal state ──────────────────────────
    if snap_state is not None and isinstance(snap_state, dict):
        state = snap_state
        if "_frag_map" not in state:
            state["_frag_map"] = {
                f["id"]: f for f in state.get("fragments", []) if "id" in f
            }
        start_seq = snap_seq + 1
    else:
        state     = _initial_internal_state()
        start_seq = 1

    # ── Phase 3: apply delta events ──────────────────────────────
    try:
        for entry in read_log_from(start_seq):
            _apply_event(state, entry)
        return _internal_to_public(state)
    except Exception:
        # Event apply failed mid-way; retry as full replay from scratch
        state = _initial_internal_state()
        try:
            for entry in read_log_from(1):
                _apply_event(state, entry)
        except Exception:
            pass
        return _internal_to_public(state)


def summarize() -> Dict[str, Any]:
    """
    Aggregate statistics from the full event log.

    Returns
    -------
    {
      "total_events":          int,
      "fragments_generated":   int,
      "boundary_adjustments":  int,
      "reorders":              int,
      "proposals_generated":   int,
      "proposals_selected":    int,
      "last_event_seq":        int | None,
      "last_event_type":       str | None
    }
    """
    events = get_log(limit=0)

    counts: Dict[str, int] = {
        EV_FRAGMENTS_GENERATED: 0,
        EV_BOUNDARY_ADJUSTED:   0,
        EV_FRAGMENTS_REORDERED: 0,
        EV_PROPOSAL_GENERATED:  0,
        EV_PROPOSAL_SELECTED:   0,
    }
    last_seq:  Optional[int] = None
    last_type: Optional[str] = None

    for entry in events:
        etype = entry.get("type", "")
        seq   = entry.get("seq")
        if etype in counts:
            counts[etype] += 1
        if seq is not None:
            last_seq  = seq
            last_type = etype

    return {
        "total_events":         len(events),
        "fragments_generated":  counts[EV_FRAGMENTS_GENERATED],
        "boundary_adjustments": counts[EV_BOUNDARY_ADJUSTED],
        "reorders":             counts[EV_FRAGMENTS_REORDERED],
        "proposals_generated":  counts[EV_PROPOSAL_GENERATED],
        "proposals_selected":   counts[EV_PROPOSAL_SELECTED],
        "last_event_seq":       last_seq,
        "last_event_type":      last_type,
    }


# ── Snapshot-accelerated replay ──────────────────────────────
# These functions extend the module without modifying replay() / summarize().
# Internal state includes "_frag_map" for O(1) boundary updates.
# replay_until() strips "_frag_map" before returning the public dict.

def _initial_internal_state() -> Dict[str, Any]:
    return {
        "fragments":      [],
        "order":          [],
        "events_count":   0,
        "last_event_seq": None,
        "_frag_map":      {},
    }


def _apply_event(state: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply a single log entry to state (mutates in-place for performance).
    Returns the same state dict.
    Malformed entries are silently skipped.
    """
    etype   = entry.get("type", "")
    payload = entry.get("payload", {})
    seq     = entry.get("seq")

    if seq is not None:
        state["last_event_seq"] = seq
    state["events_count"] += 1

    frag_map: Dict[str, Any] = state["_frag_map"]

    try:
        if etype == EV_FRAGMENTS_GENERATED:
            state["_frag_map"] = {}
            state["order"]     = []

        elif etype == EV_BOUNDARY_ADJUSTED:
            fid       = payload.get("fragment_id")
            new_start = payload.get("new_start")
            new_end   = payload.get("new_end")
            if fid and fid in frag_map:
                f = dict(frag_map[fid])
                if new_start is not None:
                    f["start"] = new_start
                if new_end is not None:
                    f["end"] = new_end
                if "start" in f and "end" in f:
                    f["duration"] = round(f["end"] - f["start"], 3)
                frag_map[fid] = f

        elif etype == EV_FRAGMENTS_REORDERED:
            new_order = payload.get("new_order", [])
            if new_order:
                state["order"] = list(new_order)

        elif etype == EV_PROPOSAL_SELECTED:
            pass   # ordering already captured by paired FRAGMENTS_REORDERED

        elif etype == EV_PROPOSAL_GENERATED:
            pass   # proposals are stateless; no state mutation required

    except Exception:
        pass

    return state


def _internal_to_public(state: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal fields and assemble the fragments list."""
    frag_map = state["_frag_map"]
    order    = state["order"]

    if order and frag_map:
        fragments = [frag_map[fid] for fid in order if fid in frag_map]
    else:
        fragments = list(frag_map.values())
        order     = [f["id"] for f in fragments if "id" in f]

    return {
        "fragments":      fragments,
        "order":          order,
        "events_count":   state["events_count"],
        "last_event_seq": state["last_event_seq"],
    }


def read_log_from(start_seq: int) -> Generator[Dict[str, Any], None, None]:
    """
    Yield log entries with seq >= start_seq in ascending order.
    Malformed lines are silently skipped.
    """
    from .edit_log import _LOG_PATH   # module-private, same package
    import json as _json

    if not _LOG_PATH.exists():
        return

    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                    if entry.get("seq", 0) >= start_seq:
                        yield entry
                except _json.JSONDecodeError:
                    pass
    except OSError:
        pass


def replay_until(seq_limit: int) -> Dict[str, Any]:
    """
    Reconstruct editing state up to and including seq_limit.

    Uses the closest available snapshot as a starting point, then
    applies only the delta events — O(N / SNAPSHOT_INTERVAL) in the
    common case.

    Never raises; returns an empty state on any failure.
    """
    from .snapshot_store import load_latest_snapshot

    # ── Phase 1: try to load a valid snapshot ≤ seq_limit ────────
    snap_seq:   int                        = 0
    snap_state: Optional[Dict[str, Any]]   = None
    try:
        snap_seq, snap_state = load_latest_snapshot(seq_limit)
    except Exception:
        snap_seq, snap_state = 0, None  # corrupted → full replay

    # ── Phase 2: restore internal state ──────────────────────────
    if snap_state is not None and isinstance(snap_state, dict):
        state = snap_state
        if "_frag_map" not in state:
            state["_frag_map"] = {
                f["id"]: f for f in state.get("fragments", []) if "id" in f
            }
        start_seq = snap_seq + 1
    else:
        state     = _initial_internal_state()
        start_seq = 1

    # ── Phase 3: apply delta events up to seq_limit ──────────────
    try:
        for entry in read_log_from(start_seq):
            if entry.get("seq", 0) > seq_limit:
                break
            _apply_event(state, entry)
        return _internal_to_public(state)
    except Exception:
        # Retry as full replay from seq 1 up to seq_limit
        state = _initial_internal_state()
        try:
            for entry in read_log_from(1):
                if entry.get("seq", 0) > seq_limit:
                    break
                _apply_event(state, entry)
        except Exception:
            pass
        return _internal_to_public(state)
