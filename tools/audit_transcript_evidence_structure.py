import sqlite3
import json
import os

def audit_structure(source_id=None):
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
    
    print(f"=== Structural Audit for Source: {source_id} ===")

    # A. evidence_board.text rows
    print("\n[A] Evidence Board Text Statistics")
    evidences = cur.execute("""
        SELECT fragment_id, start, end, text, worker_sources, metadata_json
        FROM evidence_board
        WHERE source_id = ? AND text IS NOT NULL AND text != ''
        ORDER BY start ASC
    """, (source_id,)).fetchall()
    
    print(f"Count: {len(evidences)}")
    if evidences:
        durations = [(e["end"] - e["start"]) for e in evidences]
        avg_dur = sum(durations) / len(durations)
        max_dur = max(durations)
        print(f"Average Duration: {avg_dur:.2f}s")
        print(f"Max Duration: {max_dur:.2f}s")
        
        print(f"{'ID':<30} | {'START':>7} | {'END':>7} | {'DUR':>7} | {'LEN':>5} | {'TEXT PREVIEW'}")
        for e in evidences[:10]:
            print(f"{e['fragment_id']:<30} | {e['start']:>7.2f} | {e['end']:>7.2f} | {e['end']-e['start']:>7.2f} | {len(e['text']):>5} | {e['text'][:30]!r}")
        
        # Check workers
        workers = set()
        for e in evidences:
            ws = json.loads(e["worker_sources"]) if isinstance(e["worker_sources"], str) else e["worker_sources"]
            if ws:
                workers.update(ws.values())
        print(f"Workers involved: {list(workers)}")

    # B. fragments.intelligence rows
    print("\n[B] Fragments Intelligence Statistics")
    fragments = cur.execute("""
        SELECT fragment_id, start_time, end_time, intelligence
        FROM fragments
        WHERE source_id = ?
        ORDER BY start_time ASC
    """, (source_id,)).fetchall()
    
    print(f"Count: {len(fragments)}")
    if fragments:
        has_words_count = 0
        total_words = 0
        for f in fragments:
            intel = json.loads(f["intelligence"]) if isinstance(f["intelligence"], str) else f["intelligence"]
            if intel and intel.get("words"):
                has_words_count += 1
                total_words += len(intel["words"])
        
        print(f"Fragments with 'words': {has_words_count}")
        if has_words_count > 0:
            print(f"Total Words: {total_words}")
            # Sample first/last words of the first fragment that has them
            for f in fragments:
                intel = json.loads(f["intelligence"]) if isinstance(f["intelligence"], str) else f["intelligence"]
                if intel and intel.get("words"):
                    words = intel["words"]
                    print(f"Sample Fragment: {f['fragment_id']}")
                    print(f"Intelligence keys: {list(intel.keys())}")
                    print(f"First 5 words: {words[:5]}")
                    print(f"Last 5 words: {words[-5:]}")
                    if words:
                        print(f"Word schema check: {list(words[0].keys())}")
                    break
        else:
            # Check intelligence keys anyway
            intel = json.loads(fragments[0]["intelligence"]) if isinstance(fragments[0]["intelligence"], str) else fragments[0]["intelligence"]
            print(f"Intelligence keys: {list(intel.keys()) if intel else 'None'}")

    # C. semantic_fragments rows
    print("\n[C] Semantic Fragments Statistics")
    sfs = cur.execute("""
        SELECT fragment_id, start, end, semantic_json
        FROM semantic_fragments
        WHERE source_id = ?
        ORDER BY start ASC
    """, (source_id,)).fetchall()
    
    print(f"Count: {len(sfs)}")
    if sfs:
        durations = [(sf["end"] - sf["start"]) for sf in sfs]
        print(f"Average Duration: {sum(durations)/len(durations):.2f}s")
        print(f"Min Duration: {min(durations):.2f}s")
        print(f"Max Duration: {max(durations):.2f}s")
        
        print(f"{'ID':<30} | {'START':>7} | {'END':>7} | {'DUR':>7} | {'SUMMARY'}")
        for sf in sfs[:10]:
            sem = json.loads(sf["semantic_json"]) if isinstance(sf["semantic_json"], str) else sf["semantic_json"]
            print(f"{sf['fragment_id']:<30} | {sf['start']:>7.2f} | {sf['end']:>7.2f} | {sf['end']-sf['start']:>7.2f} | {sem.get('summary', '')[:40]!r}")

    conn.close()

if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else "SRC_616AEFBA"
    audit_structure(sid)
