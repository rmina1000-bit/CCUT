import sqlite3
import json
import os
import sys
import re

def audit_sf_boundary_snap(source_id=None):
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
            print("No sources found in database.")
            conn.close()
            return
        source_id = source["source_id"]

    # 1. Fetch semantic fragments
    sfs = cur.execute("""
        SELECT id, fragment_id, start, end, semantic_json, structural_json 
        FROM semantic_fragments 
        WHERE source_id = ? 
        ORDER BY start
    """, (source_id,)).fetchall()

    total_sfs = len(sfs)

    # 2. Fetch fragments and words
    fragments = cur.execute("""
        SELECT fragment_id, start_time, end_time, intelligence 
        FROM fragments 
        WHERE source_id = ?
    """, (source_id,)).fetchall()

    puncs = ('.', '?', '!', '…', '。')
    korean_endings = ('다', '요', '죠', '네', '까', '나')
    all_endings = puncs + korean_endings

    candidates = {} # round(timestamp, 2) -> (timestamp, source, text)
    candidate_details = []
    words_available_count = 0

    for frag in fragments:
        intel_str = frag["intelligence"]
        if not intel_str:
            continue
        try:
            intel = json.loads(intel_str) if isinstance(intel_str, str) else intel_str
        except Exception:
            continue

        transcript = intel.get("transcript", "")
        words = intel.get("words", [])
        words_available_count += len(words)

        # A. Process words using sequential alignment
        if words:
            current_pos = 0
            word_spans = []
            for w in words:
                w_text = w.get("word", "")
                if not w_text:
                    continue
                # Sequential search in transcript
                pos = transcript.find(w_text, current_pos)
                if pos != -1:
                    word_spans.append({
                        "word": w_text,
                        "start_time": w.get("start"),
                        "end_time": w.get("end"),
                        "start_char": pos,
                        "end_char": pos + len(w_text)
                    })
                    current_pos = pos + len(w_text)
                else:
                    pos = transcript.find(w_text)
                    if pos != -1:
                        word_spans.append({
                            "word": w_text,
                            "start_time": w.get("start"),
                            "end_time": w.get("end"),
                            "start_char": pos,
                            "end_char": pos + len(w_text)
                        })
                        current_pos = pos + len(w_text)

            if not word_spans:
                for w in words:
                    w_text = w.get("word", "").strip()
                    t = w.get("end")
                    if t is not None and w_text:
                        is_end = w_text[-1] in all_endings or w_text[-1] in korean_endings
                        if is_end:
                            rounded = round(t, 2)
                            if rounded not in candidates:
                                candidates[rounded] = (t, "word_ends_with_ending_fallback", w_text)
                                candidate_details.append({
                                    "time": round(t, 3),
                                    "word": w_text,
                                    "source_fragment_id": frag["fragment_id"],
                                    "source_type": "word_ending",
                                    "reason": "fallback_ending"
                                })

            for ws in word_spans:
                w_text = ws["word"].strip()
                end_char = ws["end_char"]
                t = ws["end_time"]
                if t is None:
                    continue

                is_end = False
                reason = ""

                # Condition 1: Word text ends with punctuation or ending
                if w_text and w_text[-1] in all_endings:
                    is_end = True
                    reason = "word_ends_with_ending"

                # Condition 2: Followed by punctuation in transcript
                if not is_end:
                    lookahead = transcript[end_char:end_char+5].strip()
                    if lookahead and lookahead[0] in puncs:
                        is_end = True
                        reason = "followed_by_punctuation"

                # Condition 3: Word text ends with Korean ending
                if not is_end:
                    if w_text and w_text[-1] in korean_endings:
                        is_end = True
                        reason = "word_ends_with_korean_ending"

                if is_end:
                    rounded = round(t, 2)
                    if rounded not in candidates:
                        candidates[rounded] = (t, f"word_span_{reason}", w_text)
                        source_type_mapped = "word_ending"
                        if reason == "followed_by_punctuation":
                            source_type_mapped = "followed_by_punctuation"
                        candidate_details.append({
                            "time": round(t, 3),
                            "word": w_text,
                            "source_fragment_id": frag["fragment_id"],
                            "source_type": source_type_mapped,
                            "reason": f"word_span_{reason}"
                        })

        # B. Fragment transcript end
        if transcript:
            transcript_stripped = transcript.strip()
            if transcript_stripped and transcript_stripped[-1] in all_endings:
                t = frag["end_time"]
                if t is not None:
                    rounded = round(t, 2)
                    if rounded not in candidates:
                        candidates[rounded] = (t, "fragment_transcript_end", transcript_stripped[-20:])
                        candidate_details.append({
                            "time": round(t, 3),
                            "word": transcript_stripped[-20:],
                            "source_fragment_id": frag["fragment_id"],
                            "source_type": "fragment_transcript_end",
                            "reason": "fragment_transcript_end"
                        })

    # 3. Fetch evidence board text ends
    evidence_board = cur.execute("""
        SELECT fragment_id, start, end, text 
        FROM evidence_board 
        WHERE source_id = ?
    """, (source_id,)).fetchall()

    for ev in evidence_board:
        text = ev["text"]
        if text:
            text_stripped = text.strip()
            if text_stripped and text_stripped[-1] in all_endings:
                t = ev["end"]
                if t is not None:
                    rounded = round(t, 2)
                    if rounded not in candidates:
                        candidates[rounded] = (t, "evidence_board_text_end", text_stripped[-20:])
                        candidate_details.append({
                            "time": round(t, 3),
                            "word": text_stripped[-20:],
                            "source_fragment_id": ev["fragment_id"],
                            "source_type": "evidence_board_text_end",
                            "reason": "evidence_board_text_end"
                        })

    sentence_end_candidates_count = len(candidates)

    # 4. Align semantic fragments and find gaps
    candidate_timestamps = [v[0] for v in candidates.values()]

    misaligned_count = 0
    # snap_candidate_count = 0
    max_sentence_gap_sec = 0.0
    misaligned_rows = []

    for sf in sfs:
        sf_end = sf["end"]
        sf_id = sf["fragment_id"]
        
        # Parse semantic/structural JSON
        sem = json.loads(sf["semantic_json"]) if isinstance(sf["semantic_json"], str) else sf["semantic_json"]
        summary = sem.get("summary", "")

        if not candidate_timestamps:
            gap = 999.0
            nearest_cand = None
        else:
            nearest_cand = min(candidate_timestamps, key=lambda x: abs(x - sf_end))
            gap = abs(nearest_cand - sf_end)

        is_misaligned = gap > 0.1
        if is_misaligned:
            misaligned_count += 1
            # if gap <= 3.0:
            #     snap_candidate_count += 1
            if gap > max_sentence_gap_sec and gap < 999.0:
                max_sentence_gap_sec = gap
            
            misaligned_rows.append({
                "fragment_id": sf_id,
                "start": sf["start"],
                "end": sf_end,
                "nearest_cand": nearest_cand,
                "gap": gap,
                "summary": summary
            })

    misaligned_rows.sort(key=lambda x: x["gap"], reverse=True)
    top_3_misaligned = misaligned_rows[:3]

    real_word_snap_candidate_count = 0
    derived_boundary_candidate_count = 0

    for row in misaligned_rows:
        if row["gap"] <= 2.0:
            nearest_detail = next(
                (cd for cd in candidate_details
                 if row["nearest_cand"] is not None and abs(cd["time"] - row["nearest_cand"]) < 0.02),
                None
            )
            if nearest_detail and nearest_detail["source_type"] in ("word_ending", "followed_by_punctuation"):
                real_word_snap_candidate_count += 1
            else:
                derived_boundary_candidate_count += 1

    print("=== SUMMARY ===")
    print(f"total_sfs: {total_sfs}")
    print(f"words_available_count: {words_available_count}")
    print(f"sentence_end_candidates_count: {sentence_end_candidates_count}")
    print(f"misaligned_count: {misaligned_count}")
    print(f"real_word_snap_candidate_count: {real_word_snap_candidate_count}")
    print(f"derived_boundary_candidate_count: {derived_boundary_candidate_count}")
    print(f"max_sentence_gap_sec: {max_sentence_gap_sec:.4f}")
    print("top 3 misaligned rows:")
    for idx, row in enumerate(top_3_misaligned, 1):
        if row["nearest_cand"] is None:
            nearest_text = "None"
        else:
            nearest_text = f"{row['nearest_cand']:.2f}s"
        print(f"  - Row {idx}: ID={row['fragment_id']}, start={row['start']:.2f}s, end={row['end']:.2f}s, nearest_candidate={nearest_text}, gap={row['gap']:.4f}s, summary={row['summary']}")

    print("\n=== P002 Candidate Details (32.0s ~ 34.5s) ===")
    p002_details = [cd for cd in candidate_details if 32.0 <= cd["time"] <= 34.5]
    p002_details.sort(key=lambda x: x["time"])
    for cd in p002_details:
        print(f"  time={cd['time']:.2f} word={repr(cd['word'])} source={cd['source_fragment_id']} type={cd['source_type']} reason={cd['reason']}")

    conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sid = sys.argv[1]
    else:
        sid = None
    audit_sf_boundary_snap(sid)
