# Local LLM Compatibility Probe Specification

## 1. Overview
The **Local AI Compatibility Probe** is a diagnostic tool used to assess a machine's potential for running CCUT's AI Staff. It performs a "dry-run" inspection of system metadata without loading actual model weights.

## 2. Probe Methodology (`inspect_local_ai_environment.py`)
The probe checks for the following:
- **OS & Python**: Basic environment compatibility.
- **System RAM**: Total available memory.
- **GPU Presence**: Specifically NVIDIA GPUs via `nvidia-smi`.
- **VRAM Total**: Sum of all available video memory.
- **CUDA Environment**: Presence of `CUDA_PATH` and runtime environment variables.

## 3. Compatibility Logic
The probe maps detected VRAM to model grades:
- **Target Grade (12GB+ VRAM)**: Suitable for Qwen3-Instruct (8B) at high precision.
- **Standard Grade (7GB - 12GB VRAM)**: Suitable for Qwen3-Instruct (4B/7B) at standard precision.
- **Minimum Grade (4GB - 7GB VRAM)**: Suitable for small models (1.5B) or extreme quantization.

## 4. Usage
This tool is primarily for:
- Developers checking their Dev-PC status.
- Future automated installers recommending the best model variant for the user's hardware.

## 5. Non-Execution Principle
The probe **never** executes a model. It provides estimates based on documented memory requirements for GGUF-quantized models.
