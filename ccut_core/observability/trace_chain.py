import hashlib
import json
from pathlib import Path


def _last_hash(log_path: Path) -> str:
    if not log_path.exists():
        return "GENESIS"
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            return entry.get("hash", "GENESIS")
        except Exception:
            continue
    return "GENESIS"


def _compute_hash(prev_hash: str, payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    raw = (prev_hash + serialized).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def append_with_chain(log_path: Path, payload: dict):
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        prev_hash = _last_hash(log_path)
        current_hash = _compute_hash(prev_hash, payload)

        entry = {
            "prev_hash": prev_hash,
            "hash": current_hash,
            "payload": payload,
        }

        line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def verify_trace_chain(log_path: Path) -> bool:
    if not log_path.exists():
        return True

    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    lines = [l for l in lines if l.strip()]

    if not lines:
        return True

    expected_prev = "GENESIS"

    for i, line in enumerate(lines):
        try:
            entry = json.loads(line)
        except Exception:
            return False

        if entry.get("prev_hash") != expected_prev:
            return False

        recalculated = _compute_hash(entry["prev_hash"], entry["payload"])
        if recalculated != entry.get("hash"):
            return False

        expected_prev = entry["hash"]

    return True
