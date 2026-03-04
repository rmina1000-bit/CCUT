"""
proposal_api.py
---------------
FastAPI router: POST /generate-proposals

Accepts a FragmentIndex, returns exactly two proposals (A and B).
Each proposal is an ordered list of fragment IDs.
Previous proposals are never stored — each call is independent.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from proposal_engine.proposal_engine import generate_proposals
from edit_log.edit_log import append_event

router = APIRouter(tags=["proposals"])


class ProposalRequest(BaseModel):
    fragments: List[Dict[str, Any]]


class ProposalResponse(BaseModel):
    A: List[str]
    B: List[str]


@router.post("/generate-proposals", response_model=ProposalResponse)
async def generate(body: ProposalRequest):
    if not body.fragments:
        raise HTTPException(status_code=422, detail="fragments list is empty")

    try:
        result = generate_proposals(body.fragments)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response = ProposalResponse(A=result["A"], B=result["B"])
    append_event("PROPOSAL_GENERATED", {"A": result["A"], "B": result["B"]})
    return response
