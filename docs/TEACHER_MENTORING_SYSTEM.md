# Teacher-Student Mentoring System Specification

This document details the cooperative learning pipeline where the advanced AI (Teacher) guides, evaluates, and corrects the lightweight CCUT local heuristic scoring engine (Student).

---

## 1. Capability Gap & Philosophy

Lightweight local systems (Student) operate on limited CPU resources using simple linear heuristics, but lack the high-level semantic, cultural, and storytelling intuition of large models (Teacher). 

Instead of deploying a massive neural network locally, CCUT pairs them:
- **Student**: Generates editing proposal structures and identifies uncertainty.
- **Teacher**: Evaluates the proposals semantically via metadata analysis, providing coaching critiques and structural weights corrections to the Student.

---

## 2. Mentorship Workflow

```text
[Proposal Generation]
       │
[Uncertainty Check (Active Learning Selector)]
       │
       ├─► (Entropy Low)  ──► Use Student's Reranking
       │
       └─► (Entropy High) ──► Trigger Teacher Mentorship
                                     │
                             [Teacher Evaluator]
                                     ├─► Dynamic Weak Label injection
                                     └─► Memory Weight Coaching Deltas
```

1. **Uncertainty Trigger**: Triggered when BPR rerank scores for Proposal A and B differ by $\le 0.04$ (Active Learning Selector threshold).
2. **Mentoring Evaluation**: The Student passes proposal sequences and metrics metadata to the Teacher.
3. **Weak Label Injection**: The Teacher writes specialized coaching weak labels (`reaction_hold_good`, `audio_cut_bad`) into the SQLite database.
4. **Weight Coaching**: The Teacher applies a coaching delta ($+0.05$ to success counts or updates acceptance rate) to correct simple heuristics.

---

## 3. Privacy Shield Policies
- **Metadata-Only**: Only metadata structures (structural roles, timings, view/acceptance counts) are analyzed by the Teacher.
- **No Private Data**: Subprocess video paths, audio waveforms, or direct user data are strictly excluded.
