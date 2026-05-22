import sqlite3
import json
import os
import sys

def audit_boundaries():
    db_path = os.path.join("ccut_backend", "ccut_app.db")
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get latest source_id
    source = cur.execute("SELECT source_id FROM sources ORDER BY created_at DESC LIMIT 1").fetchone()
    if not source:
        print("No sources found in database.")
        conn.close()
        return
    
    source_id = source["source_id"]
    print(f"Auditing Source ID: {source_id}")

    # 2. Transcript segment 조회
    evidence_segments = cur.execute("""
        SELECT fragment_id, source_id, start, end, text, worker_sources, metadata_json
        FROM evidence_board
        WHERE source_id = ?
          AND text IS NOT NULL
          AND TRIM(text) != ''
        ORDER BY start ASC
    """, (source_id,)).fetchall()

    transcript_data = []
    for row in evidence_segments:
        transcript_data.append({
            "start": row["start"],
            "end": row["end"],
            "text": row["text"],
            "id": row["fragment_id"]
        })

    # 5. Fallback check (fragments.intelligence) if no evidence text
    if not transcript_data:
        print("Checking fragments table fallback...")
        fragments = cur.execute("""
            SELECT fragment_id, start_time, end_time, intelligence 
            FROM fragments 
            WHERE source_id = ?
        """, (source_id,)).fetchall()
        for f in fragments:
            intel = json.loads(f["intelligence"]) if isinstance(f["intelligence"], str) else f["intelligence"]
            if intel and intel.get("transcript"):
                transcript_data.append({
                    "start": f["start_time"],
                    "end": f["end_time"],
                    "text": intel["transcript"],
                    "id": f["fragment_id"]
                })

    # 4. Semantic fragments 조회
    sfs = cur.execute("""
        SELECT id, fragment_id, source_id, start, end, semantic_json, structural_json
        FROM semantic_fragments
        WHERE source_id = ?
        ORDER BY start ASC
    """, (source_id,)).fetchall()

    # 문장 종결 후보
    kr_terminators = ('다.', '요.', '죠.', '까.', '네.', '음.', '!', '?', '…')
    en_terminators = ('.', '!', '?')
    all_terminators = kr_terminators + en_terminators

    print(f"{'SF_ID':<20} | {'SF_END':>7} | {'TXT_END':>7} | {'GAP':>7} | {'CUT':<5} | {'TEXT'}")
    print("-" * 100)

    audit_results = []
    suspect_rows = []

    for sf in sfs:
        sf_id = sf["fragment_id"]
        sf_start = sf["start"]
        sf_end = sf["end"]
        
        # Find nearest transcript segment that overlaps or is near sf_end
        nearest_segment = None
        min_end_dist = float('inf')
        
        for seg in transcript_data:
            # We care about segments that contain or are near the sf_end
            if seg["start"] <= sf_end <= seg["end"] + 0.5:
                dist = abs(seg["end"] - sf_end)
                if dist < min_end_dist:
                    min_end_dist = dist
                    nearest_segment = seg

        if not nearest_segment:
            # Fallback to absolute nearest end
            for seg in transcript_data:
                dist = abs(seg["end"] - sf_end)
                if dist < min_end_dist:
                    min_end_dist = dist
                    nearest_segment = seg

        txt_start = nearest_segment["start"] if nearest_segment else 0.0
        txt_end = nearest_segment["end"] if nearest_segment else 0.0
        txt_text = nearest_segment["text"] if nearest_segment else ""
        gap = abs(txt_end - sf_end)
        
        # Cutting judgment
        mid_sentence_cut = False
        reason = ""
        
        if nearest_segment:
            # 1. sf_end가 segment.end보다 0.3초 이상 빠름
            if sf_end < txt_end - 0.3:
                mid_sentence_cut = True
                reason = f"End gap {gap:.2f}s"
            
            # 2. text가 종결 형태가 아님
            text_clean = txt_text.strip()
            if not any(text_clean.endswith(t) for t in all_terminators):
                # Only suspect if it's a significant segment
                if len(text_clean) > 5:
                    mid_sentence_cut = True
                    reason += " | Non-terminating" if reason else "Non-terminating"

        result = {
            "source_id": source_id,
            "semantic_fragment_id": sf_id,
            "sf_start": sf_start,
            "sf_end": sf_end,
            "nearest_text_start": txt_start,
            "nearest_text_end": txt_end,
            "transcript_text": txt_text,
            "boundary_gap_sec": gap,
            "possible_mid_sentence_cut": mid_sentence_cut,
            "reason": reason
        }
        audit_results.append(result)
        if mid_sentence_cut:
            suspect_rows.append(result)

        cut_str = "YES" if mid_sentence_cut else "NO"
        print(f"{sf_id:<20} | {sf_end:>7.2f} | {txt_end:>7.2f} | {gap:>7.2f} | {cut_str:<5} | {txt_text[:30]}")

    print(f"\nTotal Suspect Rows: {len(suspect_rows)}")
    print("\n--- Top 3 Suspect Cases ---")
    for row in suspect_rows[:3]:
        print(f"ID: {row['semantic_fragment_id']}, Gap: {row['boundary_gap_sec']:.2f}s, Reason: {row['reason']}")
        print(f"Text: {row['transcript_text']}")
        print("-" * 20)

    conn.close()

if __name__ == "__main__":
    audit_boundaries()
