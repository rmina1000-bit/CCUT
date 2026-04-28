# ExportInput 기술 스펙 — CCUT 1.0.4

> **역할:** Proposal JSON → Render Engine 입력 변환 계층 SSOT  
> **완료 기준 SHA:** `9bb6faf2be16c4d5d8ea2ef456a06d3853f1aabf`  
> **상태:** STEP 7 PASS ✅

## 1. 목적

Proposal(JSON)을 실제 Render Engine이 처리할 수 있는 정규화된 입력 구조(ExportInput)로 변환한다.

```text
Proposal(JSON) → ExportInput → Render Engine → mp4
```

## 2. 절대 원칙

- Proposal 없이 ExportInput 생성 금지
- ExportInput 없이 Render 실행 금지
- API 외부 응답에서 절대경로 노출 금지
- 원본 영상 파일 수정 금지

## 3. 데이터 구조

### ExportInput Schema

```json
{
  "export_id": "EXP_XXXXXX_SRC_YYYYYYYY",
  "source_id": "SRC_YYYYYYYY",
  "proposal_id": "PROP_ZZZZZZ",
  "mode": "A",
  "clips": [
    {
      "fragment_id": "SF1_SRC_YYYYYYYY",
      "source_id": "SRC_YYYYYYYY",
      "start": 0.0,
      "end": 30.0,
      "duration": 30.0,
      "order": 0
    }
  ],
  "total_duration": 30.0,
  "status": "EXPORT_INPUT_READY"
}
```

## 4. 생성 로직

1. `proposal_id`로 Proposal 조회
2. Proposal `sequence` 배열 순회
3. 각 Semantic Fragment → clip 항목 생성 (`fragment_id`, `start`, `end`, `duration`, `order`)
4. clips 합산 → `total_duration`
5. DB 저장 (`ExportInputTable`)

## 5. API

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/export-input/{proposal_id}` | Proposal 기반 ExportInput 생성 |
| `GET` | `/export-input/{source_id}` | 소스별 ExportInput 목록 조회 |
| `GET` | `/export-input/by-proposal/{proposal_id}` | 제안별 ExportInput 조회 |

## 6. 보안 규칙

- API 응답에 로컬 절대경로 포함 금지
- `source_path` 등 파일시스템 경로는 내부 조회 전용
- 외부 응답은 `source_id` / `fragment_id` 기준

## 7. 완료 증거

상세 검증 보고서: `docs/reports/STEP7_EXPORT_INPUT_REPORT.md`
