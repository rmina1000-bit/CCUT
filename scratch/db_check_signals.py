import sqlite3
import json

db_path = "ccut_backend/ccut_app.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

source_id = 'SRC_B1A26714'

# Count total rows
cursor.execute("SELECT COUNT(*) FROM evidence_board WHERE source_id = ?;", (source_id,))
print(f"Evidence Board rows for {source_id}: {cursor.fetchone()[0]}")

# Get min, max, avg for motion_score, audio_energy
cursor.execute("""
    SELECT MIN(motion_score), MAX(motion_score), AVG(motion_score),
           MIN(audio_energy), MAX(audio_energy), AVG(audio_energy)
    FROM evidence_board
    WHERE source_id = ?;
""", (source_id,))
row = cursor.fetchone()
print(f"Motion score stats: min={row[0]}, max={row[1]}, avg={row[2]}")
print(f"Audio energy stats: min={row[3]}, max={row[4]}, avg={row[5]}")

# Check any non-zero or non-null fields in evidence_board
cursor.execute("""
    SELECT COUNT(*) FROM evidence_board 
    WHERE source_id = ? AND (motion_score > 0 OR audio_energy > 0 OR text IS NOT NULL OR speaker IS NOT NULL);
""", (source_id,))
print(f"Rows with non-zero or non-null values: {cursor.fetchone()[0]}")

# Let's inspect some row details
cursor.execute("SELECT fragment_id, start, end, motion_score, audio_energy, scene_change, silence FROM evidence_board WHERE source_id = ? LIMIT 5;", (source_id,))
for r in cursor.fetchall():
    print(f"Frag: {r[0]}, Range: {r[1]} -> {r[2]}, Motion: {r[3]}, Audio: {r[4]}, SceneChange: {r[5]}, Silence: {r[6]}")

# Check words from fragments
cursor.execute("SELECT COUNT(*) FROM fragments WHERE source_id = ?;", (source_id,))
print(f"Fragments rows: {cursor.fetchone()[0]}")
cursor.execute("SELECT fragment_id, intelligence FROM fragments WHERE source_id = ? LIMIT 5;", (source_id,))
for r in cursor.fetchall():
    intel = json.loads(r[1]) if r[1] else {}
    print(f"Frag: {r[0]} | words key exists: {'words' in intel} | words len: {len(intel.get('words', [])) if 'words' in intel else 0}")

conn.close()
