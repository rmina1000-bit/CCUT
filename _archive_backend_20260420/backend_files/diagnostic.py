import sqlite3
import subprocess

print("=== 1. llama-server ===")
try:
    print(subprocess.run("tasklist | findstr llama-server", shell=True, capture_output=True, text=True).stdout.strip())
except Exception as e:
    print(e)
    
print("\n=== 2. uvicorn.log Last 30 lines ===")
try:
    with open("uvicorn.log", "r", encoding="utf-8", errors="replace") as f:
        print("".join(f.readlines()[-30:]))
except Exception as e:
    print(e)

print("\n=== 3. DB Fragments Count ===")
try:
    c = sqlite3.connect("D:/CCUT_1.0.3/ccut_database.db")
    print("Count:", c.execute("SELECT count(*) FROM fragments").fetchone()[0])
    c.close()
except Exception as e:
    print(e)
