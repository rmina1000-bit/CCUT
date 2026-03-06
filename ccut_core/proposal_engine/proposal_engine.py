"""
proposal_engine.py
------------------
Deterministic A/B proposal generator.  Pure heuristic — no external models.

Proposal A — Curated linear
  • Original fragment order preserved
  • Fragments with duration <= SHORT_THRESHOLD removed
  • Guarantee: at least 1 fragment kept (longest when all are short)

Proposal B — Duration-weighted interleave
  • Fragments scored by duration + positional salience
  • Top-half (by score) sorted descending
  • Bottom-half sorted descending
  • Interleaved: [top0, bot0, top1, bot1, ...]
  • Guarantees A ≠ B unless input is trivially small

Rules
  • Always returns exactly 2 proposals
  • Previous proposals are never reused (stateless pure function)
  • Output: list of fragment IDs in new order
"""

from typing import List, Dict, Any

SHORT_THRESHOLD: float = 3.0   # seconds — fragments at or below removed in A


def _score(frag: dict, idx: int, total: int) -> float:
    """
    Salience score.  Fully deterministic: same input always yields same output.

    Components:
      - duration        : longer = more important
      - positional bias : first & last 20 % of sequence +1.0 (hook / resolution)
    """
    dur = frag.get("duration", 0.0)
    pos_ratio = idx / max(total - 1, 1)
    positional = 1.0 if (pos_ratio <= 0.20 or pos_ratio >= 0.80) else 0.0
    return dur + positional


def _proposal_a(fragments: List[dict]) -> List[str]:
    """Original order; short fragments removed."""
    kept = [f for f in fragments if f.get("duration", 0.0) > SHORT_THRESHOLD]
    if not kept:
        kept = [max(fragments, key=lambda f: f.get("duration", 0.0))]
    return [f["id"] for f in kept]


def _proposal_b(fragments: List[dict]) -> List[str]:
    """Duration-weighted interleave."""
    n = len(fragments)
    scored = sorted(
        enumerate(fragments),
        key=lambda x: _score(x[1], x[0], n),
        reverse=True,
    )

    split = max(1, n // 2)
    top = [f for _, f in scored[:split]]
    bot = [f for _, f in scored[split:]]

    # Interleave: top0, bot0, top1, bot1, …
    result = []
    for i in range(max(len(top), len(bot))):
        if i < len(top):
            result.append(top[i]["id"])
        if i < len(bot):
            result.append(bot[i]["id"])
    return result


def generate_proposals(fragments: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Parameters
    ----------
    fragments : list of fragment dicts (id, start, end, duration, editStack)

    Returns
    -------
    {"A": [id, ...], "B": [id, ...]}
    """
    if not fragments:
        return {"A": [], "B": []}

    a = _proposal_a(fragments)
    b = _proposal_b(fragments)

    # Ensure A != B when possible (swap last two in B if identical)
    if a == b and len(b) >= 2:
        b[-1], b[-2] = b[-2], b[-1]

    return {"A": a, "B": b}
