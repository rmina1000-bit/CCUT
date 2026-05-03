# Qwen Path Hygiene Review

## 1. Problem Statement
The current CCUT 1.0.4 environment suffers from "path pollution" where the active configuration refers to a legacy directory (D:\CCUT_1.0.3) for critical AI runtime components.

## 2. Path Audit Findings

### A. Config Pollution (config.yaml)
The `qwen3_asr` provider configuration in CCUT 1.0.4's `ccut_backend/ai/config.yaml` points to the following legacy paths:
- `server_binary`: `D:/CCUT_1.0.3/tools/llama.cpp-vulkan/llama-server.exe`
- `model_path`: `D:/CCUT_1.0.3/ccut_backend/ai_models/qwen3-asr-1.7b/Qwen3-ASR-1.7B-Q8_0.gguf`
- `mmproj_path`: `D:/CCUT_1.0.3/ccut_backend/ai_models/qwen3-asr-1.7b/mmproj-Qwen3-ASR-1.7B-Q8_0.gguf`

### B. Duplicate Models
Qwen3-ASR models (0.6B and 1.7B) are duplicated in:
- `D:\CCUT1.0.4\ccut_backend\ai_models`
- `D:\CCUT_1.0.3\ccut_backend\ai_models`

### C. Resource Conflict
Relying on the 1.0.3 `llama-server.exe` while developing in 1.0.4 creates a hard dependency on the presence of the legacy folder, which may lead to "File Not Found" errors if the legacy folder is deleted or moved.

## 3. Hygiene Policy
- **Legacy Reference**: All references to `D:/CCUT_1.0.3` are classified as **Legacy Debt/Inheritance Path**.
- **Consolidation Rule**: CCUT 1.0.4 should ideally use its own `tools/` and `ai_models/` directories.
- **Action Strategy**: In the current step (R10-A), we acknowledge and document these paths. Actual correction (pointing to 1.0.4 local paths) will be performed in a separate cleanup phase to avoid breaking the current stable ASR runtime during the Narrative LLM transition.

## 4. Current Risk Level: LOW
The system works as long as `D:\CCUT_1.0.3` exists. However, the path hygiene is poor and needs resolution before final delivery.
