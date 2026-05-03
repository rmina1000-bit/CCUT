# Local LLM Runtime Options

## 1. Overview
CCUT targets local execution of Narrative LLMs. Several runtime options are available for hosting GGUF or other optimized model formats.

## 2. Runtime Candidates

### A. llama.cpp / llama-server
- **Pros**: Extremely lightweight, cross-platform (Windows Vulkan/CUDA), no daemon required, same tech as Qwen3-ASR.
- **Cons**: Requires manual management of server binaries and ports.
- **Suitability**: High. Recommended for a unified ASR/LLM experience. (Current status: Secondary candidate / Manual probe required)

### B. Ollama
- **Pros**: One-click installation on Windows, automatic model management, clean REST API.
- **Cons**: Background daemon required, slightly more abstraction than raw llama-server.
- **Suitability**: High. (Current status: Primary candidate / R9-R10 probe detected qwen2 and qwen3:0.6b).
- **Validation Target**: `qwen3:4b` (R10-C Baseline).
- **Note**: Experimental probe of `qwen3:0.6b` showed 10s timeout on Dev-PC. 4B requires validation for both quality and latency.

### C. vLLM
- **Pros**: High-throughput inference, production-grade features.
- **Cons**: Primarily Linux-focused, higher overhead for a single-user local app.
- **Suitability**: Low/Medium. Better suited for centralized server setups.

### D. Transformers (Direct)
- **Pros**: No external binary needed (Python only).
- **Cons**: High memory overhead, slower inference without deep optimization (quantization).
- **Suitability**: Low. Not recommended for primary local inference.

## 3. Recommendation
For CCUT 1.0.4, **llama-server** or **Ollama** are the primary candidates. Since Qwen3-ASR already uses a specialized `llama-server.exe`, extending this path to the Narrative LLM provides the most consistent architecture.
