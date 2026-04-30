# Form to Edit Instruction Contract (V1.0)

사용자의 폼 선택값을 CCUT 내부의 기계 판독 가능한 편집 지시서(Edit Instruction)로 변환하는 데이터 계약입니다.

## 1. 입력 스키마 (User Form Input)

```json
{
  "purpose": "product_review",
  "target_duration": "3min",
  "style": "fast_strong",
  "opening": "conclusion_first",
  "reduce": ["silence", "repetition", "ad_like_tone"],
  "preserve": ["actual_demo", "reaction", "final_opinion"],
  "subtitle": "key_subtitles_only",
  "proposal_mode": "ab"
}
```

## 2. 출력 스키마 (Internal Edit Instruction)

```json
{
  "instruction_id": "FORM_INS_001",
  "mode": "free_local",
  "target_output": "youtube_main",
  "target_duration_sec": 180,
  "pace": "fast",
  "hook_strategy": "conclusion_first",
  "reduce_rules": ["long_silence", "repetition", "ad_like_tone"],
  "preserve_rules": ["actual_demo", "reaction", "final_opinion"],
  "subtitle_policy": {
    "type": "key_subtitles_only"
  },
  "analysis_policy": {
    "matrix_mode": "ccut_matrix_light",
    "row_size_sec": 2,
    "worker_slots": 8
  },
  "quality_policy": {
    "word_boundary_snap": true,
    "render_qa": true,
    "audio_pop_guard": true
  }
}
```

## 3. 매핑 규칙 (Mapping Logic)

### 3.1. Matrix 분석 모드 매핑
- `proposal_mode: quick` → `matrix_mode: video_use_speech_only`
- `proposal_mode: ab / standard` → `matrix_mode: ccut_matrix_light`
- `proposal_mode: precision` → `matrix_mode: ccut_matrix_full` (유료/고성능 옵션)

### 3.2. 조각 추천 가중치 (Scoring Weights)
- `preserve` 항목에 해당하는 인지 신호(Column)에 가중치 +2.0 부여.
  - 예: `reaction` 선택 시 `person_signal` 및 `event_signal` 가중치 증가.
- `reduce` 항목에 해당하는 신호에 감점 -5.0 부여.
  - 예: `repetition` 선택 시 유사한 `speech_signal` 구간 중복 배제.

### 3.3. 품질 정책 매핑
- 모든 무료 폼 선택 시 `quality_policy`의 기본 항목(`word_boundary_snap`, `audio_pop_guard`)은 `true`로 고정하여 최소 품질 보장.

## 4. 제안 방식 (Proposal Logic)
- **A/B 안 생성 시**:
  - **안 A**: 사용자의 `preserve` 항목을 최우선으로 반영한 보수적 편집.
  - **안 B**: `style`과 `opening` 전략을 극대화한 파격적 편집.
