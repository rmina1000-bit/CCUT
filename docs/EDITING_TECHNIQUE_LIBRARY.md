# Editing Technique Library

## 1. 개요
Editing Technique Library는 CCUT의 **편집 원자(Editing Atomics)**들의 집합입니다. 각 기술은 특정 신호(Signal)를 입력받아 Proposal Engine의 스코어링이나 컷 생성 로직을 변형시키는 구체적인 알고리즘적 정의를 포함합니다.

사용자는 `Story Direction`을 선택하고, 시스템은 이를 `Editing Technique Pack`으로 번역하여 최종 제안을 생성합니다.

## 2. 기술 분류 (Categories)

| 분류 | 역할 | 대표 기술 |
| :--- | :--- | :--- |
| **Selection** | 어떤 조각을 고를 것인가 | `face_visibility_boost`, `hook_score_priority` |
| **Ordering** | 어떤 순서로 배치할 것인가 | `source_rotation`, `establishing_context_open` |
| **Cutting** | 어디서 자를 것인가 | `sentence_boundary_cut`, `dead_air_removal` |
| **Pacing** | 얼마나 빠르게 전개할 것인가 | `fast_pacing`, `pause_compression` |
| **QA** | 결과가 적절한지 어떻게 검사할 것인가 | `source_diversity_guard`, `factual_integrity_guard` |

## 3. Technique Pack Binding Flow

```mermaid
graph LR
    A[User Intent] --> B[Story Direction Template]
    B --> C[Editing Technique Pack]
    C --> D[Proposal Engine Rules]
    D --> E[A/B Proposals]
```

## 4. 주요 기술 명세 (`editing_techniques.json`)

각 기술은 다음과 같은 메타데이터를 가집니다:
- **`engine_effect`**: 엔진 내부 변수에 가산점(Bonus)이나 감점(Penalty)을 부여하는 수치값.
- **`required_signals`**: 해당 기술을 구현하기 위해 반드시 필요한 분석 데이터 (예: `shot_size`, `emotion_score`).
- **`failure_check`**: 기술 적용 실패 시 발생시킬 경고 또는 QA 항목.

## 5. 운영 정책
- **Technique Reusability**: 하나의 기술은 여러 템플릿에서 공유될 수 있습니다. (예: `duplicate_thumbnail_avoidance`)
- **Signal-Aware**: 분석 데이터(Evidence)가 부족한 경우, 해당 기술은 자동으로 비활성화되거나 Fallback 처리됩니다.

---
**Status**: Library Contract Defined (STEP 10-K-B1-R1)
