import json
from datetime import datetime, timezone
from pathlib import Path
from .runtime_switch import is_enabled
from .trace_buffer import buffered_append


TRACE_DIR = Path("storage/observability")
RENDER_TRACE_LOG = TRACE_DIR / "render_trace.log"

RENDER_STATES = [
    "QUEUED",
    "RESOURCE_WAIT",
    "STARTED",
    "GPU_ALLOCATED",
    "COMPLETED",
    "FAILED",
]


def trace_render(version: int, state: str, metadata: dict = None):
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": version,
            "state": state,
            "metadata": metadata or {},
        }

        if not is_enabled():
            return
        buffered_append(RENDER_TRACE_LOG, entry)
    except Exception:
        pass
