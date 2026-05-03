# Pre-Proposal Flow

## 1. Purpose

This document defines what happens before A/B proposal generation.

## 2. Required Order

```text
Analysis Complete
→ Narrative Draft Ready
→ User Consultation Pending
→ StoryIntent Confirmed
→ Proposal Generation Allowed
```

## 3. State Model

```text
analysis_pending
analysis_complete
narrative_draft_ready
consultation_pending
consultation_updated
consultation_confirmed
proposal_ready
```

## 4. UI Rule

Before `consultation_confirmed`:

* A/B proposals must not be displayed
* proposal videos must not be displayed
* export must not be primary
* user should see chat-based narrative consultation

After `consultation_confirmed`:

* A/B proposals can be displayed
* A/B preview/commit can proceed
* export can proceed after commit

## 5. Performance Rule

Proposal precompute may happen internally if it does not affect UX or speed.
However, precomputed proposals should not be exposed to the user before consultation confirmation.

## 6. Failure Rule

If Narrative Draft cannot be generated:

* show a plain fallback explanation
* still ask the user for direction
* do not block the whole pipeline
