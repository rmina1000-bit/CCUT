# Narrative Engine Roadmap

## 1. Current Stage

Current implementation is rule-based.

CCUT creates a narrative draft from:
- source count
- duration
- semantic fragment count
- source distribution
- basic quality/risk indicators

## 2. Why This Exists

This stage creates the place where AI reasoning can later be inserted.

The architecture must exist before local LLM or external AI integration.

## 3. Roadmap

### Phase 1 — Rule-based Narrative Draft
- use existing analysis data
- write simple story draft
- ask user for direction
- create StoryIntent

### Phase 2 — StoryIntent to ProposalEngine
- pass StoryIntent to proposal request
- adjust scoring weights
- adjust source coverage
- improve A/B difference

### Phase 3 — Local LLM Narrative Assistant
- use local open-source model for better narrative writing
- keep video data local
- send only text/metadata to model
- no external API required

### Phase 4 — External AI Adapter
- optional paid feature
- send compressed semantic data only
- no raw video/audio/frame transfer by default
- use API for higher-quality story reasoning

### Phase 5 — Memory / User Style
- remember user’s editing preferences
- reuse past StoryIntent patterns
- reduce repeated questions
- improve personalized proposals

## 4. Safety

External AI must not receive raw video by default.

Allowed external payload:
- source IDs
- fragment IDs
- time ranges
- summaries
- scores
- StoryIntent
- user notes

Not allowed by default:
- original video
- raw frames
- raw audio
- full private archive
