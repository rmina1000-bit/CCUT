import json
from pathlib import Path


TRACE_DIR = Path("storage/observability")


def _tail_jsonl(path: Path, n: int) -> list:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    lines = [l for l in lines if l.strip()]
    tail = lines[-n:] if len(lines) >= n else lines
    result = []
    for line in tail:
        try:
            result.append(json.loads(line))
        except Exception:
            pass
    return result


try:
    from fastapi import APIRouter

    router = APIRouter(prefix="/observe", tags=["observability"])

    @router.get("/events")
    def get_events(n: int = 50):
        return _tail_jsonl(TRACE_DIR / "event_trace.log", n)

    @router.get("/timeline")
    def get_timeline(n: int = 50):
        return _tail_jsonl(TRACE_DIR / "timeline.log", n)

    @router.get("/snapshot")
    def get_snapshot():
        entries = _tail_jsonl(TRACE_DIR / "snapshot.log", 1)
        return entries[0] if entries else {}

    @router.get("/render")
    def get_render(n: int = 50):
        return _tail_jsonl(TRACE_DIR / "render_trace.log", n)

    @router.get("/live")
    def get_live():
        from observability.live_metrics import get_live_metrics
        return get_live_metrics()

    @router.get("/health")
    def get_health():
        from observability.health_monitor import compute_health
        return compute_health()

    @router.get("/status")
    def get_status():
        from observability.runtime_switch import is_enabled
        return {"observability_enabled": is_enabled()}

    @router.post("/enable")
    def post_enable():
        from observability.runtime_switch import enable
        enable()
        return {"observability_enabled": True}

    @router.post("/disable")
    def post_disable():
        from observability.runtime_switch import disable
        disable()
        return {"observability_enabled": False}

    @router.post("/seal")
    def post_seal():
        from observability.production_seal import seal, is_sealed
        if is_sealed():
            return {"sealed": True}
        seal()
        return {"sealed": True}

except ImportError:
    router = None
