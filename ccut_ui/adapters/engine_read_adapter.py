import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_CORE = _ROOT / "ccut_core"

if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

_VERIFY_CACHE: dict = {"result": None, "ts": 0.0}
_VERIFY_TTL: float = 30.0


def read_projection() -> dict:
    try:
        from projection.projection_store import get_projection
        p = get_projection()
        if p is None:
            return {"cuts": {}, "version": 0, "note": "No projection yet"}
        cuts = {}
        try:
            cuts = {k: dict(v) if hasattr(v, "__dict__") else v
                    for k, v in p._cuts.items()}
        except Exception:
            cuts = {}
        return {"cuts": cuts, "version": getattr(p, "version", 0)}
    except Exception as e:
        return {"cuts": {}, "version": 0, "error": str(e)}


def read_status() -> dict:
    try:
        from observability.health_monitor import compute_health
        health = compute_health()
        return {
            "health_status": health.get("status", "UNKNOWN"),
            "issues": health.get("issues", []),
        }
    except Exception as e:
        return {"health_status": "UNKNOWN", "issues": [str(e)]}


def read_verify() -> dict:
    now = time.monotonic()
    cached = _VERIFY_CACHE
    if cached["result"] is not None and (now - cached["ts"]) < _VERIFY_TTL:
        return cached["result"]
    try:
        from decision_log import DecisionLog
        from verify_engine import verify_engine
        log = DecisionLog()
        verify_engine(log)
        result = {"verified": True, "status": "PASS", "seq": log._seq}
    except AssertionError as e:
        result = {"verified": False, "status": "FAIL", "error": str(e)}
    except Exception as e:
        result = {"verified": False, "status": "ERROR", "error": str(e)}
    _VERIFY_CACHE["result"] = result
    _VERIFY_CACHE["ts"] = now
    return result


def read_metrics() -> dict:
    try:
        from observability.live_metrics import get_live_metrics
        return get_live_metrics()
    except Exception as e:
        return {"error": str(e)}


def read_seal() -> bool:
    try:
        from observability.production_seal import is_sealed
        return is_sealed()
    except Exception:
        return False


def read_decision_log(limit: int = 200) -> list:
    import json
    try:
        log_path = Path("storage") / "engine.log"
        if not log_path.exists():
            return []
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        lines = [l for l in lines if l.strip()]
        tail = lines[-limit:] if len(lines) >= limit else lines
        result = []
        for l in tail:
            try:
                result.append(json.loads(l))
            except Exception:
                pass
        return result
    except Exception:
        return []


def read_trace(n: int = 50) -> list:
    import json
    try:
        trace_path = Path("storage") / "observability" / "event_trace.log"
        if not trace_path.exists():
            return []
        lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
        lines = [l for l in lines if l.strip()]
        tail = lines[-n:] if len(lines) >= n else lines
        result = []
        for l in tail:
            try:
                entry = json.loads(l)
                payload = entry.get("payload", entry)
                result.append(payload)
            except Exception:
                pass
        return result
    except Exception:
        return []


def preview_replay() -> dict:
    try:
        events = read_decision_log(1000)
        type_counts: dict = {}
        for e in events:
            t = e.get("type", e.get("event_type", "UNKNOWN"))
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "event_count": len(events),
            "event_types": type_counts,
            "first_seq": events[0].get("seq") if events else None,
            "last_seq": events[-1].get("seq") if events else None,
            "dry_run": True,
            "note": "Replay preview — no execution performed",
        }
    except Exception as e:
        return {"error": str(e), "dry_run": True}


def read_audit(n: int = 20) -> list:
    import json
    candidates = [
        _CORE / "storage" / "observability" / "audit.log",
        Path("storage") / "observability" / "audit.log",
    ]
    for path in candidates:
        try:
            if path.exists():
                lines = path.read_text(encoding="utf-8").strip().split("\n")
                lines = [l for l in lines if l.strip()]
                tail = lines[-n:] if len(lines) >= n else lines
                return [json.loads(l) for l in tail]
        except Exception:
            continue
    return []
