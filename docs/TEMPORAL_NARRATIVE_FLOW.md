# STEP 18: Temporal Narrative Flow Learning System Specification

This document outlines the system architecture for **Sequence-level learning** in CCUT, advancing from isolated clip heuristics to learning temporal pacing and rhythm transitions (Hook → Setup → Tension → Pause → Payoff → Rehook).

---

## 1. Sequence Pacing & Flow Segments

Rather than looking at a single clip, CCUT models editing flow as a structured transition graph of temporal states:

1. **Hook**: Rapid action/audio trigger within the first 3 seconds to secure viewer attention.
2. **Setup**: Mid-tempo scenic or dialogue clips providing contextual reality.
3. **Tension**: Fast-paced cutting sequence where durations decrease sequentially.
4. **Pause**: A silent gap or static scenery clip to build anticipation.
5. **Payoff**: Peak emotional or auditory reaction clip.
6. **Rehook**: Quick transition back into a high-density scene to combat user retention drop-offs.

---

## 2. Sequence-Level Transition Learning

The `TemporalFlowMemoryTable` stores flow templates and tracks their success/failure counts:
- **Transition Quality**: Evaluated by looking at the continuity of visual motion scores and audio energy shifts.
- **Flow Reranking**: Sequences matching high-acceptance templates (e.g., `Hook → Setup → Tension → Payoff`) receive a sequence rhythm multiplier.
- **Addiction Modeling**: Penalizes sequences that fail to deliver a Payoff within a reasonable duration, preventing cognitive fatigue.

```text
[Generated Sequence] ──► [Flow Template Mapping] ──► [Transition Evaluation]
                                                              │
                                      ┌───────────────────────┴───────────────────────┐
                                      ▼                                               ▼
                              (Pattern Valid)                                 (Pattern Invalid)
                                      │                                               │
                                      ▼                                               ▼
                              Flow Success + 1                                Flow Failure + 1
                             (Flow Multiplier Up)                           (Flow Multiplier Down)
```
