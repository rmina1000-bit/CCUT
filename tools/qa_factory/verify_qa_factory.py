import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FAILURE_DIR = PROJECT_ROOT / "artifacts" / "qa_factory" / "failures"

def run_cmd(args, env_override=None):
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    res = subprocess.run([sys.executable] + args, capture_output=True, text=True, env=env)
    return res

def test_replay_mechanism():
    print("=== CCUT QA FACTORY SYSTEM VERIFICATION ===")
    
    # 1. Clean previous failures
    shutil.rmtree(FAILURE_DIR, ignore_errors=True)
    FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    
    # 2. Run a short brutal simulation (3 cases) with scaled CI mode
    print("[STEP 1] Running scaled simulation (mode: brutal)...")
    res = run_cmd(
        ["tools/qa_factory/run_qa_factory.py", "--mode", "brutal", "--cases", "3", "--chaos", "1"],
        env_override={"CCUT_CI_VERIFY": "true"}
    )
    
    print(f"Stdout:\n{res.stdout}")
    print(f"Stderr:\n{res.stderr}")
    
    if res.returncode != 0:
        print("[FAIL] Scaled brutal run failed!")
        sys.exit(1)
    else:
        print("[PASS] Scaled brutal run completed successfully.")

    # 3. Create a fake failure case JSON to test the replay parser
    print("[STEP 2] Creating simulated failure CASE_000999...")
    fake_case = {
        "run_id": "QA_BRUTAL_TEST",
        "seed": 999999,
        "case_id": "CASE_000999",
        "mode": "brutal",
        "failure_type": "ValueError",
        "failure_message": "Intentionally simulated failure to test replay correctness",
        "chaos_injected": ["db_locked"],
        "timestamp": "2026-05-28T20:00:00",
        "replay_command": "python tools/qa_factory/run_qa_factory.py --replay CASE_000999"
    }
    
    with open(FAILURE_DIR / "CASE_000999.json", "w", encoding="utf-8") as f:
        json.dump(fake_case, f, indent=2)
        
    # 4. Trigger replay of CASE_000999
    # Since chaos is db_locked, it should fail again with sqlite3.OperationalError: database is locked
    print("[STEP 3] Replaying CASE_000999...")
    res_replay = run_cmd(["tools/qa_factory/run_qa_factory.py", "--replay", "CASE_000999"])
    
    print(f"Replay Stdout:\n{res_replay.stdout}")
    print(f"Replay Stderr:\n{res_replay.stderr}")
    
    # Verify that it attempted replay and correctly threw sqlite3.OperationalError / failed
    if "database is locked" in res_replay.stdout or "database is locked" in res_replay.stderr:
        print("[PASS] Replay failed deterministically as expected (sqlite3.OperationalError).")
    else:
        print("[FAIL] Replay did not reproduce the expected database locked exception!")
        sys.exit(1)
        
    print("=== ALL QA FACTORY VERIFICATIONS PASSED ===")
    sys.exit(0)

if __name__ == "__main__":
    test_replay_mechanism()
