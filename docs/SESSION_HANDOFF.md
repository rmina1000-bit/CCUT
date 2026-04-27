# CCUT 1.0.4 v3.2.1 SESSION HANDOFF — STEP 7 → STEP 8

## 현재 기준 흐름
영상 → Proxy/Segment → Evidence Board → Semantic Fragment → User Intent → Proposal(JSON) → ExportInput → Render

## 완료 상태
- STEP 0 기준선 확보: PASS
- STEP 1 Proxy / Segment / Fingerprint: PASS
- STEP 2 Evidence Board: PASS
- STEP 3 Quick Scan + Hypothesis: PASS
- STEP 4 Semantic Fragment: PASS
- STEP 5 User Intent 최종 반영: PASS
- STEP 6 Proposal Engine: PASS
- STEP 7 ExportInput 생성: PASS

## 최신 완료 작업
STEP 7 ExportInput 생성 완료.

Proposal JSON을 Render 입력으로 변환하는 ExportInput 구조가 만들어졌고, clips, total_duration, status=EXPORT_INPUT_READY가 저장된다.

## 확인된 API
- POST /export-input/{proposal_id}
- GET /export-input/{source_id}
- GET /export-input/by-proposal/{proposal_id}

## 다음 작업
STEP 8 Render Engine / Export 실행.

## STEP 8 목적
ExportInput을 기반으로 실제 영상 파일을 생성한다.

## STEP 8 절대 기준
- ExportInput 없이 Render 금지
- Proposal 직접 Render 금지
- Semantic Fragment 직접 Render 금지
- ffmpeg 입력은 ExportInput 기준
- 렌더 결과는 별도 export 파일로 저장
- 원본 파일 훼손 금지

## STEP 8 전 확인
- export_input 저장 구조 확인
- clips 배열의 start/end/duration/order 확인
- source_path 내부 참조 가능 여부 확인
- total_duration 정합성 확인
- 기존 render_engine 자산 확인
