from datetime import datetime, timezone
from pathlib import Path


GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"

_TRACE_DIR = Path("storage/observability")
_LAST_HEALTH_STATUS = None


def _flush_delay_seconds() -> float:
    from .live_metrics import _LAST_FLUSH_TS
    if _LAST_FLUSH_TS is None:
        return 0.0
    try:
        last = datetime.fromisoformat(_LAST_FLUSH_TS)
        now = datetime.now(timezone.utc)
        return (now - last).total_seconds()
    except Exception:
        return 0.0


def _quick_chain_check() -> bool:
    import json
    from .trace_chain import _compute_hash
    log_path = _TRACE_DIR / "event_trace.log"
    try:
        if not log_path.exists():
            return True
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        lines = [l for l in lines if l.strip()]
        if len(lines) < 1:
            return True
        entry = json.loads(lines[-1])
        recalculated = _compute_hash(entry["prev_hash"], entry["payload"])
        return recalculated == entry.get("hash")
    except Exception:
        return False


def compute_health() -> dict:
    from .live_metrics import get_live_metrics

    metrics = get_live_metrics()
    issues = []
    worst = GREEN

    def escalate(level):
        nonlocal worst
        if level == RED or (level == YELLOW and worst == GREEN):
            worst = level

    total_buffer = sum(metrics["buffer_sizes"].values())
    if total_buffer >= 1000:
        issues.append(f"Buffer size critical: {total_buffer}")
        escalate(RED)
    elif total_buffer >= 500:
        issues.append(f"Buffer size high: {total_buffer}")
        escalate(YELLOW)

    qd = metrics["render_queue_depth"]
    if qd >= 30:
        issues.append(f"Render queue depth critical: {qd}")
        escalate(RED)
    elif qd >= 10:
        issues.append(f"Render queue depth high: {qd}")
        escalate(YELLOW)

    delay = _flush_delay_seconds()
    if delay >= 30:
        issues.append(f"Flush delay critical: {delay:.1f}s")
        escalate(RED)
    elif delay >= 10:
        issues.append(f"Flush delay high: {delay:.1f}s")
        escalate(YELLOW)

    if not metrics["observability_enabled"]:
        issues.append("Observability is disabled")
        escalate(YELLOW)

    if not _quick_chain_check():
        issues.append("Trace chain integrity check failed")
        escalate(RED)

    global _LAST_HEALTH_STATUS
    try:
        from .audit_log import record_audit
        if _LAST_HEALTH_STATUS != worst:
            prev = _LAST_HEALTH_STATUS
            _LAST_HEALTH_STATUS = worst

            record_audit("HEALTH_STATUS_CHANGE", {
                "from": prev,
                "to": worst,
                "issues": issues,
            })

            if worst == RED:
                record_audit("HEALTH_RED_ENTER", {"issues": issues})
            elif worst == YELLOW:
                record_audit("HEALTH_YELLOW_ENTER", {"issues": issues})
            elif worst == GREEN and prev is not None:
                record_audit("HEALTH_GREEN_RECOVER", {})
        else:
            _LAST_HEALTH_STATUS = worst
    except Exception:
        pass

    return {
        "status": worst,
        "issues": issues,
        "metrics": metrics,
    }
