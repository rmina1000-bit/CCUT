# Render QA Rules (V1.0)

렌더링 결과물이 사용자에게 제공되기 전, 물리적/논리적 결함을 검수하기 위한 자동화 규칙입니다.

## 1. 검수 항목 (Checklist)

| 항목 | 검사 내용 | PASS 기준 |
|------|-----------|-----------|
| **말 잘림 (Speech Cut)** | 단어 중간에서 컷이 발생했는지 확인 | 모든 컷 경계가 단어 외부 |
| **소리 튐 (Audio Pop)** | 오디오 파형의 불연속성 검출 | 피크 노이즈 없음 |
| **자막 싱크 (Subtitle Sync)** | 오디오 음성 지점과 자막 표시 시점 일치 여부 | 오차 0.1s 이내 |
| **자막 가림 (Visual Overlay)** | 자막이 다른 시각 요소에 의해 가려지는지 확인 | 레이어 최상단 보장 |
| **무음 구간 (Long Silence)** | 편집 후 너무 긴 침묵(3s 이상)이 잔존하는지 | 없음 |
| **반복 구간 (Duplication)** | 동일한 설명이 중복되어 편집되었는지 | 문맥 중복 없음 |
| **길이 불일치 (Duration)** | 목표 길이와 실제 생성 길 비교 | 오차 ±10% 이내 |
| **화면 튐 (Jump Cut)** | 시각적으로 너무 부자연스러운 연결 구간 탐색 | 시각 엔트로피 변화 임계치 내 |
| **파일 생성 (File IO)** | 최종 mp4 파일이 정상 생성 및 읽기 가능한지 | 재생 가능 |

## 2. 검수 결과 데이터 구조 (JSON)

```json
{
  "simulation_id": "SIM_QA_20260430",
  "source_id": "SRC_001",
  "qa_status": "PASS",
  "score": 0.95,
  "checks": {
    "speech_cut_check": "PASS",
    "audio_pop_check": "PASS",
    "subtitle_sync_check": "PASS",
    "duration_check": "PASS",
    "visual_integrity_check": "WARNING"
  },
  "warnings": [
    "시각적 전환이 다소 빠름 (Jump Cut 가능성)"
  ],
  "fallback_reason": null,
  "timestamp": "2026-04-30T22:00:00Z"
}
```

## 3. 사후 조치 (Post-QA)
- **PASS**: 사용자에게 Preview 표시 및 다운로드 링크 활성화.
- **WARNING**: 결과를 표시하되 사용자에게 "미세한 부자연스러움이 있을 수 있음" 알림 표시.
- **FAIL**: 자동 재보정(Re-snapping) 시도 후 실패 시 사용자에게 리포트 및 수동 수정 요청.
