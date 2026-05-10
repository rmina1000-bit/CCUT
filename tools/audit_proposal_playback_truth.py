import sqlite3
import json
import os
import sys

def row_get(row, key, default=None):
    try:
        if row is None:
            return default
        if hasattr(row, "keys") and key in row.keys():
            return row[key]
        if isinstance(row, dict):
            return row.get(key, default)
    except Exception:
        pass
    return default


def parse_json_maybe(value, default=None):
    if default is None:
        default = {}
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def get_sequence_fragment_id(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return (
            item.get("fragment_id")
            or item.get("source_fragment_id")
            or item.get("id")
            or item.get("fragment_uid")
        )
    return None

def audit_playback():
    db_path = r"d:/CCUT1.0.4/ccut_backend/ccut_app.db"
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # 1. Get latest proposals
        cur.execute("SELECT proposal_id, mode, sequence, created_at FROM proposals ORDER BY created_at DESC LIMIT 10")
        proposal_rows = cur.fetchall()

        if not proposal_rows:
            print("No proposals found in DB.")
            return

        print(f"\n{'='*140}")
        print(f"{'STEP 10-K-C1-R34 Proposal Playback Ground Truth Audit (REFINED)':^140}")
        print(f"{'='*140}\n")

        for p_row in proposal_rows:
            proposal_id = row_get(p_row, "proposal_id")
            mode = row_get(p_row, "mode")
            sequence_raw = row_get(p_row, "sequence")
            created_at = row_get(p_row, "created_at")

            if not sequence_raw:
                continue

            sequence = parse_json_maybe(sequence_raw, [])
            
            print(f"Proposal: {proposal_id} | Mode: {mode} | Created: {created_at} | Items: {len(sequence)}")
            print("-" * 155)
            header = f"{'Order':<5} | {'FragID':<30} | {'Source':<12} | {'StartF':<8} | {'EndF':<8} | {'StartS':<8} | {'EndS':<8} | {'DurS':<6} | {'Contig':<6} | {'Gap':<6} | {'Thumb'}"
            print(header)
            print("-" * 155)

            prev_frag = None
            contig_count = 0
            total_items = len(sequence)

            for i, item in enumerate(sequence):
                frag_id = get_sequence_fragment_id(item)
                if not frag_id:
                    print(f"{i+1:<5} | {'INVALID ITEM':<30} | Raw: {item}")
                    continue

                # Query full fragment data
                cur.execute("SELECT * FROM fragments WHERE fragment_id = ?", (frag_id,))
                f_data = cur.fetchone()

                table_origin = "fragments"
                if not f_data:
                    # Try semantic_fragments if not found in fragments
                    cur.execute("SELECT * FROM semantic_fragments WHERE fragment_id = ?", (frag_id,))
                    f_data = cur.fetchone()
                    table_origin = "semantic_fragments"

                if not f_data:
                    # [STEP 10-K-C1-R35-AUDIT-FIX] Try to extract metadata from the raw sequence item if DB lookup fails
                    start_sec = float(row_get(item, "start", row_get(item, "start_time", 0.0)) or 0.0)
                    end_sec = float(row_get(item, "end", row_get(item, "end_time", start_sec)) or start_sec)
                    source_id = row_get(item, "source_id", "UNKNOWN")
                    start_frame = int(round(start_sec * 30))
                    end_frame = int(round(end_sec * 30))
                    thumb_url = row_get(item, "thumb_url", row_get(item, "thumbnail_url", "None"))
                    
                    print(f"{i+1:<5} | {frag_id:<30} | {source_id:<12} (RAW) | {start_frame:<8} | {end_frame:<8} | {start_sec:<8.2f} | {end_sec:<8.2f} | {end_sec-start_sec:<6.2f}")
                    # Continue with contiguity check using raw data
                else:
                    # Metadata extraction
                    intel = parse_json_maybe(row_get(f_data, "intelligence"))
                    if table_origin == "semantic_fragments":
                        sem_json = parse_json_maybe(row_get(f_data, "semantic_json"))
                        struc_json = parse_json_maybe(row_get(f_data, "structural_json"))
                        intel.update(sem_json)
                        intel.update(struc_json)
                    
                    # Frames/Time
                    start_sec = (
                        row_get(f_data, "start_time")
                        if row_get(f_data, "start_time") is not None
                        else row_get(f_data, "start", 0.0)
                    )
                    end_sec = (
                        row_get(f_data, "end_time")
                        if row_get(f_data, "end_time") is not None
                        else row_get(f_data, "end", 0.0)
                    )
                    
                    # Check for frames in intelligence or structural
                    start_frame = intel.get("start_frame")
                    end_frame = intel.get("end_frame")
                    
                    if start_frame is None: start_frame = int(round(start_sec * 30))
                    if end_frame is None: end_frame = int(round(end_sec * 30))
                    
                    duration = end_sec - start_sec
                    source_id = row_get(f_data, "source_id", "UNKNOWN")
                    
                    # Thumbnail lookup
                    thumb_url = (
                        intel.get("thumb_url") 
                        or intel.get("thumbnail_url") 
                        or row_get(f_data, "thumbnail_url")
                        or (intel.get("thumbnail") or {}).get("thumbnail_url")
                        or "None"
                    )

                    row_str = f"{i+1:<5} | {frag_id:<30} | {source_id:<12} | {start_frame:<8} | {end_frame:<8} | {start_sec:<8.2f} | {end_sec:<8.2f} | {duration:<6.2f}"
                    # print(row_str, end="") # Moved print to after contig calc

                # Contiguity check
                contig = "N/A"
                gap = 0.0
                if prev_frag:
                    if prev_frag["source_id"] == source_id:
                        gap = start_sec - prev_frag["end_sec"]
                        if abs(gap) < 0.15:
                            contig = "YES"
                            contig_count += 1
                        else:
                            contig = "NO"
                    else:
                        contig = "DIFF"

                row_str = f"{i+1:<5} | {frag_id:<30} | {source_id:<12} | {start_frame:<8} | {end_frame:<8} | {start_sec:<8.2f} | {end_sec:<8.2f} | {duration:<6.2f} | {contig:<6} | {gap:<6.2f} | {os.path.basename(thumb_url)}"
                print(row_str)

                prev_frag = {
                    "source_id": source_id,
                    "end_sec": end_sec
                }

            contig_ratio = (contig_count / (total_items - 1) * 100) if total_items > 1 else 0
            print("-" * 155)
            print(f"Contiguity: {contig_count}/{total_items-1} ({contig_ratio:.1f}%)")
            
            # Final Verdict
            verdict = "UNKNOWN"
            if contig_ratio > 70:
                verdict = "PROPOSAL_CONTIGUOUS (Playback likely looks cumulative by design)"
            elif contig_ratio < 30:
                verdict = "NON_CONTIGUOUS (If it looks cumulative, it is a PLAYER_BUG)"
            else:
                verdict = "MIXED"
            
            print(f"Verdict: {verdict}\n")

    except Exception as e:
        print(f"Error during audit: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    audit_playback()
