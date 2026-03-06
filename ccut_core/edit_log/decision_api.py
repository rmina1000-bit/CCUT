"""
decision_api.py
---------------
FastAPI router exposing the append-only edit decision log.

Endpoints
  GET  /decision-log            -- return recent entries
  POST /append-event            -- fire-and-forget append (non-blocking response)
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

import threading
from edit_log.edit_log import append_event, get_log
from edit_log.replay_engine import replay, summarize
from edit_log.undo_engine import get_undo_engine
from render.smart_render import build_render_plan, diff_render_plan, format_render_plan

router = APIRouter(tags=["decision-log"])

# Server-side render plan cache (last computed plan for diff)
_plan_cache: list = []
_plan_lock  = threading.Lock()


class AppendRequest(BaseModel):
    type: str
    payload: Dict[str, Any] = {}


@router.post("/append-event", status_code=202)
async def post_append(body: AppendRequest):
    """202 Accepted — UI fire-and-forget. Never blocks the caller."""
    append_event(body.type, body.payload)
    return {"accepted": True}


@router.get("/decision-log")
def get_decision_log(limit: int = 500):
    return get_log(limit)


@router.get("/decision-replay")
def get_decision_replay():
    """Reconstruct current editing state from the full event log."""
    return replay()


@router.get("/decision-summary")
def get_decision_summary():
    """Aggregate statistics across all logged events."""
    return summarize()


@router.post("/undo")
def post_undo():
    """
    Step active_seq back by one and return the reconstructed state.
    Append-only log is never modified.
    """
    engine = get_undo_engine()
    state  = engine.undo()
    state["undo_status"] = engine.status()
    return state


@router.post("/redo")
def post_redo():
    """Step active_seq forward by one and return the reconstructed state."""
    engine = get_undo_engine()
    state  = engine.redo()
    state["undo_status"] = engine.status()
    return state


@router.post("/smart-render")
def post_smart_render():
    """
    Derive a render plan from the current replay state.
    Diffs against the previously cached plan so only changed segments
    are flagged.  append-only log is never read or modified.
    """
    global _plan_cache

    current_state = replay()
    new_plan      = build_render_plan(current_state)

    with _plan_lock:
        prev_plan    = list(_plan_cache)
        changed      = diff_render_plan(prev_plan, new_plan)
        _plan_cache  = new_plan

    return {
        "plan":            new_plan,
        "changed_segments": changed,
        "total_duration":  sum(s["duration"] for s in new_plan),
        "formatted":       format_render_plan(new_plan),
        "diff_count":      len(changed),
        "full_rerender":   len(changed) == len(new_plan),
    }
