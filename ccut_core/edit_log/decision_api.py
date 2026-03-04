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

from edit_log.edit_log import append_event, get_log
from edit_log.replay_engine import replay, summarize

router = APIRouter(tags=["decision-log"])


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
