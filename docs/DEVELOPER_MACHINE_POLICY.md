# Developer Machine Policy (Dev-PC Policy)

## 1. Definition
The Developer Machine (Dev-PC) refers to the environment used by the CCUT development team (including the "Director's PC").

## 2. Role and Limitations
- **Verification, Not Validation**: The Dev-PC is used to verify that the code *works* (contracts are met, JSON is valid, logic flows). It is NOT used to validate if a model is "too slow" for the final product.
- **Heterogeneous Specs**: Dev-PCs may vary in specs. Code must be robust enough to run on mid-tier hardware for testing purposes.
- **Mock-First Development**: When Dev-PC resources are constrained, developers should use the **Mock Narrative LLM Adapter** (R6) to test system flow without launching heavy weights.

## 3. Rejection Guard
A model candidate (e.g., Qwen3-Instruct 7B) cannot be rejected solely because it runs slowly on a Dev-PC. Rejection must be based on performance data from the **High-End Laptop Profile**.

## 4. Environment Probe
Developers should periodically run `tools/inspect_local_ai_environment.py` to ensure their local environment meets the minimum functional requirements for the current development phase.
