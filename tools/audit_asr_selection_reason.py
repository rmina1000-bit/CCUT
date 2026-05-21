import sqlite3
import json
import os

def audit_selection(source_id=None):
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
    
    print(f"=== ASR Selection Audit: {source_id} ===")

    # Fetch fragments and their intelligence
    fragments = cur.execute("""
        SELECT fragment_id, start_time, end_time, intelligence
        FROM fragments
        WHERE source_id = ?
        ORDER BY start_time ASC
    """, (source_id,)).fetchall()

    # Fetch evidence board
    evidences = cur.execute("""
        SELECT fragment_id, text, audio_energy, silence, scene_change, worker_sources, metadata_json
        FROM evidence_board
        WHERE source_id = ?
    """, (source_id,)).fetchall()
    
    ev_map = {e["fragment_id"]: dict(e) for e in evidences}

    print(f"{'ID':<25} | {'START':>7} | {'TXT':<3} | {'HOOK':>5} | {'ROLE':<8} | {'ENERGY':>6} | {'SCENE':<5}")
    print("-" * 90)

    for f in fragments:
        fid = f["fragment_id"]
        # Safe JSON parsing for intelligence
        try:
            intel_raw = f["intelligence"]
            intel = json.loads(intel_raw) if isinstance(intel_raw, str) else intel_raw
            if intel is None: intel = {}
        except Exception:
            intel = {}

        ev = ev_map.get(fid, {})
        
        # Accessing via .get() after dict conversion
        txt_val = intel.get("transcript") or ev.get("text")
        has_text = "YES" if txt_val else "NO"
        
        hook = intel.get("hook_score", 0.0)
        role = intel.get("role", "None")
        energy = ev.get("audio_energy", 0.0)
        
        scene_raw = ev.get("scene_change")
        try:
            scene_list = json.loads(scene_raw) if isinstance(scene_raw, str) else scene_raw
            scene_exists = "YES" if (scene_list and len(scene_list) > 0) else "NO"
        except Exception:
            scene_exists = "NO"
        
        print(f"{fid:<25} | {f['start_time']:>7.1f} | {has_text:<3} | {hook:>5.2f} | {role:<8} | {energy:>6.2f} | {scene_exists:<5}")

    conn.close()

if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else None
    audit_selection(sid)
