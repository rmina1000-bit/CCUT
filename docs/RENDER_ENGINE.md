# STEP 8 Render Engine / Export 실행 — 초안

## 기준
- D:\CCUT1.0.4
- docs/EXPORT_INPUT.md
- docs/VALIDATION_PROTOCOL.md

## 대상
- ccut_backend/engine/render_engine.py 또는 기존 render_engine
- ccut_backend/main.py
- ccut_backend/archive/db_models.py
- ccut_backend/archive/manager.py
- ccut_backend/ccut_app.db

## 할 일
1. ExportInput 조회
2. clips 순서 확인
3. 각 clip의 source_path/start/end/duration 확인
4. ffmpeg 명령 구성
5. export 파일 생성
6. export 결과 저장
7. export API 추가 또는 기존 API 연결

## 금지
- Proposal에서 직접 Render 금지
- Semantic Fragment에서 직접 Render 금지
- ExportInput 없이 Render 금지
- 원본 파일 수정 금지
- UI 리디자인 금지

## 검증
- ExportInput 기반 렌더 실행
- output mp4 생성
- total_duration 근사 일치
- 원본 훼손 없음
- API 응답 확인
- 브라우저 / Swagger 확인

## 보고
- PASS / 조건부 PASS / FAIL
- 증거: 코드 / DB / API / 생성 파일 / 브라우저
- 남은 문제
- 다음 단계 가능 여부
