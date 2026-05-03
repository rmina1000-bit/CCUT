# Ollama Provider Probe Specification

## 1. Overview
The **Ollama Provider Probe** is a diagnostic mechanism used to evaluate if an Ollama instance is available as a Narrative LLM provider for CCUT. This probe is currently decoupled from the main CCUT runtime and acts as a validation step for future integration (R10).

## 2. Probe Logic
The probe follows a non-destructive sequence:
1. **Server Detection**: Pings `http://127.0.0.1:11434/api/tags` to check if the Ollama daemon is active.
2. **Model Inventory**: Lists installed models to see if a suitable candidate (e.g., Qwen3-Instruct) is present.
3. **Connectivity Test**: Performs a single, non-streaming generation call to verify that the selected model responds correctly to a narrative request.

## 3. Status Codes
- `OLLAMA_NOT_RUNNING`: The server was not found or timed out.
- `NO_MODEL_AVAILABLE`: Server is up, but the model list is empty.
- `MODEL_CALL_FAILED`: Server is up and model exists, but inference failed.
- `JSON_PARSE_FAILED`: Inference succeeded, but the response was not valid JSON.
- `PROBE_PASS`: Everything is working as expected.

## 4. Why Use a Probe?
Using a probe allows CCUT to detect the environment without hard-coding a dependency on Ollama. If the probe fails, CCUT remains stable and continues to use the rule-based mock fallback.

## 5. Non-Automation Principle
The probe does **not** automatically download models (`ollama pull`). It only reports the current state and guides the user on what is missing.
