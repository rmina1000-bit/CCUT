# Narrative LLM Model Baseline

## 1. Baseline Definitions

| Model | Role | Status | Notes |
|-------|------|--------|-------|
| **qwen3:4b** | **Validation Baseline** | **Current Target** | Primary candidate for R10-C/D verification. |
| **qwen3:8b** | Product Candidate | High-End | Target for premium creator laptops. |
| **qwen3:0.6b** | Experimental | Tested | Low-resource candidate; baseline probe showed timeout. |
| **qwen2:latest** | Legacy | Test-only | Used for initial connection tests only. |
| **Qwen3-ASR** | Specialized | ASR-only | Not used for Narrative Chat. |

## 2. Core Principle: Model Independence
CCUT is architected to depend on the **StoryIntentPatch contract**, not specific model IDs. The baseline models listed above are selected for initial benchmarking and can be swapped via the `narrative_provider_registry.py` without code changes.

## 3. Evaluation Cycle
1. **Mock**: Verify system flow with the rule-based mock.
2. **Baseline (4B)**: Verify local LLM feasibility and quality.
3. **Product (8B)**: Final validation for high-end hardware profiles.
