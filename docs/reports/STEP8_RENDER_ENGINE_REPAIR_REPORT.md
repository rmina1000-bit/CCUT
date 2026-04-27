# STEP 8 Render Engine Repair Report

작성: 2026-04-27
정정: Codex

## 목적

STEP 8 Render Engine / Export 검수에서 FAIL로 판정된 항목 4개를 보완한다.

## 보완 항목

1. `ccut_backend/engine/render_engine.py` 내부 절대경로 하드코딩 제거
2. `SRC_3BD89C3B` 실제 source 경로를 DB 기준으로 정정
3. `GET /render-result/{export_input_id}` 응답에서 `output_path_internal` 제거
4. 루트/백엔드에 남은 임시 untracked 파일 정리

## 실제 source 경로 정정

- `source_id`: `SRC_3BD89C3B`
- DB 기준 `file_path`: `D:\CCUT1.0.4\ccut_backend\storage\uploads\20130512_143229.mp4`

## 보완 결과

- Render Engine은 `Path(__file__).resolve().parents[1]` 기준으로 backend 루트를 계산한다.
- Render 결과는 DB에 `output_path_internal`을 저장하되, API 응답에는 노출하지 않는다.
- Render 구조는 `ExportInput -> clips -> render -> export_results -> API -> static output`을 유지한다.
- 임시 검증 파일은 정리한다.

## 재검증 기준

- `render_engine.py`에서 `D:/CCUT1.0.4` 또는 `D:\CCUT1.0.4` 검색 결과 없음
- `GET /render-result/{export_input_id}` 응답에 `output_path_internal` 없음
- `sources.file_path`는 위 DB 값과 일치
