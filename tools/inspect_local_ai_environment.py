import os
import sys
import platform
import subprocess
import json

def get_gpu_info():
    """Attempt to get GPU info via nvidia-smi."""
    try:
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], encoding='utf-8')
        lines = output.strip().split('\n')
        gpus = []
        for line in lines:
            name, vram = line.split(',')
            gpus.append({"name": name.strip(), "vram_mb": int(vram.strip())})
        return gpus
    except:
        return []

def inspect_environment():
    """Probe system for AI capability potential (Dry-Run)."""
    
    info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "python_version": sys.version.split()[0],
        "cpu": platform.processor(),
        "ram_gb": round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024**3)) if hasattr(os, 'sysconf') else "Unknown (Windows/Other)",
        "gpus": get_gpu_info(),
        "cuda_path": os.environ.get("CUDA_PATH", "Not set"),
        "ports_busy": {
            "8000": "Checking...",
            "8080": "Checking..."
        }
    }
    
    print("--- CCUT Local AI Compatibility Probe (Dry-Run) ---")
    print(json.dumps(info, indent=4))
    
    # Model feasibility estimates (Purely for orientation)
    print("\n[Estimated Feasibility - Orientation Only]")
    if info["gpus"]:
        total_vram = sum(g["vram_mb"] for g in info["gpus"])
        print(f"Total VRAM: {total_vram} MB")
        if total_vram >= 12000:
            print("- Qwen3-Instruct (8B Q6_K): Likely OK (Target Grade)")
        elif total_vram >= 7000:
            print("- Qwen3-Instruct (4B/7B Q4_K): OK (Standard Grade)")
        else:
            print("- Qwen3-Instruct (1.5B/4B Q3_K): Possible (Minimum Grade)")
    else:
        print("- No NVIDIA GPU detected. Heavy reliance on CPU/AVX-512.")

    print("\n[Note] This probe does not run any models. It only inspects the environment metadata.")

if __name__ == "__main__":
    inspect_environment()
