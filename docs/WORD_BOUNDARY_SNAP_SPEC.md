# Word Boundary Snap Specification (V1.0)

AI 추천이나 사용자 드래그로 설정된 컷 경계를 실제 언어적/청각적 경계로 정밀하게 보정하는 기술 규격입니다.

## 1. 목적
조각(Fragment)의 시작과 끝이 단어 중간에서 잘리는 "음절 잘림" 현상을 방지하고, 침묵(Silence) 구간을 이용해 자연스러운 호흡을 확보합니다.

## 2. 입출력 정의 (Interface)

### 2.1. 입력 데이터 (Input)
- `clip_start_sec`: 요청된 시작 지점.
- `clip_end_sec`: 요청된 종료 지점.
- `transcript`: 해당 구간의 텍스트 데이터.
- `word_timestamps`: 단어별 시작/종료 시간 리스트.
- `silence_ranges`: 분석된 무음 구간 리스트.
- `must_keep_ranges`: 사용자가 절대 자르지 말라고 지정한 구간.
- `avoid_ranges`: 편집에 포함하지 말아야 할 구간(NG 등).

### 2.2. 출력 데이터 (Output)
- `snapped_start_sec`: 보정된 시작 지점.
- `snapped_end_sec`: 보정된 종료 지점.
- `snap_reason`: 보정 근거 (예: `SILENCE_SNAP`, `WORD_START_SNAP`).
- `confidence`: 보정 신뢰도 (0.0 ~ 1.0).
- `fallback_reason`: 보정 실패 시 이유.

## 3. 보정 규칙 (Priority Rules)

1. **말 중간 절단 금지**: 단어 타임스탬프 내부에 컷이 걸릴 경우, 무조건 해당 단어의 시작 이전이나 끝 이후로 경계를 밀어냄.
2. **침묵 구간 우선 (Silence-first)**: 컷 경계 0.5s 이내에 침묵 구간이 있다면 해당 침묵의 중앙 또는 끝으로 스냅.
3. **문장 끝 우선 (Sentence-end)**: 마침표(.)나 물음표(?) 등으로 끝나는 문장 경계에 가중치를 부여.
4. **Must-keep 보존**: 스냅 결과가 `must_keep_ranges`를 침범하면 스냅을 취소하거나 구간을 확장함.
5. **길이 제한 준수**: 보정 후의 길이가 원래 요청된 길이보다 20% 이상 차이 날 경우 경고 또는 폴백 적용.

## 4. 알고리즘 흐름
1. 요청 지점 주변 1초 내의 모든 `word_timestamps` 검색.
2. 각 단어 사이의 간격(Gap) 점수화 (간격이 클수록 고득점).
3. `silence_ranges`와 중첩되는 간격에 가중치 합산.
4. 가장 높은 점수의 지점으로 `snapped_time` 결정.
5. `must_keep` 체크 후 최종 확정.
