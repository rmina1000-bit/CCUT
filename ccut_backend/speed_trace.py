import contextvars
import json
import os
import threading
import time
from pathlib import Path
from typing import Any


_TRACE_ON = os.getenv("CCUT_TRACE", "0").lower() in ("1", "true", "yes", "on")
_BACKEND_DIR = Path(__file__).resolve().parent
_TRACE_PATH = _BACKEND_DIR.parent / "logs" / "trace" / "speed_trace.jsonl"
_LOCK = threading.Lock()
_RECORDS: dict[str, dict[str, Any]] = {}

current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ccut_speed_trace_id", default=None
)


def enabled() -> bool:
    return _TRACE_ON


def now_ms() -> int:
    return int(time.time() * 1000)


def set_current(trace_id: str | None):
    return current_trace_id.set(trace_id if _TRACE_ON and trace_id else None)


def reset_current(token) -> None:
    try:
        current_trace_id.reset(token)
    except Exception:
        pass


def get_current() -> str | None:
    return current_trace_id.get()


def mark(trace_id: str | None, key: str, value: Any | None = None, **extra: Any) -> None:
    if not _TRACE_ON or not trace_id:
        return
    with _LOCK:
        rec = _RECORDS.setdefault(trace_id, {"trace_id": trace_id})
        rec[key] = now_ms() if value is None else value
        if extra:
            rec.update(extra)


def update(trace_id: str | None, **fields: Any) -> None:
    if not _TRACE_ON or not trace_id:
        return
    with _LOCK:
        rec = _RECORDS.setdefault(trace_id, {"trace_id": trace_id})
        rec.update(fields)


def append_ollama_call(trace_id: str | None, call: dict[str, Any]) -> int | None:
    if not _TRACE_ON or not trace_id:
        return None
    with _LOCK:
        rec = _RECORDS.setdefault(trace_id, {"trace_id": trace_id})
        calls = rec.setdefault("ollama_calls", [])
        calls.append(call)
        return len(calls) - 1


def update_ollama_call(trace_id: str | None, idx: int | None, **fields: Any) -> None:
    if not _TRACE_ON or not trace_id or idx is None:
        return
    with _LOCK:
        calls = _RECORDS.setdefault(trace_id, {"trace_id": trace_id}).setdefault("ollama_calls", [])
        if 0 <= idx < len(calls):
            calls[idx].update(fields)


def finalize(frontend: dict[str, Any]) -> dict[str, Any]:
    trace_id = str(frontend.get("trace_id") or "")
    if not _TRACE_ON or not trace_id:
        return {"status": "OFF"}
    with _LOCK:
        rec = _RECORDS.pop(trace_id, {"trace_id": trace_id})
        rec["frontend"] = frontend
        for key in ("t0", "t1", "t6", "t7", "t8"):
            if key in frontend:
                rec[key] = frontend.get(key)
        rec["longtasks"] = frontend.get("longtasks") or []
        rec["request"] = frontend.get("request") or rec.get("request")
        rec["response"] = frontend.get("response") or rec.get("response")
        if "t5" not in rec:
            for call in rec.get("ollama_calls") or []:
                if call.get("t_first_token"):
                    rec["t5"] = call.get("t_first_token")
                    break
                if call.get("t_done"):
                    rec["t5"] = call.get("t_done")
                    break
        rec["finalized_at"] = now_ms()
        _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return {"status": "OK", "path": str(_TRACE_PATH), "trace_id": trace_id}
