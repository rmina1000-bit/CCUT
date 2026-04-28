# Render Engine 기술 스펙 — CCUT 1.0.4

> **역할:** ExportInput → ffmpeg → mp4 생성 계층 SSOT  
> **완료 기준 SHA:** `9bb6faf2be16c4d5d8ea2ef456a06d3853f1aabf`  
> **상태:** STEP 8 PASS ✅

## 1. 목적

ExportInput의 clips 배열을 기반으로 실제 mp4 파일을 생성하고 결과를 저장한다.

```text
ExportInput → RenderEngine → ffmpeg → mp4 → RenderResult 저장
```

## 2. 절대 원칙

- ExportInput 없이 Render 실행 금지
- Proposal / Semantic Fragment에서 직접 Render 금지
- 원본 파일 수정 금지
- API 외부 응답에서 절대경로 노출 금지
- output_url은 `/static/exports/...` 형식 (상대 경로)

## 3. 실행 흐름

```text
POST /render/{export_input_id}
  → ExportInputTable 조회
  → clips 검증 (fragment_id / start / end / duration / order)
  → source_id → sources.file_path 동적 조회
  → clips 정렬 (order 기준)
  → ffmpeg concat/trim 실행
  → output mp4 저장
  → RenderResult DB 저장
  → output_url 반환
```

## 4. clips 처리 규칙

- `order` 기준 오름차순 정렬
- 각 clip: `source_id` → `sources.file_path` 동적 조회 (하드코딩 금지)
- `start` / `end` / `duration` 기준으로 ffmpeg trim
- clip 누락 또는 파일 없으면 `CLIPS_INVALID` 반환

## 5. ffmpeg 구조

```text
ffmpeg -y \
  -ss {start} -to {end} -i {source_path} \
  ... (clip 반복) \
  -filter_complex concat \
  {output_path}
```

- GPU 인코딩 시도 (NVENC → AMF → QSV → CPU x264 fallback)
- 실패 시 `error_msg` 기록, 프로세스 중단하지 않음

## 6. RenderResult Schema

```json
{
  "export_input_id": "EXP_XXXXXX",
  "status": "RENDER_SUCCESS",
  "output_url": "/static/exports/output_XXXXXX.mp4",
  "file_size": 12345678,
  "duration": 30.0,
  "created_at": "2026-04-28T00:00:00Z"
}
```

## 7. API

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/render/{export_input_id}` | Render 실행 |
| `GET` | `/render-result/{export_input_id}` | Render 결과 조회 |

## 8. 에러 상태

| status | 의미 |
|--------|------|
| `RENDER_SUCCESS` | 정상 완료 |
| `CLIPS_EMPTY` | clips 배열 없음 |
| `CLIPS_INVALID` | clip 검증 실패 |
| `RENDER_FAILED` | ffmpeg 실패 |
| `NOT_FOUND` | ExportInput 없음 |

## 9. 완료 증거

상세 검증 보고서: `docs/reports/STEP8_RENDER_ENGINE_REPAIR_REPORT.md`
