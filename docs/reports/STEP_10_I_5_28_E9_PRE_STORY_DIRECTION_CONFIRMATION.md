# STEP 10-I.5.28-E9-PRE Story Direction Confirmation Design

## 1. 기준
- branch: ccut-1.0.4-step9
- HEAD: c5874a3f1b69abc96e872bcf60d29933b77f703b
- 코드 수정 여부: NO
- 작업 성격: 설계 문서화

## 2. 배경
- 현재 CCUT은 영상 분석 직후 사용자의 의도 확인 없이 바로 A/B 편집 제안을 생성함.
- 이는 속도는 빠르지만, 결과물의 논리적 흐름이나 장면 전환의 근거가 사용자 기대와 다를 수 있는 위험이 있음.
- 편집 제안 생성 전, AI가 판단한 "이야기 방향(Story Direction)"을 먼저 제시하고 사용자의 합의를 얻는 단계(Confirmation Gate)를 도입하여 신뢰도를 높이고 결과물의 개인화를 강화함.

## 3. 핵심 원칙
- **선 제안 후 편집**: AI는 바로 편집 시퀀스를 짜지 않고, 먼저 이야기의 뼈대(StoryPlan)를 제안함.
- **비차단형 확인**: 사용자가 응답하지 않아도 기본 StoryPlan으로 제안 생성이 가능해야 하며, 확인 단계가 병목(Bottleneck)이 되지 않도록 설계함.
- **경량 추론**: 외부 AI(LLM) 호출 없이 기존 Semantic Fragment와 메타데이터만 활용하여 O(n) 속도로 방향을 결정함.
- **Snapshot 기반 보정**: 사용자의 수정 요청이 있을 경우, 이를 Snapshot으로 저장하여 즉시 재제안에 반영함.

## 4. 제안 흐름 (Workflow)

1. **분석 단계**: 영상 업로드 및 Semantic Analysis 완료.
2. **Story Direction Preview**: `NarrativeBox`가 분석 데이터를 기반으로 `StoryPlan v0` 생성 및 UI 표시.
3. **사용자 상호작용**: 
   - [이대로 제안]: 즉시 A/B 제안 생성.
   - [방향 수정]: "더 빠르게", "특정 영상 위주로" 등 옵션 선택 또는 텍스트 입력.
   - [무응답]: 일정 시간 경과 또는 사용자가 결과 탭 이동 시 기본값으로 자동 진행.
4. **편집 제안 생성**: 확정된 `StoryPlan`을 가이드라인으로 삼아 `ProposalEngine`이 조각 선택.

## 5. StoryPlan v0 계약 (Draft)

```json
{
  "story_plan_id": "STP_20260503_01",
  "project_id": "proj_abc123",
  "source_ids": ["SRC_A", "SRC_B", "SRC_C"],
  "project_type": "family_vlog",
  "detected_theme": "가족 나들이 기록",
  "default_direction": "user_memory",
  "direction_options": [
    {
      "id": "market_highlight",
      "label": "시장형 하이라이트",
      "description": "강한 장면으로 시작해 빠르게 이어 붙이는 임팩트 중심 방향"
    },
    {
      "id": "user_memory",
      "label": "사용자친화형 기록",
      "description": "여러 영상을 넓게 반영해 하루의 흐름을 자연스럽게 복기하는 방향"
    }
  ],
  "source_roles": {
    "SRC_A": "opening_hook",
    "SRC_B": "main_context",
    "SRC_C": "atmosphere_closing"
  },
  "risk_sources": [
    {
      "source_id": "SRC_K",
      "reason": "의미 조각 부족 (JUNK_SUSPECT)",
      "status": "EXCLUDE_RECOMMENDED"
    }
  ],
  "user_confirmation": {
    "status": "pending",
    "selected_direction": null,
    "adjustment_notes": null
  }
}
```

## 6. NarrativeBox와 ProposalEngine 책임 경계

- **NarrativeBox**: 
  - 분석 데이터 해석 및 프로젝트 성격 추론.
  - `StoryPlan` 생성 및 사용자 확인 UI 인터랙션 담당.
  - 사용자의 방향 지시를 `ProposalEngine`이 이해할 수 있는 가중치/제약 조건으로 변환.
- **ProposalEngine**:
  - 전달받은 `StoryPlan`을 준수하며 실제 조각 시퀀스(Sequence) 생성.
  - Source coverage 및 Duration 최적화.
  - 선택 결과에 대한 기술적 사유(`selection_reasons`) 생성.

## 7. A/B 차별화 기준

- **A안 (Market Mode)**: 
  - `market_highlight` 방향 우선.
  - 고득점(Visual/Audio impact) 조각 위주, 빠른 호흡, 중복 최소화.
- **B안 (User Mode)**: 
  - `user_memory` 방향 우선.
  - 소스 영상의 고른 분포(Coverage), 현장감 유지, 사용자가 명시한 영상 반영.

## 8. 속도 설계 (Performance)
- **추론 속도**: 기존 데이터 캐시를 활용하여 **O(n)** 내에 StoryPlan 생성.
- **병목 방지**: 사용자가 확인 버튼을 누르기 전이라도 백그라운드에서 기본 제안 생성을 미리 시작(Pre-compute)하여 체감 속도 극대화.

## 9. E9-R1 구현 범위 제안
- `StoryPlan` 데이터 구조 및 초기 생성 로직 구현.
- 중앙 패널(`CenterPanel`) 또는 제안 영역 상단에 간단한 방향 확인 카드 UI 추가.
- "이대로 제안" 버튼 클릭 시 기존 Proposal 흐름으로 연결하는 인터페이스 구축.
- 외부 AI 호출이나 복잡한 채팅형 메모리는 이번 단계에서 제외.

## 10. 판정
**PASS**
- 이야기 방향 확인의 목적, 데이터 구조(StoryPlan v0), 사용자 응답 처리 및 시스템 책임 경계가 명확히 설계됨.
