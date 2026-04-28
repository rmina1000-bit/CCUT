# Common Core v1

## 정의
Evidence Board, Semantic Fragment, Proposal, ExportInput, Render가 공유하는 공통 데이터/계약 계층.

## 목적
각 단계가 직접 결합되지 않고, 공통 계약을 통해 연결되게 한다.

## 포함 범위
- source_id
- evidence_board_id
- semantic_fragment_id
- proposal_id
- export_input_id
- render_result_id
- confidence
- fallback_reason
- status
- created_at / updated_at

## 원칙
- Common Core는 새 엔진이 아니다.
- Common Core는 공통 데이터 계약이다.
- 이번 단계(CCUT 1.0.4)에서는 코드 대규모 수정을 하지 않는다.
