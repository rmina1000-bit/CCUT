# Poor-Man Learning System (PMLS) Architecture Specification

This document details the design specifications of the low-cost learning loop developed for CCUT. PMLS operates on local CPU resources using SQLite-backed heuristic scoring to constantly improve proposal editing quality.

---

## 1. System Topology

```text
User Action (Choice / PBE Edit)
→ Decision Logger
→ SQLite ccut_app.db (Decisions, Preference Pairs, Weak Labels)
→ Pattern Memory Heuristics
→ Proposal Ranker (Reranker)
```

1. **User Choice Logger**: Intercepts proposal acceptances and manual tweaks.
2. **Weak Supervision Generator**: Snorkel-style rule labeling to extract noisy labels from audio energy, motion values, and visibility drifts.
3. **Pattern Memory Repository**: Increments success/failure counters and tracks average user acceptance scores per editing template.
4. **Post-Proposal Reranker**: Performs score adjustments using the pattern weights to change option layouts dynamically.

---

## 2. Preference Ranking Model (CPU-Only BPR Heuristics)

Rather than executing heavy backpropagation on deep transformer neural networks, CCUT implements a **Bayesian Personalized Ranking (BPR)** surrogate that computes a linear score mutation:

$$\text{RerankedScore} = \text{BaseHRS} \times \omega_{\text{pattern}} \times \omega_{\text{weak\_labels}} \times \omega_{\text{boundary}}$$

* $\omega_{\text{pattern}}$: Fetches a positive boost ($1.15$) if the user has accepted reaction/scenery clips of this template type $>65\%$ of the time.
* $\omega_{\text{weak\_labels}}$: Rewards fragments containing positive weak tags (`hook_candidate`, `reaction_hold_good`) and penalizes fragments containing noise tags (`boredom_risk`, `cognitive_overload_risk`).
* $\omega_{\text{boundary}}$: Rewards proposals matching historical PBE corrections ($\Delta_{\text{left}}$ or $\Delta_{\text{right}}$) and applies a slight penalty if the proposal falls back to unadjusted boundaries.
