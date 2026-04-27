import subprocess
import os

print("=== 1. PROCESS STATUS ===")
for cmd in [
    ("python", "tasklist | findstr python"),
    ("llama-server", "tasklist | findstr llama-server"),
    ("port 8000", "netstat -ano | findstr :8000"),
    ("port 8091", "netstat -ano | findstr :8091"),
]:
    print(f"[{cmd[0]}]")
    try:
        res = subprocess.run(cmd[1], shell=True, capture_output=True, text=True)
        print(res.stdout.strip() if res.stdout.strip() else "(No output)")
    except Exception as e:
        print(f"Error: {e}")

print("\n=== 2. uvicorn.log LAST 50 LINES ===")
try:
    with open("uvicorn.log", "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
        print("".join(lines[-50:]))
except Exception as e:
    print(f"Log error: {e}")
