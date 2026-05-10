
import os
import sys
import json
import sqlite3
from datetime import datetime

# Add ccut_backend to sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ccut_backend"))
sys.path.append(BACKEND_DIR)

DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

def query_db(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def audit_fragment_generation():
    print("\n=== 1. Fragment Generation Quality Audit ===")
    sources = query_db("SELECT * FROM sources")
    results = []
    
    for src in sources:
        sid = src["source_id"]
        label = src["title"]
        duration = src["duration"]
        
        frags = query_db("SELECT * FROM semantic_fragments WHERE source_id = ?", (sid,))
        
        if not frags:
            results.append({
                "source_id": sid,
                "source_label": label,
                "duration": duration,
                "fragment_count": 0,
                "avg_fragment_duration": 0,
                "min/max": "N/A",
                "suspicious_notes": "NO_FRAGMENTS"
            })
            continue
            
        durations = [f["end"] - f["start"] for f in frags]
        avg_dur = sum(durations) / len(durations)
        min_dur = min(durations)
        max_dur = max(durations)
        
        # Diagnostics
        short_frags = [d for d in durations if d < 2.0]
        long_frags = [d for d in durations if d > 60.0]
        
        notes = []
        if short_frags: notes.append(f"SHORT_FRAGS:{len(short_frags)}")
        if long_frags: notes.append(f"LONG_FRAGS:{len(long_frags)}")
        
        # Check role distribution
        roles = {}
        for f in frags:
            struct = json.loads(f["structural_json"])
            role = struct.get("role", "unknown")
            roles[role] = roles.get(role, 0) + 1
        
        # Check semantic summary
        placeholders = 0
        for f in frags:
            sem = json.loads(f["semantic_json"])
            if sem.get("summary") == "Visual/Audio Context":
                placeholders += 1
        if placeholders: notes.append(f"PLACEHOLDERS:{placeholders}")

        results.append({
            "source_id": sid,
            "source_label": label,
            "duration": round(duration, 2) if duration else 0,
            "fragment_count": len(frags),
            "avg_fragment_duration": round(avg_dur, 2),
            "min/max": f"{round(min_dur, 1)}s / {round(max_dur, 1)}s",
            "suspicious_notes": ", ".join(notes) if notes else "OK",
            "roles": roles
        })
        
    # Print table
    print(f"{'source_id':<12} | {'label':<15} | {'dur':<8} | {'count':<6} | {'avg':<6} | {'min/max':<12} | {'notes'}")
    print("-" * 100)
    for r in results:
        print(f"{r['source_id']:<12} | {r['source_label'][:15]:<15} | {r['duration']:<8} | {r['fragment_count']:<6} | {r['avg_fragment_duration']:<6} | {r['min/max']:<12} | {r['suspicious_notes']}")

def audit_fragment_boundaries():
    print("\n=== 2. Fragment Boundary Quality Audit ===")
    frags = query_db("SELECT * FROM semantic_fragments LIMIT 20")
    
    print(f"{'fragment_id':<20} | {'source_id':<12} | {'start/end':<15} | {'dur':<6} | {'reason':<20} | {'ev_refs':<8} | {'issue'}")
    print("-" * 120)
    
    for f in frags:
        sid = f["source_id"]
        fid = f["fragment_id"]
        start, end = f["start"], f["end"]
        dur = end - start
        
        sem = json.loads(f["semantic_json"])
        ev_refs = sem.get("evidence_refs", [])
        
        # Check thumbnail repetition (simplified: just list if possible)
        # Actually, let's check evidence_board for boundary reason if any
        evs = query_db("SELECT * FROM evidence_board WHERE fragment_id = ?", (fid,))
        boundary_reason = "N/A"
        if evs:
            ev = evs[0]
            # evidence_board has worker_sources
            ws = json.loads(ev["worker_sources"]) if ev["worker_sources"] else {}
            boundary_reason = ", ".join(ws.keys())
            
        issue = "OK"
        if dur < 2.0: issue = "TOO_SHORT"
        elif dur > 60.0: issue = "TOO_LONG"

        print(f"{fid:<20} | {sid:<12} | {round(start,1):>5}-{round(end,1):<5} | {round(dur,1):<6} | {boundary_reason[:20]:<20} | {len(ev_refs):<8} | {issue}")

def audit_proposal_engine():
    print("\n=== 3. Proposal Engine Quality Audit ===")
    proposals = query_db("SELECT * FROM proposals")
    
    print(f"{'proposal_id':<25} | {'mode':<4} | {'clips':<6} | {'dur':<6} | {'sources':<8} | {'distribution':<20} | {'score':<5} | {'issue'}")
    print("-" * 130)
    
    for p in proposals:
        pid = p["proposal_id"]
        mode = p["mode"]
        seq = json.loads(p["sequence"])
        dur = p["duration"]
        
        # Analyze source distribution
        src_counts = {}
        for clip in seq:
            sid = clip.get("source_id", "UNKNOWN")
            src_counts[sid] = src_counts.get(sid, 0) + 1
        
        used_sources = len(src_counts)
        dist_str = ", ".join([f"{s[-6:]}:{c}" for s, c in src_counts.items()])
        
        # Find repeats
        repeated = [s for s, c in src_counts.items() if c > 5] # arbitrary threshold
        
        score = p.get("confidence", 0.0)
        
        issue = "OK"
        if used_sources < 2: issue = "LOW_DIVERSITY"
        if not seq: issue = "EMPTY"

        print(f"{pid:<25} | {mode:<4} | {len(seq):<6} | {round(dur,1):<6} | {used_sources:<8} | {dist_str[:20]:<20} | {score:<5} | {issue}")

def audit_source_diversity():
    print("\n=== 4. Source Diversity Audit ===")
    sources = query_db("SELECT * FROM sources")
    proposals = query_db("SELECT * FROM proposals")
    
    source_stats = {}
    for src in sources:
        sid = src["source_id"]
        frags = query_db("SELECT count(*) as cnt FROM semantic_fragments WHERE source_id = ?", (sid,))
        source_stats[sid] = {
            "total": frags[0]["cnt"],
            "selected_A": 0,
            "selected_B": 0,
            "avg_score": 0,
            "scores": []
        }
        
    for p in proposals:
        mode = p["mode"]
        seq = json.loads(p["sequence"])
        for clip in seq:
            sid = clip.get("source_id")
            if sid in source_stats:
                if mode == "A": source_stats[sid]["selected_A"] += 1
                else: source_stats[sid]["selected_B"] += 1
                
                # Try to get edit_value
                # In sequence, clip might have edit_value
                ev = clip.get("structural", {}).get("edit_value", 0.5)
                source_stats[sid]["scores"].append(ev)

    print(f"{'source_id':<12} | {'total':<6} | {'sel_A':<6} | {'sel_B':<6} | {'avg_score':<10} | {'reason_not_selected'}")
    print("-" * 80)
    
    for sid, stat in source_stats.items():
        avg_score = sum(stat["scores"]) / len(stat["scores"]) if stat["scores"] else 0
        reason = "OK"
        if stat["selected_A"] == 0 and stat["selected_B"] == 0:
            if stat["total"] == 0: reason = "NO_FRAGMENTS"
            elif avg_score < 0.3: reason = "LOW_EDIT_VALUE"
            else: reason = "RANKED_OUT"
            
        print(f"{sid:<12} | {stat['total']:<6} | {stat['selected_A']:<6} | {stat['selected_B']:<Stat['selected_B']} | {round(avg_score,2):<10} | {reason}")

def audit_visual_evidence_integration():
    print("\n=== 7. Visual Evidence Integration Audit ===")
    # Check if EvidenceBoard has visual entries
    evs = query_db("SELECT count(*) as cnt FROM evidence_board WHERE keyframe IS NOT NULL")
    count = evs[0]["cnt"]
    
    # Check if any cognitive fragments exist (using metadata_json)
    cognitive = query_db("SELECT count(*) as cnt FROM evidence_board WHERE metadata_json LIKE '%trace_visual_candidate%'")
    cog_count = cognitive[0]["cnt"]
    
    # Check if proposals use these
    # This is hard to check without deep JSON inspection, but we can check if Qwen results are in the DB
    
    print(f"{'stage':<20} | {'connected':<10} | {'artifact_only':<15} | {'data_path'}")
    print("-" * 80)
    print(f"{'Stage 5 (VL)':<20} | {'NO':<10} | {'YES':<15} | {'artifacts/trace_batch'}")
    print(f"{'Stage 6 (Refine)':<20} | {'PARTIAL':<10} | {'NO':<15} | {'evidence_board.metadata'}")
    
    print(f"\n[DIAG] Keyframed evidences: {count}")
    print(f"[DIAG] Cognitive trace candidates: {cog_count}")

if __name__ == "__main__":
    audit_fragment_generation()
    audit_fragment_boundaries()
    audit_proposal_engine()
    audit_source_diversity()
    audit_visual_evidence_integration()
