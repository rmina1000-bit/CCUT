import hashlib
import json
from pathlib import Path


_KEEP_FIELDS = {
    "event_trace.log":  {"event_type", "engine_seq", "trace_seq"},
    "timeline.log":     {"phase", "state", "timeline_seq"},
    "snapshot.log":     {"decision_count", "engine_status", "render_queue_depth"},
    "render_trace.log": {"version", "state"},
}


def _strip_entry(entry: dict, keep: set) -> dict:
    return {k: v for k, v in entry.items() if k in keep}


def build_trace_hash(log_path: Path) -> str:
    """
    Trace 로그를 결정성 검증용 canonical hash로 변환.
    timestamp / trace_id / resource_state 제거, 순서 유지.
    """
    if not log_path.exists():
        return hashlib.sha256(b"").hexdigest()

    keep = _KEEP_FIELDS.get(log_path.name, set())
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")

    canonical_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            stripped = _strip_entry(entry, keep)
            canonical_lines.append(
                json.dumps(stripped, sort_keys=True, separators=(",", ":"))
            )
        except Exception:
            continue

    combined = "\n".join(canonical_lines).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def build_combined_trace_hash(trace_dir: Path) -> str:
    """
    모든 trace 로그 파일의 hash를 결합한 단일 hash 생성.
    """
    log_names = sorted(_KEEP_FIELDS.keys())
    parts = []
    for name in log_names:
        file_hash = build_trace_hash(trace_dir / name)
        parts.append(f"{name}:{file_hash}")

    combined = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()
