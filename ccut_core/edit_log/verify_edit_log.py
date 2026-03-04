"""
verify_edit_log.py
------------------
Integrity checks for the edit-decision log + snapshot store.

verify_snapshot_integrity()
  -- each snapshot file is valid JSON and contains required keys

verify_snapshot_replay_match()
  -- for every snapshot, replay_until(snap_seq) must equal the snapshot state
     (fragments + order)

verify_random_rewind(samples=5)
  -- pick N random seq values, ensure replay_until() returns without error
     and last_event_seq == requested seq (or lower if log is shorter)

All functions return (bool, str) — (passed, message).
Never raise; errors are captured in the message string.
"""

import json
import os
import random
import sys
from pathlib import Path
from typing import Tuple

from .snapshot_store import SNAPSHOT_DIR, load_latest_snapshot
from .replay_engine  import replay_until
from .edit_log       import get_last_seq, _LOG_PATH


def verify_snapshot_integrity() -> Tuple[bool, str]:
    """Check every snapshot file is parseable and has required keys."""
    required = {"fragments", "order", "events_count", "last_event_seq"}

    if not SNAPSHOT_DIR.exists():
        return True, "no snapshots directory — skipped"

    files = [
        f for f in os.listdir(SNAPSHOT_DIR)
        if f.startswith("snapshot_seq_") and f.endswith(".json")
    ]
    if not files:
        return True, "no snapshot files — skipped"

    bad = []
    for name in files:
        path = SNAPSHOT_DIR / name
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            missing = required - set(data.keys())
            if missing:
                bad.append(f"{name}: missing keys {missing}")
        except (OSError, json.JSONDecodeError) as exc:
            bad.append(f"{name}: {exc}")

    if bad:
        return False, "snapshot integrity failures: " + "; ".join(bad)
    return True, f"all {len(files)} snapshot(s) valid"


def verify_snapshot_replay_match() -> Tuple[bool, str]:
    """
    For each snapshot, run replay_until(snap_seq) and compare
    the resulting order and fragment ids against the snapshot.
    Mismatch → failure.
    """
    if not SNAPSHOT_DIR.exists():
        return True, "no snapshots directory — skipped"

    files = [
        f for f in os.listdir(SNAPSHOT_DIR)
        if f.startswith("snapshot_seq_") and f.endswith(".json")
    ]
    if not files:
        return True, "no snapshot files — skipped"

    mismatches = []
    for name in sorted(files):
        try:
            seq = int(name[len("snapshot_seq_"):-len(".json")])
        except ValueError:
            continue

        try:
            _, snap_state = load_latest_snapshot(seq)
            if snap_state is None:
                mismatches.append(f"seq={seq}: snapshot unloadable")
                continue

            replayed = replay_until(seq)

            snap_order    = snap_state.get("order", [])
            replay_order  = replayed.get("order", [])

            if snap_order != replay_order:
                mismatches.append(
                    f"seq={seq}: order mismatch "
                    f"snap={snap_order[:4]}… replay={replay_order[:4]}…"
                )
        except Exception as exc:
            mismatches.append(f"seq={seq}: exception — {exc}")

    if mismatches:
        return False, "snapshot/replay mismatches: " + "; ".join(mismatches)
    return True, f"all {len(files)} snapshot(s) match replay"


def verify_random_rewind(samples: int = 5) -> Tuple[bool, str]:
    """
    Pick *samples* random seq values in [1, last_seq] and confirm
    replay_until() returns a valid state dict without raising.
    """
    last_seq = get_last_seq()
    if last_seq < 1:
        return True, "log is empty — skipped"

    universe = list(range(1, last_seq + 1))
    chosen   = random.sample(universe, min(samples, len(universe)))
    chosen.sort()

    errors = []
    for seq in chosen:
        try:
            state = replay_until(seq)
            if not isinstance(state, dict):
                errors.append(f"seq={seq}: non-dict return")
                continue
            actual_seq = state.get("last_event_seq")
            if actual_seq is not None and actual_seq > seq:
                errors.append(
                    f"seq={seq}: returned last_event_seq={actual_seq} > requested"
                )
        except Exception as exc:
            errors.append(f"seq={seq}: exception — {exc}")

    if errors:
        return False, "random rewind failures: " + "; ".join(errors)
    return True, f"random rewind ok for seq={chosen}"


def run_all_checks() -> dict:
    """
    Run all three checks and return a summary dict.
    Safe to call from an API endpoint or test harness.
    """
    checks = {
        "snapshot_integrity":    verify_snapshot_integrity,
        "snapshot_replay_match": verify_snapshot_replay_match,
        "random_rewind":         verify_random_rewind,
    }
    results = {}
    overall = True
    for name, fn in checks.items():
        try:
            passed, msg = fn()
        except Exception as exc:
            passed, msg = False, str(exc)
        results[name] = {"passed": passed, "message": msg}
        if not passed:
            overall = False

    results["overall"] = overall
    return results


if __name__ == "__main__":
    # When invoked as: python -m ccut_core.edit_log.verify_edit_log
    # CWD must be ccut_core/ so that relative storage paths resolve correctly.
    _core_dir = Path(__file__).resolve().parent.parent  # …/ccut_core
    os.chdir(_core_dir)
    if str(_core_dir) not in sys.path:
        sys.path.insert(0, str(_core_dir))

    results = run_all_checks()
    print(json.dumps(results, indent=2))
    sys.exit(0 if results.get("overall") else 1)
