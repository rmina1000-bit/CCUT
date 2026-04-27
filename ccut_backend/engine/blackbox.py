import os
import psutil
import time
import json
import datetime
from pathlib import Path

LOG_PATH = Path("d:/CCUT_1.0.3/ccut_backend/storage/blackbox.log")

class BlackBoxRecorder:
    @staticmethod
    def log(category, msg, data=None):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        log_entry = {
            "timestamp": timestamp,
            "category": category,
            "message": msg,
            "data": data
        }
        # 利됱떆 ?뚯씪???곌린 (踰꾪띁 釉붾줈??諛⑹?)
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except:
            pass
        print(f"[{category}] {msg}")

    @staticmethod
    def record_system_stats():
        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            py_proc = psutil.Process(os.getpid())
            py_mem = py_proc.memory_info().rss / (1024 * 1024)
            
            ffmpeg_list = []
            for proc in psutil.process_iter(['name', 'pid', 'cpu_percent', 'memory_info']):
                if "ffmpeg" in proc.info['name'].lower():
                    ffmpeg_list.append({
                        "pid": proc.info['pid'],
                        "cpu": proc.info['cpu_percent'],
                        "mem_mb": proc.info['memory_info'].rss / (1024 * 1024)
                    })
            
            BlackBoxRecorder.log("SYSTEM", "Stats Update", {
                "system_cpu": cpu,
                "system_mem": mem,
                "python_mem_mb": py_mem,
                "active_ffmpegs": ffmpeg_list
            })
        except Exception as e:
            BlackBoxRecorder.log("ERROR", f"Stats failed: {e}")

blackbox = BlackBoxRecorder()

