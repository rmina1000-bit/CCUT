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


def _ms_between(end: Any, start: Any) -> int | None:
    if isinstance(end, (int, float)) and isinstance(start, (int, float)):
        return int(end - start)
    return None


def _tok_per_sec(call: dict[str, Any], gen_ms: int | None) -> float | None:
    tokens = call.get("completion_tokens")
    if not isinstance(tokens, (int, float)) or tokens <= 0:
        return None
    duration_ns = call.get("eval_duration_ns")
    if isinstance(duration_ns, (int, float)) and duration_ns > 0:
        return round(float(tokens) / (float(duration_ns) / 1_000_000_000), 2)
    if isinstance(gen_ms, int) and gen_ms > 0:
        return round(float(tokens) / (float(gen_ms) / 1000), 2)
    return None


def _summarize_ollama_calls(rec: dict[str, Any]) -> None:
    calls = rec.get("ollama_calls") or []
    rec["model_call_count"] = len(calls)
    for call in calls:
        if "prompt_tokens" not in call and call.get("prompt_eval_count") is not None:
            call["prompt_tokens"] = call.get("prompt_eval_count")
        if "completion_tokens" not in call and call.get("eval_count") is not None:
            call["completion_tokens"] = call.get("eval_count")
        request_ms = call.get("t_request")
        first_ms = call.get("t_first_token") or call.get("t_done")
        done_ms = call.get("t_done")
        call["ttft_ms"] = _ms_between(first_ms, request_ms)
        call["gen_ms"] = _ms_between(done_ms, first_ms)
        call["tok_per_sec"] = _tok_per_sec(call, call.get("gen_ms"))
        if call.get("num_predict") is None:
            call["num_predict"] = "unset"
        stop = call.get("stop")
        call["stop_configured"] = bool(stop)
        if call.get("prompt_tokens") is None and call.get("prompt_eval_count") is None:
            call["prompt_token_status"] = "missing"
        else:
            call["prompt_token_status"] = "ok"


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
        server_response = rec.get("response") if isinstance(rec.get("response"), dict) else {}
        frontend_response = frontend.get("response") if isinstance(frontend.get("response"), dict) else {}
        rec["response"] = {**server_response, **frontend_response}
        rec["screen_text"] = frontend.get("screen_text")
        rec["db_assistant_text"] = frontend.get("db_assistant_text")
        rec["db_assistant_source"] = frontend.get("db_assistant_source")
        rec["client_abort"] = bool(frontend.get("client_abort"))
        if "t5" not in rec:
            for call in rec.get("ollama_calls") or []:
                if call.get("t_first_token"):
                    rec["t5"] = call.get("t_first_token")
                    break
                if call.get("t_done"):
                    rec["t5"] = call.get("t_done")
                    break
        _summarize_ollama_calls(rec)
        rec["finalized_at"] = now_ms()
        _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return {"status": "OK", "path": str(_TRACE_PATH), "trace_id": trace_id}
