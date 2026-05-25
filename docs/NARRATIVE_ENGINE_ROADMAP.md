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

### Phase 4 — External AI Adapter (확장: 영상 생성 AI 통합)
- 서브타입 A: **Proposal 보강** (기존)
  - 의미 데이터만 외부 AI에 전송
  - 스토리/편집 방향 조언 수신
  - `EXTERNAL_PROPOSAL_SERVICE.md` 참조
- 서브타입 B: **영상 생성 클립 보완** (신규 — 2026-05-26 수립)
  - "부족한 B-roll / 전환 클립" 자동 생성
  - 원본 영상 전송 금지, 스틸 프레임 jpg + 텍스트 프롬프트만 전송
  - Runway Gen-4.5 (1순위) / Kling 3.0 (2순위) API 활용
  - 생성 클립은 일반 소스와 동일하게 CCUT 편집 파이프라인으로 처리
  - 렌더링은 항상 로컬 FFmpeg
  - 사용자 명시적 동의 및 비용 고지 후 실행
  - 상세: `docs/EXTERNAL_AI_VIDEO_API_ROADMAP.md`

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
