# EXECUTION PLAN v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## STEP 0. 기준선 확보
목적: 1.0.3 복사 코드의 오염과 legacy를 목록화한다.
- git status / build / backend run 확인
- `CCUT_1.0.3` 경로 전체 검색
- mock/demo/random/legacy 목록화
- 삭제 금지, 격리 계획만 작성

## STEP 1. Proxy + Segment Partitioning
- 분석용 proxy 생성
- segment 10~30초 단위 분할
- overlap 0.5초
- fingerprint 생성

## STEP 2. Evidence Board
- Worker 결과를 buffer에 수집
- 1초 또는 10 segment 단위 batch flush
- field-level merge
- coverage 100% 검증

## STEP 3. Quick Scan + Hypothesis
- 대표 이미지 3~7개
- 짧은 영상 요약
- AI 가설 생성: 영상 성격 / 핵심 / 편집 방향
- 사용자 미응답 시 default intent로 계속 진행

## STEP 4. Semantic Fragment
- Evidence 30% 이상 + transcript 10% 이상 확보 시 partial 생성
- semantic / structural / continuity 3계층 생성
- merge/split 적용
- confidence/fallback_reason 기록

## STEP 5. User Intent 최종 반영
- must_keep / avoid / tone / target_length 반영
- edit_value 재계산
- Proposal 전 re-score 완료

## STEP 6. Proposal Engine
- backend semantic 기반 A/B 생성
- A: Market Mode
- B: User Mode
- proposal_reason / confidence / fallback_reason 포함
- frontend heuristic 생성 금지

## STEP 7. ExportInput + Export
- Proposal → ExportInput 변환
- render_engine 재사용
- 최종 렌더 1회

## STEP 8. Local Resource Orchestration
구조 완성 후 Resource Governor 기반 최적화 적용.

## STEP 9. UI 최소연동
UI 리디자인 금지. API 응답 확인용 최소 표시만 허용.

## STEP 10. 검증 및 안정화
E2E: upload → evidence → semantic → proposal → export PASS.
