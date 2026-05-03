# STEP 10-I.5.28-E8 Proposal Diversity & Source Balance Audit

## 1. 기준
- branch: ccut-1.0.4-step9
- HEAD: 9b01ecd4ab325b0d67969c5eb281b2c2b3ef5aac
- 코드 수정 여부: NO
- 작업 성격: 감사 전용

## 2. 현재 문제
- A/B 제안에 사용된 조각이 많이 겹침
- 특정 영상에 제안 사용 조각이 편중됨
- 일부 영상은 분석 조각이 많아도 제안 사용 조각이 0개
- Market Mode / User Mode가 실제 결과에서 충분히 다르게 보이지 않음

## 3. 감사 결과 요약
- A/B 생성 위치: ccut_backend/engine/proposal_engine.py
- A안 생성 함수: _create_market_proposal
- B안 생성 함수: _create_user_proposal
- A/B scoring 차이: 존재하나 default intent 상태에서는 거의 동일하게 작동
- A/B overlap 제한: 없음
- Source balance 규칙: 없음
- source_usage 성격: 선택 후 통계, 선택 전 제약 아님
- Narrative 영향: 선택 후 설명용, 실제 조각 선택에는 영향 없음

## 4. A/B 유사 원인
SemanticFragmentGenerator에서 market_value와 edit_value가 명시적 사용자 의도 없이 비슷한 기본 가중치로 계산된다.
ProposalEngine은 이 점수 기반으로 전역 ranking 후 greedy selection을 수행한다.
따라서 상위 점수 조각이 A/B 양쪽에 중복 포함될 가능성이 높다.

## 5. Source 편중 원인
ProposalEngine 선택 루프에 source_id 기반 최소/최대 사용 제한이 없다.
긴 영상이나 activity score가 높은 영상에서 생성된 고득점 조각이 전체 proposal pool을 점유한다.
source_usage는 사후 리포트용 통계이며 선택 과정에 제약으로 작동하지 않는다.

## 6. Narrative와 선택의 관계
proposal_story와 proposal_explanation은 선택 완료 후 생성된다.
현재 Narrative는 선택 결과를 설명할 뿐, 조각 선택을 변경하지 않는다.
Narrative Box Phase 2와 연결하려면 StoryPlan이 ProposalEngine에 guide/constraint로 전달되는 별도 단계가 필요하다.

## 7. 최소 수정 후보
- proposal_engine.py 내부에서 B안 생성 시 A안 선택 fragment_id에 overlap penalty 적용
- source별 사용량이 일정 비율을 넘으면 soft penalty 적용
- 멀티 source 프로젝트에서 최소 1개 이상 후보를 우선 고려하되, 저품질 조각 강제 사용은 금지
- source_usage를 사후 통계에서 soft constraint 참고값으로 확장

## 8. 속도 영향
- overlap penalty: LOW
- source counter 기반 soft balance: LOW
- source별 후보 grouping: LOW
- 모든 조각 간 pairwise 비교 O(n²): HIGH, 금지
- 외부 AI 호출/재분석: HIGH, 금지

## 9. 다음 단계 제안
STEP 10-I.5.28-E8-R1 — Lightweight Proposal Diversity Pass

원칙:
- 원본 재분석 없음
- 외부 AI 호출 없음
- DB 변경 없음
- UI 변경 없음
- ProposalEngine 내부 최소수정
- O(n) 또는 O(n log n) 유지
- 강제 균등 배분이 아니라 soft diversity 적용

## 10. 판정
PASS
