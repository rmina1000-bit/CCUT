"""
smart_render.py
---------------
Deterministic render plan derived solely from replay state.

Rules (per CCUT Constitution §3):
  - Input: replay_state dict only (no decision_log reads)
  - No random, no timestamp, no UUID in output
  - Fragment data is never mutated
  - Same state in → same plan out (deterministic)

Functions
  build_render_plan(state)          → List[segment]
  diff_render_plan(prev, new)       → List[changed_segment]
  apply_smart_render(prev_plan)     → SmartRenderResult
"""

from typing import Any, Dict, List, Optional

# ── Types ─────────────────────────────────────────────────────

Segment = Dict[str, Any]
# {
#   "fragment_id": str,
#   "timeline_start": float,   # seconds from clip start
#   "timeline_end":   float,
#   "source_start":   float,   # within original fragment
#   "source_end":     float,
#   "duration":       float,
# }

RenderPlan = List[Segment]


# ── Core functions ─────────────────────────────────────────────

def build_render_plan(state: Dict[str, Any]) -> RenderPlan:
    """
    Derive a deterministic render plan from replay_state.

    Uses state["order"] when present; falls back to state["fragments"] order.
    Fragment data (start/end) is read but never modified.

    Returns an empty list for empty / missing fragment data.
    """
    fragments: List[Dict[str, Any]] = state.get("fragments", [])
    order:     List[str]            = state.get("order", [])

    # Build id→fragment map for O(1) lookup when order is explicit
    frag_map: Dict[str, Dict[str, Any]] = {
        f["id"]: f for f in fragments if "id" in f
    }

    # Determine rendering sequence
    if order:
        sequence = [frag_map[fid] for fid in order if fid in frag_map]
    else:
        sequence = fragments

    plan: RenderPlan = []
    cursor: float = 0.0

    for frag in sequence:
        src_start = frag.get("start", 0.0)
        src_end   = frag.get("end",   src_start)
        duration  = round(src_end - src_start, 6)

        if duration <= 0:
            continue  # skip zero-length or inverted fragments

        plan.append({
            "fragment_id":    frag["id"],
            "timeline_start": round(cursor, 6),
            "timeline_end":   round(cursor + duration, 6),
            "source_start":   src_start,
            "source_end":     src_end,
            "duration":       duration,
        })
        cursor += duration

    return plan


def diff_render_plan(
    prev_plan: RenderPlan,
    new_plan:  RenderPlan,
) -> List[Dict[str, Any]]:
    """
    Return segments from new_plan that differ from prev_plan.

    A segment is "changed" when:
      - its index does not exist in prev_plan, OR
      - any field value differs from the previous segment at that index.

    Returns [] when both plans are identical (no re-render needed).
    """
    changed: List[Dict[str, Any]] = []

    for i, seg in enumerate(new_plan):
        if i >= len(prev_plan) or prev_plan[i] != seg:
            changed.append({**seg, "_changed_at_index": i})

    return changed


def render_plan_total_duration(plan: RenderPlan) -> float:
    """Sum of all segment durations in the plan."""
    return round(sum(s["duration"] for s in plan), 6)


def format_render_plan(plan: RenderPlan) -> str:
    """
    Human-readable plan string for UI display and console output.
    Example:
        Render Plan  (3 segments, 20.0 s total)
          [  0.0 –  7.0]  F2   (src  5.0–12.0)
          [  7.0 – 15.0]  F3   (src 12.0–20.0)
          [ 15.0 – 20.0]  F1   (src  0.0– 5.0)
    """
    if not plan:
        return "Render Plan  (empty)"

    total = render_plan_total_duration(plan)
    lines = [f"Render Plan  ({len(plan)} segments, {total} s total)"]
    for seg in plan:
        lines.append(
            f"  [{seg['timeline_start']:6.1f} – {seg['timeline_end']:6.1f}]"
            f"  {seg['fragment_id']:<6}"
            f"  (src {seg['source_start']:.1f}–{seg['source_end']:.1f})"
        )
    return "\n".join(lines)
