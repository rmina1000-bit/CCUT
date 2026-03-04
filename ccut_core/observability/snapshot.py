import json
from datetime import datetime, timezone
from pathlib import Path
from .runtime_switch import is_enabled
from .trace_buffer import buffered_append


TRACE_DIR = Path("storage/observability")
SNAPSHOT_LOG = TRACE_DIR / "snapshot.log"


def record_snapshot(
    decision_count: int,
    projection_hash: str = None,
    render_queue_depth: int = 0,
    engine_status: str = "STABLE",
):
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision_count": decision_count,
            "projection_hash": projection_hash,
            "resource_gate_state": "OPEN",
            "render_queue_depth": render_queue_depth,
            "engine_status": engine_status,
        }

        try:
            from .live_metrics import update_decision_count
            update_decision_count(decision_count)
        except Exception:
            pass
        if not is_enabled():
            return
        buffered_append(SNAPSHOT_LOG, entry)
    except Exception:
        pass
