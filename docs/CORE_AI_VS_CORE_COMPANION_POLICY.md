# Core AI vs Core Companion Policy

## 1. Comparison of Integration Models

| Feature | Direct Core Embedding | Boundary-Based Core Companion |
|---------|-----------------------|--------------------------------|
| **Coupling** | High (Hard-coded logic) | Low (Interface-driven) |
| **Risk** | High (AI failure breaks Core) | Low (AI failure triggers fallback) |
| **Flexibility** | Low (Difficult to swap) | High (Easy to swap providers) |
| **Asset Ownership** | Blurred | Clear (Core owns data/logic) |

## 2. Policy Conclusion
1. **No Direct 결합**: Specific LLMs or AI providers shall not be directly integrated into the CCUT Core Engine.
2. **AI as Advisor**: AI Staff serve as advisors for `StoryIntentPatch`, QA, and semantic interpretation.
3. **Core Ownership**: `ProposalEngine`, `SemanticEngine`, and `Render` are maintained as immutable CCUT Core components.
4. **Resilience**: In case of AI failure, CCUT must remain operational via rule-based fallbacks.

## 3. Guiding Principle
> **"AI may advise, but CCUT Core owns decisions, evidence, and execution."**
