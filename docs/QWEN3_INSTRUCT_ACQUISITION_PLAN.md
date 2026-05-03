# Qwen3-Instruct Acquisition Plan

## 1. Context
Currently, CCUT possesses Qwen3-ASR models (0.6B and 1.7B) for transcription tasks. However, the **Narrative Consultation** feature requires a conversational model capable of structured reasoning, specifically **Qwen3-Instruct**. This model is currently missing from local storage.

## 2. Acquisition Strategy
Qwen3-Instruct is classified as an **AI Staff Provider**, not a core dependency. Its acquisition must follow a controlled process:
- **Manual Acquisition**: Models are NOT automatically downloaded by the CCUT backend.
- **User Approval**: Installation occurs only after explicit user approval via a manual command or setup wizard.
- **Candidate Variants**:
  - **Qwen3 0.6B/1.7B**: Experimental low-resource candidates. (0.6B tested; baseline probe timeout recorded).
  - **Qwen3 4B-Instruct**: **Primary Validation Baseline** for R10-C.
  - **Qwen3 8B-Instruct**: Target candidate for high-end creator laptops (RTX 4090/5090).

## 3. Deployment Runtimes
- **Primary**: **Ollama** (via `ollama pull` or custom `Modelfile` registration).
- **Secondary**: **llama-server** (via GGUF files stored in `ccut_backend/ai_models/narrative/`).

## 4. Storage Policy
- Models acquired via Ollama reside in the standard Ollama registry.
- Models acquired for llama-server are stored in `D:\CCUT1.0.4\ccut_backend\ai_models\narrative\`.
- ASR and Instruct models must be kept in distinct directories to prevent runtime configuration errors.

## 5. Rollback & Fallback
If Qwen3-Instruct acquisition fails or the model underperforms, the system defaults to:
1. **Mock Narrative LLM Adapter** (R6) for development.
2. **Rule-Based Fallback** (Frontend `buildConsultationReply`) for production stability.
