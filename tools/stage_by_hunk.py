import subprocess
import os
import re
import sys

def run_git(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
    if result.returncode != 0:
        print(f"Error running {' '.join(cmd)}: {result.stderr}")
    return result.stdout.strip()

def parse_hunks(diff_text):
    if not diff_text:
        return []
    
    files_diffs = diff_text.split("diff --git ")
    hunks = []
    
    for fd in files_diffs:
        if not fd.strip():
            continue
        lines = fd.splitlines()
        header_lines = []
        file_path_m = re.search(r"b/(ccut_backend/[^\s]+)", lines[0])
        if not file_path_m:
            continue
        file_path = file_path_m.group(1)
        
        # Extract headers
        hunk_start_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("@@"):
                hunk_start_idx = i
                break
            header_lines.append(line)
            
        if hunk_start_idx == -1:
            continue
            
        current_hunk = []
        for line in lines[hunk_start_idx:]:
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append((file_path, header_lines, current_hunk))
                    current_hunk = []
            current_hunk.append(line)
        if current_hunk:
            hunks.append((file_path, header_lines, current_hunk))
            
    return hunks

def apply_hunk(file_path, header_lines, hunk_lines):
    patch_content = "diff --git a/" + file_path + " b/" + file_path + "\n"
    patch_content += "\n".join(header_lines[1:]) + "\n"
    patch_content += "\n".join(hunk_lines) + "\n"
    
    patch_file = "temp_hunk.patch"
    with open(patch_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(patch_content)
        
    res = subprocess.run("git apply --cached --whitespace=nowarn temp_hunk.patch", shell=True, capture_output=True, text=True)
    if os.path.exists(patch_file):
        os.remove(patch_file)
        
    if res.returncode != 0:
        print(f"Failed to apply hunk for {file_path}: {res.stderr}")
        return False
    return True

def main():
    print("=== Category ASR / Storage / Snap Hunk Committer ===")
    
    # 0. Ensure no staged changes initially
    run_git(["git", "reset"])
    
    # Get modifications diff
    main_diff = run_git(["git", "diff", "ccut_backend/main.py"])
    manager_diff = run_git(["git", "diff", "ccut_backend/archive/manager.py"])
    
    main_hunks = parse_hunks(main_diff)
    manager_hunks = parse_hunks(manager_diff)
    
    print(f"Found {len(main_hunks)} hunks in main.py")
    print(f"Found {len(manager_hunks)} hunks in manager.py")
    
    # --- PHASE 1: ASR Contract Restore & Whisper Primary ---
    print("\n--- Phase 1: Staging ASR changes ---")
    # Stage config and whisper adapter
    run_git(["git", "add", "ccut_backend/ai/config.yaml"])
    run_git(["git", "add", "ccut_backend/ai/adapters/whisper_adapter.py"])
    
    # Stage ASR hunks from main.py
    for fp, header, hunk in main_hunks:
        hunk_text = "\n".join(hunk)
        if any(kw in hunk_text for kw in ["_background_whisper", "SOURCE_REUSED", "ASR Contract", "provider", "fallback_reason", "get_analysis_quality"]):
            print("Staging ASR hunk in main.py")
            apply_hunk(fp, header, hunk)
            
    # Stage ASR hunks from manager.py
    for fp, header, hunk in manager_hunks:
        hunk_text = "\n".join(hunk)
        if any(kw in hunk_text for kw in ["get_analysis_quality", "ASR_PROVIDER_CHANGED", "ASR_MODEL_CHANGED", "ASR_MODEL_MISSING", "stored_asr_providers", "current_model_size"]):
            print("Staging ASR hunk in manager.py")
            apply_hunk(fp, header, hunk)
            
    # Add untracked ASR tools
    asr_tools = [
        "tools/audit_asr_provider_strategy.py",
        "tools/audit_asr_selection_reason.py",
        "tools/audit_transcript_coverage_path.py"
    ]
    for tool in asr_tools:
        if os.path.exists(tool):
            run_git(["git", "add", tool])
            
    # Add ASR reports
    run_git(["git", "add", "docs/reports/STEP_2_A_FINAL_QWEN3_ASR_RUNTIME_AUDIT.md"])
    run_git(["git", "add", "docs/reports/STEP_2_C_ASR_GUARD_RUNTIME_RETEST.md"])
    run_git(["git", "add", "docs/reports/STEP_2_C_R1_PROPOSAL_SELECTION_COUNT_AUDIT.md"])
    run_git(["git", "add", "docs/reports/STEP_2_C_R3B_PROPOSAL_AB_SPLIT_LOGIC_AUDIT.md"])
    run_git(["git", "add", "docs/reports/STEP_2_C_R4_PROPOSAL_DIVERSITY_POLICY_FIX.md"])
    run_git(["git", "add", "docs/reports/STEP_2_C_SESSION_HANDOFF_TRUE_FRAGMENT_ENTRY.md"])
    
    # Commit Phase 1
    print(run_git(["git", "status", "--short"]))
    print(run_git(["git", "commit", "-m", "feat: restore ASR contract and switch Whisper primary"]))
    print(run_git(["git", "log", "-1", "--oneline"]))
    
    # --- PHASE 2: Storage / Thumbnail Path Fix ---
    print("\n--- Phase 2: Staging Storage changes ---")
    run_git(["git", "add", "ccut_backend/engine/video_engine.py"])
    
    # Stage Storage hunks from main.py
    for fp, header, hunk in main_hunks:
        hunk_text = "\n".join(hunk)
        if any(kw in hunk_text for kw in ["static", "storage", "thumbnail", "static_url", "build_static_url"]) and not any(kw in hunk_text for kw in ["_background_whisper", "snap_debug"]):
            print("Staging Storage hunk in main.py")
            apply_hunk(fp, header, hunk)
            
    # Stage Storage hunks from manager.py
    for fp, header, hunk in manager_hunks:
        hunk_text = "\n".join(hunk)
        if any(kw in hunk_text for kw in ["update_fragment_thumb", "thumb_url"]):
            print("Staging Storage hunk in manager.py")
            apply_hunk(fp, header, hunk)
            
    # Commit Phase 2
    print(run_git(["git", "status", "--short"]))
    print(run_git(["git", "commit", "-m", "fix: normalize storage path for thumbnails and video engine"]))
    print(run_git(["git", "log", "-1", "--oneline"]))
    
    # --- PHASE 3: R16 Sentence Boundary Snap ---
    print("\n--- Phase 3: Staging Snap changes ---")
    run_git(["git", "add", "ccut_backend/engine/semantic_engine.py"])
    
    # Stage Snap hunks from main.py
    for fp, header, hunk in main_hunks:
        hunk_text = "\n".join(hunk)
        if "snap_debug" in hunk_text:
            print("Staging Snap hunk in main.py")
            apply_hunk(fp, header, hunk)
            
    # Add untracked Snap tools & docs
    snap_tools = [
        "tools/audit_sf_boundary_snap.py",
        "tools/audit_transcript_evidence_structure.py",
        "tools/audit_transcript_fragment_boundary.py"
    ]
    for tool in snap_tools:
        if os.path.exists(tool):
            run_git(["git", "add", tool])
            
    run_git(["git", "add", "docs/tasks/STEP_2_D_STARTUP_CHECKLIST.md"])
    run_git(["git", "add", "docs/tasks/STEP_2_D_TRANSCRIPT_AWARE_FRAGMENT_BOUNDARY_FIX.md"])
    run_git(["git", "add", "docs/reports/STEP_2_D_TRANSCRIPT_AWARE_FRAGMENT_BOUNDARY_FIX.md"])
    run_git(["git", "add", "docs/reports/STEP_2_D_TRANSCRIPT_AWARE_BOUNDARY_FIX_REPORT.md"])
    
    # Commit Phase 3
    print(run_git(["git", "status", "--short"]))
    print(run_git(["git", "commit", "-m", "feat: add sentence-aware semantic boundary snap"]))
    print(run_git(["git", "log", "-1", "--oneline"]))
    
    print("\n=== Remaining Unstaged / Untracked Files ===")
    print(run_git(["git", "status", "--short"]))

if __name__ == "__main__":
    main()
