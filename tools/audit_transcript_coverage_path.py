import sqlite3
import json
import os

def audit_coverage(source_id=None):
    db_path = os.path.join("ccut_backend", "ccut_app.db")
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not source_id:
        source = cur.execute("SELECT source_id FROM sources ORDER BY created_at DESC LIMIT 1").fetchone()
        if not source:
            print("No sources found.")
            return
        source_id = source["source_id"]
    
    # Source Info
    source_row = cur.execute("SELECT duration FROM sources WHERE source_id = ?", (source_id,)).fetchone()
    source_duration = source_row["duration"] if source_row else 0.0

    print(f"=== Coverage Path Audit: {source_id} ===")
    print(f"Source Duration: {source_duration:.2f}s")

    # 1. Evidence Board Stats
    ev_total = cur.execute("SELECT COUNT(*) FROM evidence_board WHERE source_id = ?", (source_id,)).fetchone()[0]
    ev_text_rows = cur.execute("""
        SELECT fragment_id, start, end, text, fallback_reason, worker_sources 
        FROM evidence_board 
        WHERE source_id = ? AND text IS NOT NULL AND text != ''
    """, (source_id,)).fetchall()
    
    ev_text_count = len(ev_text_rows)
    
    # Calculate coverage seconds
    coverage_seconds = 0.0
    if ev_text_rows:
        # Merge overlapping/adjacent segments for coverage calculation
        intervals = sorted([(r["start"], r["end"]) for r in ev_text_rows])
        if intervals:
            merged = [intervals[0]]
            for current in intervals[1:]:
                prev_start, prev_end = merged[-1]
                curr_start, curr_end = current
                if curr_start <= prev_end:
                    merged[-1] = (prev_start, max(prev_end, curr_end))
                else:
                    merged.append(current)
            coverage_seconds = sum(end - start for start, end in merged)

    print(f"Evidence Board Rows (Total): {ev_total}")
    print(f"Evidence Board Text Rows: {ev_text_count}")
    print(f"Text Coverage: {coverage_seconds:.2f}s / {source_duration:.2f}s ({ (coverage_seconds/source_duration*100) if source_duration > 0 else 0 :.1f}%)")

    # 2. Intelligence Stats
    fragments = cur.execute("SELECT fragment_id, intelligence FROM fragments WHERE source_id = ?", (source_id,)).fetchall()
    frag_count = len(fragments)
    intel_text_count = 0
    intel_words_count = 0
    
    for f in fragments:
        intel = json.loads(f["intelligence"]) if isinstance(f["intelligence"], str) else f["intelligence"]
        if intel:
            if intel.get("transcript"):
                intel_text_count += 1
            if intel.get("words") and len(intel["words"]) > 0:
                intel_words_count += 1

    print(f"Fragments Count: {frag_count}")
    print(f"Fragments w/ Intelligence Transcript: {intel_text_count}")
    print(f"Fragments w/ Non-Empty Words: {intel_words_count}")

    # 3. Worker & Fallback Distribution
    workers = {}
    for r in ev_text_rows:
        ws = json.loads(r["worker_sources"]) if isinstance(r["worker_sources"], str) else r["worker_sources"]
        if ws and "text" in ws:
            wname = ws["text"]
            workers[wname] = workers.get(wname, 0) + 1
    
    print(f"Text Worker Distribution: {workers}")

    fallbacks = cur.execute("""
        SELECT fallback_reason, COUNT(*) as cnt 
        FROM evidence_board 
        WHERE source_id = ? AND (text IS NULL OR text = '')
        GROUP BY fallback_reason
    """, (source_id,)).fetchall()
    
    print("Fallback Reasons (for empty text rows):")
    for fb in fallbacks:
        print(f"  - {fb['fallback_reason']}: {fb['cnt']}")

    # 4. Text Row Details
    print("\nText Row List (Start/End):")
    for r in sorted(ev_text_rows, key=lambda x: x["start"]):
        print(f"  - {r['fragment_id']}: {r['start']:>7.2f}s - {r['end']:>7.2f}s (len={len(r['text'])})")

    # 5. Smart Quality Check
    print("\n=== Smart Quality Check ===")
    coverage_ratio = (coverage_seconds / source_duration) if source_duration > 0 else 0
    
    empty_rows_cnt = 0
    old_contract_cnt = 0
    asr_attempted_cnt = 0
    for fb in fallbacks:
        cnt = fb['cnt']
        empty_rows_cnt += cnt
        if fb['fallback_reason'] is None:
            old_contract_cnt += cnt
        elif fb['fallback_reason'] and (
            fb['fallback_reason'].startswith("asr_rejected") or 
            fb['fallback_reason'].startswith("asr_empty") or 
            fb['fallback_reason'].startswith("asr_provider_error")
        ):
            asr_attempted_cnt += cnt

    import yaml
    config_path = os.path.join("ccut_backend", "ai", "config.yaml")
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        current_provider = (cfg.get("active") or {}).get("asr", "unknown")
        # [R14] read current model_size
        current_model_size = (
            cfg.get("providers", {})
               .get("whisper", {})
               .get("config", {})
               .get("model_size", "unknown")
        )
    except Exception:
        current_provider = "unknown"
        current_model_size = "unknown"

    all_evidences = cur.execute("SELECT metadata_json FROM evidence_board WHERE source_id = ?", (source_id,)).fetchall()
    stored_providers = set()
    stored_model_sizes = set()  # [R14]
    for e in all_evidences:
        meta_str = e["metadata_json"]
        if meta_str:
            meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            if "asr_provider" in meta:
                stored_providers.add(meta["asr_provider"])
            if "asr_model_size" in meta and meta["asr_model_size"]:  # [R14]
                stored_model_sizes.add(meta["asr_model_size"])

    has_old_contract = old_contract_cnt > 0
    is_low_coverage = coverage_ratio < 0.5
    
    provider_changed = (
        current_provider != "unknown"
        and bool(stored_providers)
        and current_provider not in stored_providers
        and is_low_coverage
    )

    # 우선순위 3: ASR_MODEL_MISSING
    model_missing = (
        current_provider == "whisper"
        and "whisper" in stored_providers
        and not stored_model_sizes
        and coverage_ratio > 0   # text가 존재하는 경우에만 (empty는 별도 처리)
    )

    # 우선순위 4: ASR_MODEL_CHANGED
    model_changed = (
        bool(stored_model_sizes)
        and current_model_size != "unknown"
        and current_model_size not in stored_model_sizes
    )

    asr_attempted = (
        not has_old_contract
        and not provider_changed
        and not model_missing
        and not model_changed
        and is_low_coverage
        and asr_attempted_cnt > 0
    )
    
    print(f"current_provider: {current_provider}")
    print(f"stored_asr_providers: {list(stored_providers)}")
    print(f"current_model_size: {current_model_size}")           # [R14]
    print(f"stored_asr_model_sizes: {list(stored_model_sizes)}") # [R14]

    reasons = []
    if has_old_contract:  reasons.append("OLD_ASR_CONTRACT")
    if provider_changed:  reasons.append("ASR_PROVIDER_CHANGED")
    if model_missing:     reasons.append("ASR_MODEL_MISSING")
    if model_changed:     reasons.append("ASR_MODEL_CHANGED")
    if asr_attempted and not (has_old_contract or provider_changed or model_missing or model_changed):
        reasons.append("ASR_ATTEMPTED_NO_TEXT")

    quality = {
        "reason": reasons,
        "next_action": (
            "REANALYZE_WITH_CURRENT_ASR_PROVIDER" if (has_old_contract or provider_changed)
            else "REANALYZE_WITH_CURRENT_ASR_MODEL" if (model_missing or model_changed)
            else "REVIEW_ASR_PROVIDER" if asr_attempted
            else "OK"
        )
    }

    if has_old_contract:
        print(f"[!] OLD_ASR_CONTRACT detected ({old_contract_cnt} rows with None fallback).")
    
    if provider_changed:
        print("[!] ASR_PROVIDER_CHANGED detected.")

    if "ASR_MODEL_MISSING" in quality.get("reason", []):
        print("[!] ASR_MODEL_MISSING detected. (whisper result exists but no model_size recorded)")
    if "ASR_MODEL_CHANGED" in quality.get("reason", []):
        print("[!] ASR_MODEL_CHANGED detected.")
        
    if asr_attempted:
        print("[!] ASR_ATTEMPTED_NO_TEXT detected (same provider — reanalysis blocked).")

    print(f"[ACTION] {quality.get('next_action')}")

    conn.close()

if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else None
    audit_coverage(sid)
