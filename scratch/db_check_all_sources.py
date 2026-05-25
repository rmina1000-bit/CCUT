import sqlite3
import json

db_path = "ccut_backend/ccut_app.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT source_id, title, duration FROM sources;")
sources = cursor.fetchall()

print(f"{'Source ID':<15} | {'Title':<25} | {'Duration':<8} | {'Max Motion':<10} | {'Avg Audio':<9} | {'Words Count':<11}")
print("-" * 90)

for sid, title, dur in sources:
    # Max motion
    cursor.execute("SELECT MAX(motion_score), AVG(audio_energy) FROM evidence_board WHERE source_id = ?;", (sid,))
    motion_row = cursor.fetchone()
    max_motion = motion_row[0] if motion_row and motion_row[0] is not None else 0.0
    avg_audio = motion_row[1] if motion_row and motion_row[1] is not None else 0.0
    
    # Words count
    cursor.execute("SELECT intelligence FROM fragments WHERE source_id = ?;", (sid,))
    words_count = 0
    for frag_row in cursor.fetchall():
        intel = json.loads(frag_row[0]) if frag_row[0] else {}
        words_count += len(intel.get("words", []))
        
    print(f"{sid:<15} | {title:<25} | {dur:<8.2f} | {max_motion:<10.4f} | {avg_audio:<9.4f} | {words_count:<11}")

conn.close()
