# Story Direction Template Registry

## 1. 목적
Story Direction Template Registry는 사용자의 추상적인 편집 의도(Story Direction)를 백엔드 엔진이 이해할 수 있는 구체적인 편집 기준(Editing Criteria)으로 변환하는 **중심 계약(Central Contract)**입니다.

기존의 `ccut_backend/narrative/` 구조가 가진 복잡성을 배제하고, JSON 기반의 경량화된 레지스트리를 통해 Proposal Engine이 즉각적으로 참조할 수 있는 데이터 구조를 제공합니다.

## 2. 핵심 개념

### A. Story Direction (사용자 언어)
사용자가 상담 UI(Narrative Consultation)에서 선택하거나 채팅으로 입력하는 편집의 방향입니다.
- 예: "여러 영상 골고루", "인물 중심으로", "더 빠르게"

### B. Editing Technique Pack (기술 묶음)
템플릿에 연결된 실제 편집 기술들의 리스트입니다. `editing_techniques.json`에 정의된 원자 기술들을 조합하여 템플릿의 성격을 결정합니다.

### C. Production Hard Rules (제작 절대 규칙)
예술적 선택보다 우선하는 기술적/품질적 제약 조건입니다. `production_hard_rules.json`에 정의된 규칙들이 템플릿별로 바인딩되어 안전한 결과물을 보장합니다.

### D. Editing Criteria (엔진 언어)
기술 팩의 가중치와 템플릿의 `soft_scoring`, `hard_constraints`를 의미합니다.

### E. Proposal Template (결과 구조)
최종 A/B 제안의 시퀀스 패턴과 `qa_checks`를 통해 품질이 검증된 결과물입니다.

## 3. 파이프라인 흐름
**사용자 의도** → **템플릿 매칭** → **기술 팩 & 하드 규칙 적용** → **엔진 계산** → **QA 검증** → **최종 제안**


## 3. 레지스트리 구조 (`story_direction_templates.json`)

| 필드 | 설명 |
| :--- | :--- |
| `template_id` | 템플릿 고유 식별자 |
| `display_name` | UI에 표시될 이름 |
| `user_triggers` | 해당 템플릿을 활성화하는 키워드 목록 |
| `story_intent_match` | `StoryIntentPatch`와 매칭될 필드 조건 |
| `hard_constraints` | 반드시 지켜야 할 물리적 제약 (길이, 점수 하한선 등) |
| `soft_scoring` | 제안 생성 시 적용할 가중치 분배 |
| `sequence_pattern` | 추천되는 장면 전개 순서 |
| `qa_checks` | 생성 후 수행할 품질 검사 항목 |

## 4. 운영 정책
- **Lightweight First**: 복잡한 상태 머신 대신 정적 템플릿 조회를 우선합니다.
- **Safe Fallback**: 매칭되는 템플릿이 없거나 분석 결과가 부족할 경우 `safe_default`를 사용합니다.
- **Non-Blocking**: 이 레지스트리 조회는 Fast Path 분석 속도에 영향을 주지 않아야 합니다.

## 5. 관리 위치
- **Config**: `ccut_backend/config/story_direction_templates.json`
- **Reference Code**: `ccut_backend/engine/proposal_engine.py` (도입 예정)

---
**Status**: Initial Contract Established (STEP 10-K-B1)
