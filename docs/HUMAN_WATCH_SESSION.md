# STEP 19: Human Watch Session System Specification

This document details the system design for tracking real human watch behaviors to optimize editing retention. Rather than relying on simulated attention curves, CCUT logs interactive user playback actions to map genuine attention bottlenecks.

---

## 1. Playback Action Tracking

The system captures micro-events from the frontend video player:
- **Skip (Jump Forward)**: Indicates pacing was too slow, generating a positive penalty for associated editing patterns (e.g., long dialogue gaps).
- **Rewatch (Seek Back)**: Represents high interest or information overload, prompting review of visual complexity weights.
- **Pause**: Suggests high engagement, interruptions, or comprehension buffers.
- **Drop (Early Termination)**: Identifies the exact timestamp and fragment where interest was permanently lost (Drop Point).

---

## 2. Retention Metrics Mapping

Every watch session yields a calculated **Retention Map** representing fragment-level survival rates:
- **Fragment Completion Rate**:
  $$R_f = \frac{\text{Time Spent inside Fragment}}{\text{Fragment Duration}}$$
- **Drop Trigger**: When $R_f < 0.3$, the system registers a negative `boredom_penalty` to the SQLite editing memory patterns active in that fragment.
- **Engagement Trigger**: Repeated rewatches or full completions ($R_f \ge 1.0$) increment the pattern's success rate directly.

```text
[User Playback Event] ──► [Log Event to DB]
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
     (Retention < 30%)                     (Retention >= 100%)
            │                                     │
            ▼                                     ▼
  Boredom Penalty (Failure + 1)         Engagement Boost (Success + 1)
```
