# Story Intent Pipeline Bridge Plan

## 1. 개요
현재 CCUT 1.0.4의 가장 큰 문제점은 프론트엔드에서 획득한 고도의 "사용자 의도"가 백엔드 제안 엔진까지 도달하지 못하고 증발한다는 점입니다. 이 문서는 이 단절된 파이프라인을 복구하기 위한 최소 연결 계획을 정의합니다.

## 2. 단절 지점 및 해결책

### [BP-1] Frontend State -> API Payload
- **현상**: `useProposalState`의 `story_intent`가 `videoService.requestProjectProposals` 호출 시 누락됨.
- **해결**: `videoService.ts`의 인자를 수정하여 `user_intent` 객체를 Payload에 포함.

### [BP-2] API Contract (Pydantic Model)
- **현상**: `main.py`의 `ProjectProposalRequest`에 의도를 받을 그릇이 없음.
- **해결**: `user_intent: Optional[dict] = None` 필드 추가.

### [BP-3] Backend Engine Entry
- **현상**: `ProposalEngine.generate_proposals_from_fragments`가 `intent` 인자를 받지 않음.
- **해결**: 함수 시그니처에 `intent=None` 추가 및 내부 하드코딩 제거.

## 3. 우선순위 연결 대상: `balanced_sources`
전체 파이프라인을 한꺼번에 연결하기보다, 사용자의 갈증이 가장 큰 "여러 영상 골고루" 의도를 최우선으로 연결합니다.

| 필드 | 값 | 영향 (Proposal Engine) |
| :--- | :--- | :--- |
| `user_intent.coverage` | `"balanced_sources"` | `source_rotation`, `source_diversity_guard` 기술 팩 활성화 |
| `template_id` | `"balanced_multi_source_record"` | `story_direction_templates.json` 기술 바인딩 참조 |

## 4. 구현 단계 (R10-K-B2)

1.  **Backend Model Update**: `main.py` 내 `ProjectProposalRequest` 수정.
2.  **Technique Resolver**: `editing_techniques.json`에서 기술 명세를 로드하고 템플릿에 주입하는 유틸리티 구현.
3.  **Engine Signature Update**: `proposal_engine.py` 인자 확장.
4.  **Frontend Wiring**: `Index.tsx`에서 `storyPlan.story_intent`를 추출하여 API 호출부에 주입.


## 5. 기대 효과
- 사용자가 "여러 영상 골고루"를 선택했을 때, 실제로 A/B 제안의 소스 구성이 눈에 띄게 다양해짐.
- 하드코딩된 제안 로직에서 데이터 중심(Template Registry)의 제안 로직으로 전환.

---
**Status**: Bridge Plan Defined (Next: STEP 10-K-B2 Implementation)
