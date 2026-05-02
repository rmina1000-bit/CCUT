# CCUT Narrative Box

## Purpose
- Story Planning / Narrative / 소설화 계층을 ProposalEngine에서 분리하기 위한 전용 박스.
- Phase 1에서는 계약과 템플릿만 정의.
- 기존 파이프라인에 연결하지 않음.

## Speed Preservation Rule
- 원본 영상 접근 금지
- 새 Whisper/VLM/LLM 호출 금지
- 파일 시스템 스캔 금지
- DB schema 변경 금지
- O(n) JSON 집계만 허용
- proposal 생성 속도 영향 0 유지

## Responsibility Boundary
- Narrative Box: story_plan, source role, storyline option, user feedback, explanation contract
- ProposalEngine: 실제 조각 선택, sequence 생성, target length 조정
- Frontend: 표시와 사용자 피드백 입력만

## Phase Plan
- Phase 1: skeleton + StoryPlan contract only
- Phase 2: narrative_explainer 이관
- Phase 3: StoryPlan shadow mode
- Phase 4: user feedback 반영
- Phase 5: ProposalEngine guide 연결

## Forbidden in Phase 1
- import 연결
- API 추가
- proposal_engine.py 수정
- 런타임 경로 변경
