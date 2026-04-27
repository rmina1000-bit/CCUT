import subprocess
import time
import sys

cmd = [
    r"D:\CCUT_1.0.3\tools\llama.cpp-vulkan\llama-server.exe",
    "-m", r"D:/CCUT_1.0.3/ccut_backend/ai_models/qwen3-asr-1.7b/Qwen3-ASR-1.7B-Q8_0.gguf",
    "--mmproj", r"D:/CCUT_1.0.3/ccut_backend/ai_models/qwen3-asr-1.7b/mmproj-Qwen3-ASR-1.7B-Q8_0.gguf",
    "--port", "8092",
    "--host", "127.0.0.1",
    "--ctx-size", "4096",
    "--n-gpu-layers", "99"
]

print("Starting vulkan server...")
with open("test_vulkan.log", "w", encoding="utf-8") as f:
    p = subprocess.Popen(cmd, stdout=f, stderr=f)

print(f"PID: {p.pid}")
time.sleep(15) # wait for model to load
for i in range(10):
    time.sleep(3)
    if p.poll() is not None:
        print(f"Server crashed! Exit code: {p.returncode}")
        break
    try:
        import urllib.request
        res = urllib.request.urlopen("http://127.0.0.1:8092/health").read().decode()
        print("Health check:", res)
        break
    except Exception as e:
        pass

p.terminate()
try:
    p.wait(timeout=10)
    print("Terminated successfully.")
except:
    p.kill()
