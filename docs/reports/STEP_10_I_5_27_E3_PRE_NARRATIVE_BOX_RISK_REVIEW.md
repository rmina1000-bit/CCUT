# STEP 10-I.5.27-E3-PRE Narrative Box Risk Review

## 1. 기준
- branch: `ccut-1.0.4-step9`
- HEAD: `60a4e27627eff242ea9c12b39049bc81b188d386`
- git status: `Clean before creation, 1 new report file pending commit`
- 코드 수정 여부: 없음

## 2. 현재 코드베이스 역할 분포

| 역할 | 현재 위치 | 이상적 위치 | 위험도 | 조치 |
|:---|:---|:---|:---|:---|
| 조각 선택 | `ProposalEngine` (Backend) | `ProposalEngine` | 낮음 | 유지 (Algorithm Core) |
| proposal 생성 | `ProposalEngine` (Backend) | `ProposalEngine` | 낮음 | 유지 (Orchestration) |
| story 생성 | `ProposalEngine._generate_story` | `NarrativeBox` | **중간** | 이관 필요 (Text logic) |
| explanation 생성 | `ProposalEngine._generate_explanation` | `NarrativeBox` | **중간** | 이관 필요 (Reasoning) |
| source role 판단 | `SemanticFragmentGenerator` | `SemanticEngine` | 낮음 | 유지 (Data Source) |
| user direction 관리 | `useProposalState.ts` (Frontend) | `NarrativeBox` (Context) | **높음** | 백엔드 동기화 필요 |
| reproposal 관리 | `useProposalState.ts` (Frontend) | `NarrativeBox` | **높음** | 백엔드 API 신설 필요 |
| UI 표시 | `CenterPanel.tsx` | `CenterPanel.tsx` | 낮음 | 유지 (Display Only) |
| export clip 생성 | `ExportEngine` (Backend) | `ExportEngine` | 낮음 | 유지 (Physical Render) |

## 3. Narrative Box 필요성
현재 `ProposalEngine`은 "조각을 고르는 일"과 "고른 이유를 설명하는 일"을 동시에 수행하고 있습니다. 이로 인해 편집 의도가 복잡해질수록 엔진 코드가 비대해지고 있으며, 사용자의 주관적 피드백(Reproposal)을 반영하기 위한 유연한 문맥 관리가 어렵습니다. `Narrative Box`는 편집의 '의도'와 '이야기'를 별도의 객체(`StoryPlan`)로 관리하여 엔진의 부담을 줄이고 지능적인 편집 피드백 루프를 제공하기 위해 필요합니다.

## 4. Narrative Box 도입 위험
- **속도 저하**: 텍스트 분석 및 스토리 구성 로직이 무거워질 경우 분석 속도에 악영향.
- **정합성 붕괴**: `NarrativeBox`가 짠 스토리라인(`StoryPlan`)을 `ProposalEngine`이 제대로 구현하지 못할 경우(조각 부족 등) 사용자에게 거짓 정보를 제공할 위험.
- **API 호환성**: 현재 프론트엔드가 의존하고 있는 `proposal_story` 및 `proposal_explanation` 필드 구조가 변경될 때 UI가 깨질 위험.

## 5. 책임 경계 제안
- **Narrative Box**: "무엇을 말할 것인가" (What to say) 결정. 스토리 요약, 전개 과정 설계, 품질 경고 판단.
- **Proposal Engine**: "어떻게 보여줄 것인가" (How to show) 결정. 실제 조각 매칭, 브릿지 삽입, 타겟 길이 준수.
- **Narrative Box는 절대 원본 영상이나 파일 시스템에 직접 접근하지 않으며, 오직 `SemanticEngine`이 제공하는 메모리 내 조각 데이터만 사용합니다.**

## 6. StoryPlan JSON 계약안 (v0)
```json
{
  "story_plan_id": "STP_001",
  "project_id": "PRJ_123",
  "source_ids": ["SRC_A", "SRC_B"],
  "project_summary": "이 프로젝트는... (자동 생성)",
  "source_roles": { "SRC_A": "Main Story", "SRC_B": "Atmosphere" },
  "candidate_fragments": ["SF_01", "SF_05", "SF_10"],
  "storyline_options": ["Chronological", "Emotional Arc"],
  "selected_storyline": "Chronological",
  "user_feedback": "좀 더 빠르게 전개해줘",
  "final_storyline": [
    { "step": 1, "intent": "Opening", "desc": "가장 강렬한 장면으로 시작" }
  ],
  "proposal_constraints": { "min_duration": 30, "max_duration": 60 },
  "quality_warnings": ["저조도 장면 포함 주의"],
  "trace": "System -> Analysis -> Narrative Plan created"
}
```

## 7. 기존 proposal_story/proposal_explanation과 관계
- `NarrativeBox`는 `StoryPlan`을 기반으로 기존의 `proposal_story`와 `proposal_explanation` 객체를 생성하여 반환합니다.
- 즉, 프론트엔드는 데이터의 원천이 `ProposalEngine`에서 `NarrativeBox`로 바뀌었음을 인지하지 못하도록 하위 호환성을 유지합니다.

## 8. directionSnapshot / user intent와 관계
- 프론트엔드의 `directionSnapshot`은 `NarrativeBox`의 `user_feedback` 및 `proposal_constraints` 필드로 매핑되어 입력됩니다.
- 이는 백엔드에서 `StoryPlan`을 갱신하는 트리거가 됩니다.

## 9. export / resolver와의 관계
- `NarrativeBox`는 `ExportEngine`에 영향을 주지 않습니다.
- 오직 `ProposalEngine`이 확정한 조각 시퀀스만이 `ExportEngine`으로 전달됩니다.

## 10. 속도 영향 분석
- **LOW**: 이미 메모리에 로드된 `semantic_fragments`를 `O(n)`으로 순회하며 텍스트를 조합하는 경우. (현재 목표)
- **MEDIUM**: 조각 간의 관계를 심층 분석하기 위해 중첩 루프(`O(n^2)`)가 빈번하게 발생하는 경우.
- **HIGH**: 외부 AI API(LLM 등)를 동기적으로 호출하거나, 원본 영상의 메타데이터를 다시 읽기 위해 파일 시스템 I/O가 발생하는 경우. (절대 금지)

## 11. Migration 단계 제안
- **Phase 0**: 본 문서(Risk Review) 확정.
- **Phase 1**: `ccut_backend/narrative/` skeleton 및 `StoryPlan` contract 생성. (`proposal_engine.py` 리팩토링은 Phase 2 이후로 보류)
- **Phase 2**: `proposal_engine.py` 내의 `_generate_explanation` 함수를 `narrative/`로 이동. (Refactoring only)
- **Phase 3**: `StoryPlan` 객체 도입 및 `ProposalEngine`과 연결 (Shadow Mode - UI 반영 안 함).
- **Phase 4**: 사용자 피드백(`Reproposal`)을 `StoryPlan` 갱신에 반영하는 API 신설.
- **Phase 5**: `StoryPlan`이 실제 조각 선택 과정에 가중치를 주는 수준으로 심화.

## 12. 지금 절대 하지 말아야 할 것
- `ProposalEngine.py`를 통째로 지우고 새로 짜는 행위.
- `StoryPlan` 도입을 위해 DB 스키마를 즉시 변경하는 행위.
- 프론트엔드 `CenterPanel` UI를 갈아엎는 행위.
- **Phase 1에서 `proposal_engine.py` import/연결 금지**
- **Phase 1에서 API 추가 금지**
- **Phase 1에서 런타임 경로 변경 금지**

## 13. 결론
- **Narrative Box 진행 가능 여부**: **진행 가능**.
- **전제 조건**: 기존 `proposal_story` API 응답 규격 준수 필수.
- **다음 단계**: Phase 1으로 `ccut_backend/narrative/` skeleton과 `StoryPlan` contract만 생성한다.

