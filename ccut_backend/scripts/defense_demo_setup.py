import subprocess
import os
import json
import uuid

# ?ㅼ젙
UPLOAD_DIR = r"D:\CCUT_1.0.3\ccut_backend\storage\uploads"
DB_PATH = r"D:\CCUT_1.0.3\ccut_backend\ccut_database.db"

video_urls = [
    "https://www.youtube.com/shorts/kGwA_IZtXBw",
    "https://www.youtube.com/shorts/m2BstamzpiM",
    "https://www.youtube.com/shorts/oeB9ccN0oVY",
    "https://www.youtube.com/shorts/o-DqLtzRmYY",
    "https://www.youtube.com/shorts/XGjEcLSZiLY",
    "https://www.youtube.com/shorts/t1v3ftU5kDw",
    "https://www.youtube.com/shorts/OWAHTyku4NQ",
    "https://www.youtube.com/shorts/5KvQcul-ngk",
    "https://www.youtube.com/shorts/97MxSMIut1A",
    "https://www.youtube.com/shorts/-6qTpwqsY3M"
]

def download_video(url, index):
    print(f"[{index+1}/10] Downloading {url}...")
    source_id = f"SRC_DEFENSE_{index+1:03d}"
    output_template = os.path.join(UPLOAD_DIR, f"{source_id}.%(ext)s")
    
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        url
    ]
    
    try:
        subprocess.run(cmd, check=True)
        filename = f"{source_id}.mp4"
        filepath = os.path.join(UPLOAD_DIR, filename)
        return source_id, filename, filepath
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None, None, None

def get_video_duration(filepath):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except:
        return 0.0

def register_in_db(source_id, filename, filepath, duration):
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # ensure status exists even if it's not in the sqlalchemy model yet (v1.0.3)
    # wait, my sqlalchemy model doesn't have status in sources, only in fragments.
    # so just title, filepath, duration.
    title = f"Defense Demo Video {source_id[-3:]}"
    cursor.execute("""
        INSERT OR REPLACE INTO sources (source_id, title, file_path, duration, created_at)
        VALUES (?, ?, ?, ?, DATETIME('now'))
    """, (source_id, title, filepath, duration))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
        
    for i, url in enumerate(video_urls):
        sid, fname, fpath = download_video(url, i)
        if sid and os.path.exists(fpath):
            dur = get_video_duration(fpath)
            register_in_db(sid, fname, fpath, dur)
            print(f"Registered {sid} - {dur}s")

