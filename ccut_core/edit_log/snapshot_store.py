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
SNAPSHOT_INTERVAL = 10


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
            json.dump({"seq": seq, "state": state}, fh,
                      ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, target)   # atomic on POSIX; best-effort on Windows
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def load_latest_snapshot(
    target_seq: int = 10 ** 18,
) -> Tuple[int, Optional[Dict[str, Any]]]:
    """
    Return (snap_seq, state) for the most-recent *valid* snapshot with
    seq <= target_seq.  Returns (0, None) if no usable snapshot exists.

    Integrity rules (corrupted snapshots are silently skipped):
      - file must be parseable JSON
      - "seq"   must be a positive int
      - "state" must be a dict
      - seq must be <= target_seq
      - when multiple candidates exist, the one with the largest seq wins
    """
    if not SNAPSHOT_DIR.exists():
        return 0, None

    candidates: list = []

    try:
        entries = os.listdir(SNAPSHOT_DIR)
    except OSError:
        return 0, None

    for name in entries:
        if not (name.startswith("snapshot_seq_") and name.endswith(".json")):
            continue

        path = SNAPSHOT_DIR / name
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            # ── Format validation ─────────────────────────────
            # New format: {"seq": int, "state": dict}
            if isinstance(data, dict) and "seq" in data and "state" in data:
                seq   = data["seq"]
                state = data["state"]
            # Old format: raw state dict (backward compat)
            elif isinstance(data, dict):
                # derive seq from filename
                try:
                    seq = int(name[len("snapshot_seq_"):-len(".json")])
                except ValueError:
                    continue
                state = data
            else:
                continue  # not a dict at all

            # ── Field type guard ─────────────────────────────
            if not isinstance(seq, int) or seq <= 0:
                continue
            if not isinstance(state, dict):
                continue
            if seq > target_seq:
                continue

            candidates.append((seq, state))

        except Exception:
            # corrupted / unreadable snapshot → ignore, never raise
            continue

    if not candidates:
        return 0, None

    best_seq, best_state = max(candidates, key=lambda x: x[0])
    return best_seq, best_state
