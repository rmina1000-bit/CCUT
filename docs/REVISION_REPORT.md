# REVISION REPORT — STEP 7 ExportInput

## 변경 요약
STEP 7에서 Proposal JSON을 Render Engine 입력으로 변환하는 ExportInput 계층을 추가했다.

## 신규/수정 범위
- ExportInput 데이터 구조
- ExportInput 생성 로직
- ExportInput 저장 구조
- ExportInput API 3종

## 주요 API
- POST /export-input/{proposal_id}
- GET /export-input/{source_id}
- GET /export-input/by-proposal/{proposal_id}

## 검증 결과
PASS.

## 검증 증거
- Swagger UI endpoint 노출
- export_engine.py 변환 로직 확인
- Browser 200 응답
- Backend Docs 200 응답

## 영향 범위
- Render Engine 전 단계 입력 구조 확보
- Proposal / Semantic Fragment / User Intent 구조 변경 없음
- 실제 ffmpeg 렌더링 없음

## 다음 변경 예정
STEP 8 Render Engine / Export 실행.
