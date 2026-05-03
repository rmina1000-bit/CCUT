# PROPOSAL ENGINE v3.3.0

> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.3.0  

## StoryIntent-Guided Proposal Generation

ProposalEngine should not be understood as the first decision maker after analysis.

The intended order is:

Analysis Data
→ Narrative Draft
→ User Consultation
→ StoryIntent
→ ProposalEngine
→ A/B Proposal

## A/B Role After StoryIntent

A proposal:
- Market / highlight direction
- faster pacing
- stronger opening
- more selective fragments

B proposal:
- user memory / intent direction
- broader source coverage
- more natural flow
- respects StoryIntent more strongly

## Current Limitation

As of E9-R2, StoryIntent is collected in the frontend consultation flow, but full backend ProposalEngine weighting is not yet complete.

Next:
E9-R3 should connect StoryIntent to proposal request or proposal scoring.

## Source Coverage Policy

All sources should not be forced into proposals blindly.  
However, if a source has usable fragments and the user uploaded it intentionally, the system should attempt to include at least one qualified fragment, especially in user-memory mode.

Bad footage should be explained, not silently ignored.
User override always has priority.

---

## Legacy Rules (Reference)
Proposal은 영상이 아니라 Semantic Fragment ID 조합(JSON)이다.
- A: Market Mode, hook/engagement 우선
- B: User Mode, must_keep/촬영 의도 우선
- frontend heuristic 생성 금지
- 영상 로딩 금지
- Semantic 없이 생성 금지
