# AI Boundary Unification Review

**Baseline SHA**: `72b745319ecf1da19ce6b3c40eecb9fa1010390e`  
**Branch**: `ccut-1.0.4-step9`  
**Scope**: Documentation only. No runtime path changes.

## 1. Existing AI Components

| Component | File or path | Category | Current policy |
|---|---|---|---|
| Qwen3-ASR | `ccut_backend/ai/adapters/qwen3_asr_adapter.py` | ACTIVE_PROVIDER / PASS_THROUGH_PROVIDER | Keep current runtime path unchanged |
| Whisper | `ccut_backend/ai/adapters/whisper_adapter.py` | FALLBACK_PROVIDER | Keep as fallback candidate |
| Narrative rule-based reply | `ccut_frontend/src/hooks/useProposalState.ts` / `buildConsultationReply()` | RULE_BASED_FALLBACK | Reclassify as fallback, not primary intelligence |
| Vision Engine | `ccut_backend/engine/vision_engine.py` | PLACEHOLDER / FUTURE_PROVIDER | Keep as placeholder |
| Vector Engine | `ccut_backend/engine/vector_engine.py` | PLACEHOLDER / FUTURE_PROVIDER | Keep as placeholder |
| Proposal Engine | `ccut_backend/engine/proposal_engine.py` | CORE | Do not move into AI provider layer |
| Semantic Engine | `ccut_backend/engine/semantic_engine.py` | CORE | Do not move into AI provider layer |
| Audio Engine | `ccut_backend/engine/audio_engine.py` | CORE | Keep current delegation path |

## 2. Classification Rules

| Category | Meaning |
|---|---|
| CORE | CCUT-owned core logic, not an external AI provider |
| ACTIVE_PROVIDER | Currently active AI provider |
| PASS_THROUGH_PROVIDER | Existing provider managed by boundary classification but runtime path remains unchanged |
| FUTURE_PROVIDER | Candidate for future integration |
| FALLBACK_PROVIDER | Provider used when a primary provider fails |
| RULE_BASED_FALLBACK | Rule-based fallback logic |
| PLACEHOLDER | Simulation, documentation-only, or incomplete component |

## 3. Existing Adapter vs New Boundary

The existing CCUT AI structure already has an early adapter and registry concept under `ccut_backend/ai/`.  
However, it does not yet define a full AI Boundary policy for all AI-related components.

The new AI Boundary does not replace current runtime paths.  
It creates a common classification layer so that future providers enter through a controlled structure.

## 4. Do Not Touch Area

The following areas must remain unchanged in this step:

- Qwen3-ASR runtime path
- Whisper fallback path
- ProposalEngine
- SemanticEngine
- Render and Export pipeline
- Frontend narrative chat runtime behavior
- `config.yaml`
- Database schema
- Model files and runtime downloads

## 5. Safe Extension Area

The following extensions are allowed as documentation or non-runtime skeletons:

- Provider descriptor definitions
- AI provider inventory definitions
- Narrative LLM future provider classification
- Boundary policy documentation
- AI Staff strategy documentation

No new skeleton file may be imported into existing runtime code during this step.

## 6. Long-Term Migration Candidates

| Candidate | Future role | Current status |
|---|---|---|
| Qwen3-Instruct | Narrative LLM / StoryIntentPatch generation | FUTURE_PROVIDER |
| Qwen-VL | Frame or scene understanding | FUTURE_PROVIDER |
| Qwen-Coder | Code-assist candidate | FUTURE_PROVIDER |
| External AI API | Paid optional enhancer | FUTURE_PROVIDER / PAID_ONLY |

## 7. Why Narrative LLM Must Enter Through the Boundary

Narrative LLM is different from the existing rule-based narrative reply.  
It introduces model latency, model failure risk, output variability, and license or provider policy risk.

Therefore, it must enter only through the AI Boundary.  
The expected output must be a controlled `StoryIntentPatch`, not arbitrary editing decisions.

## 8. Runtime Impact Assessment

This review does not change runtime behavior.

Expected impact:

- Existing ASR continues through the current Qwen3-ASR path.
- Existing proposal generation remains in ProposalEngine.
- Existing semantic generation remains in SemanticEngine.
- Existing render and export behavior remains unchanged.
- New Narrative LLM work must be added only through future boundary-based providers.

## 9. Next Steps

1. Keep the clean provider skeleton committed at SHA `72b745319ecf1da19ce6b3c40eecb9fa1010390e`.
2. Create AI Staff strategy documents.
3. Define the Narrative LLM gateway contract.
4. Add a mock Narrative LLM provider only after documentation is complete.
5. Validate that all future providers are classified before runtime integration.

## 10. Final Statement

Existing AI components are included in the common AI Boundary classification now, but stable runtime paths remain pass-through. New Narrative LLM providers must enter only through the Boundary.
