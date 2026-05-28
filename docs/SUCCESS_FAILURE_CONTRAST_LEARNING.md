# STEP 17: Success-Failure Contrast Learning System Specification

This document details the reverse editing analysis and success-failure contrastive learning pipeline for CCUT. Rather than cloning top-performing video structures blindly, CCUT contrasts high-performing videos with low-performing videos in the same genre to discover retention-killing patterns.

---

## 1. Reverse Editing Analysis

Since raw video files only show the finalized product, CCUT performs **Reverse Editing Analysis** on metadata sequences extracted via AI:
- **Hook Density**: The concentration of high-motion, high-volume clips in the first 8 seconds.
- **Speech Tempo**: Ratio of syllables/words per second inside speech clips.
- **Reaction Spacing**: The intervals between main narration/action clips and reaction clips.
- **Silence Gap Distribution**: The percentage and spacing of silent buffers.
- **Scene Rhythm**: The average duration of cuts across structural roles.

---

## 2. Contrastive Feedback Mechanism

By comparing high-retention (Success) and low-retention (Failure) videos of similar search queries:
- **Success Patterns**: High-retention structures increase the `success_count` of editing patterns (e.g., tight `reaction_hold`).
- **Failure Patterns**: Low-retention structures increment the `failure_count` of associated editing patterns (e.g., long `boredom_prevent` failures), applying a direct penalty.

```text
       [Compare High vs Low Retention Videos]
                        │
       ┌────────────────┴────────────────┐
       ▼                                 ▼
[Success Video Patterns]          [Failure Video Patterns]
       │                                 │
       ▼                                 ▼
   Success + 1                       Failure + 1
   (Positive Boost)                  (Negative Penalty)
```

---

## 3. Human Watch Simulation Schema

To model real human behavior (skipping, drop-offs, visual fatigue), the learning system tracks simulated Retention Curves:
- **Retention Drop Point**: Triggered when a sequence clip exhibits a `boredom_risk` label alongside low audio energy.
- **Skip Probability**: Modeled based on user attention span drifts, updating acceptance thresholds dynamically.
