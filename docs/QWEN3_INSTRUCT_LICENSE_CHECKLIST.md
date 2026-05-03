# Qwen3-Instruct License Checklist

Before downloading or registering a Qwen3-Instruct model, the following verification steps must be performed by a human reviewer.

## 1. Source Verification
- [ ] **Original Repository**: Verify the LICENSE file at the official Alibaba-Qwen HuggingFace or GitHub repository.
- [ ] **GGUF Source**: If using a quantized GGUF version (e.g., from Bartowski or MaziyarPanahi), confirm that the conversion has not introduced additional restrictive terms.

## 2. Terms Review
- [ ] **Apache-2.0 Confirmation**: Confirm the model is released under the Apache-2.0 license.
- [ ] **Commercial Use**: Verify there are no revenue-based or user-count-based commercial restrictions (common in Llama/Gemma).
- [ ] **Redistribution**: Check if the license allows bundling the model or providing it via a local registry.
- [ ] **Attribution**: Note the required attribution format for the `About` or `Licenses` section of CCUT.

## 3. Metadata Recording
The following information must be recorded in the `provider_registry` or documentation:
- **Model Name/Version**: (e.g., Qwen3-7B-Instruct)
- **Quantization Level**: (e.g., Q4_K_M)
- **Source URL**: (Link to HuggingFace/GitHub)
- **Reviewer Signature**: (Human approval name/date)

## 4. Policy Reminder
> **"Actual model LICENSE must be checked at the selected model repository before any production use."**
