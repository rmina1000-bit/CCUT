import shutil
from pathlib import Path
from .trace_hash import build_combined_trace_hash


STORAGE_DIR = Path("storage")
OBS_DIR = STORAGE_DIR / "observability"


def _reset_storage():
    if STORAGE_DIR.exists():
        shutil.rmtree(STORAGE_DIR)


def verify_trace_determinism(run_fn) -> bool:
    """
    run_fn을 2회 실행하고 Trace 구조 hash가 동일한지 검증.
    Observability가 Replay 결정성에 영향을 주지 않음을 증명.
    """
    _reset_storage()
    run_fn()
    hash_1 = build_combined_trace_hash(OBS_DIR)

    _reset_storage()
    run_fn()
    hash_2 = build_combined_trace_hash(OBS_DIR)

    if hash_1 != hash_2:
        print("TRACE NON-DETERMINISTIC")
        print(f"  run_1: {hash_1}")
        print(f"  run_2: {hash_2}")
        return False

    return True
