"""
snapshot_store.py
-----------------
Periodic state snapshots to accelerate replay_until().

Files: storage/snapshots/snapshot_seq_{N}.json
Rules:
  - saved when seq % SNAPSHOT_INTERVAL == 0
  - never overwrite existing snapshots
  - snapshot content is the full internal replay state
  - crash-safe: write to .tmp then rename
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SNAPSHOT_DIR      = Path("storage/snapshots")
SNAPSHOT_INTERVAL = 200


def should_snapshot(seq: int) -> bool:
    return seq > 0 and seq % SNAPSHOT_INTERVAL == 0


def save_snapshot(seq: int, state: Dict[str, Any]) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    target = SNAPSHOT_DIR / f"snapshot_seq_{seq}.json"
    if target.exists():
        return  # never overwrite

    tmp = target.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, target)   # atomic on POSIX; best-effort on Windows
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def load_latest_snapshot(target_seq: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    """
    Return (snap_seq, state) for the most-recent snapshot with seq <= target_seq.
    Returns (0, None) if no usable snapshot found.
    """
    if not SNAPSHOT_DIR.exists():
        return 0, None

    candidates = []
    try:
        for name in os.listdir(SNAPSHOT_DIR):
            if name.startswith("snapshot_seq_") and name.endswith(".json"):
                try:
                    seq = int(name[len("snapshot_seq_"):-len(".json")])
                    if seq <= target_seq:
                        candidates.append(seq)
                except ValueError:
                    pass
    except OSError:
        return 0, None

    if not candidates:
        return 0, None

    latest = max(candidates)
    path   = SNAPSHOT_DIR / f"snapshot_seq_{latest}.json"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return latest, json.load(fh)
    except (OSError, json.JSONDecodeError):
        return 0, None
