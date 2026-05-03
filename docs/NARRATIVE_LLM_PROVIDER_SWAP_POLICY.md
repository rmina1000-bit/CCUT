# Narrative LLM Provider Swap Policy

## 1. Core Goal: Swapability
The primary goal of the R7 design is to ensure that the Narrative LLM provider can be swapped (e.g., from Qwen to Mistral) without modifying the CCUT Core Engine. Qwen3-Instruct is the primary candidate but not a hard dependency.

## 2. Dependency Inversion
CCUT Core does not depend on a specific model or provider. Instead:
- CCUT Core depends on the `NarrativeLLMProvider` interface and the `StoryIntentPatch` contract.
- Providers are "plugged in" behind the AI Boundary.

## 3. What Changes During a Swap
When a provider is swapped, only the following items within the provider adapter should change:
- **Provider Metadata**: ID, name, family, license.
- **Provider Adapter**: The logic that handles the specific API or binary call.
- **Runtime Endpoint**: URL or port for the local inference server.
- **Prompt Template**: Model-specific system prompts (e.g., ChatML for Qwen).
- **License Records**: The legal terms associated with the new model.

## 4. What Remains Constant
The following components must **never** be modified during a provider swap:
- **CCUT Core Engine**: Heuristics and state management.
- **ProposalEngine**: Proposal generation logic.
- **SemanticEngine**: Fragment similarity and value scoring.
- **Render / Export**: Physical output generation.
- **StoryIntentPatch Contract**: The JSON structure returned to the frontend.
- **Decision Log**: The format for recording audit trails.

## 5. Evaluation Criteria for New Providers
To become a candidate for a provider swap, a model must be evaluated on:
- **JSON Schema Compliance**: Ability to strictly follow `StoryIntentPatch` format.
- **Korean Instruction Following**: Proficiency in interpreting Korean narrative requests.
- **Latency**: Speed of local inference (target < 2s for consultation).
- **Local Resource Usage**: Memory and GPU footprint.
- **License Safety**: Commercial use viability (Apache-2.0 preferred).
- **Fallback Reliability**: Compatibility with the rule-based fallback system.
- **Accuracy**: Alignment of the generated patch with the user's intent.
