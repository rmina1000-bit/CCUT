# CCUT1.0.4 STEP 2-F-RUNTIME-AUDIT: Intent → ProposalEngine 연결 감사 보고서

이 보고서는 `ccut-1.0.4-step9` 브랜치(최신 기준 커밋: `94cf5bdf794e73b84dc4552f77e8b042c13a2c6f`) 기준의 CCUT 1.0.4 백엔드 코드(`D:\CCUT1.0.4`)를 분석하여 **자연어/버튼 Intent → ProposalEngine** 연동 상태를 정밀 진단한 결과입니다.

> [!IMPORTANT]
> **코드 수정 금지** 원칙에 따라, 본 보고서는 현황 분석 및 단절 지점, 수정 필요 위치에 대한 **기록 및 진단만 수행**하며 어떠한 코드나 UI 수정도 수행하지 않았습니다.

---

## 1. 자연어/버튼 Intent 저장 경로 및 구조화 상태

### 1.1 Intent 수신 API 및 저장 구조
* **자연어 Intent 수신 API**:
  * **API 경로**: `POST /api/narrative/intent` 및 `POST /narrative/intent`
  * **함수명**: `post_narrative_intent` (위치: [main.py](file:///D:/CCUT1.0.4/ccut_backend/main.py#L1237))
  * **설명**: 사용자의 자연어 입력(`NarrativeIntentRequest`)을 받아 `NarrativeProviderAdapter`를 통해 `StoryIntentPatch` JSON 구조로 매핑하여 반환합니다.
* **버튼/최종 Intent 저장 API**:
  * **API 경로**: `POST /user-intent/{source_id}`
  * **함수명**: `post_user_intent` (위치: [main.py](file:///D:/CCUT1.0.4/ccut_backend/main.py#L1262))
  * **저장소 (DB)**: `user_intent` 테이블 (모델: `UserIntentTable` (위치: [db_models.py](file:///D:/CCUT1.0.4/ccut_backend/archive/db_models.py#L111)))
  * **구조화 필드**:
    * `source_id` (String, PK)
    * `must_keep` (JSON list): 필수 포함 키워드
    * `avoid` (JSON list): 회피 키워드
    * `tone` (String): 영상 톤
    * `target_length` (Float): 목표 영상 길이
    * `priority_axis` (JSON dict): visual/speech/emotion 가중치 (`{"visual": 1.0, "speech": 1.0, "emotion": 1.0}`)

### 1.2 주요 Intent 구조화/매핑 현황
* **`balanced_sources`**: **WIRED (연결됨)**
  * [story_direction_templates.json](file:///D:/CCUT1.0.4/ccut_backend/config/story_direction_templates.json#L4)에 정의된 `balanced_multi_source_record` 템플릿의 `story_intent_match` 필드로 `"coverage": "balanced_sources"`가 구조화되어 있으며, `ProposalEngine` 내에서 해당 템플릿을 식별하여 반영합니다.
* **`fast_pace`**: **PARTIAL (불완전/템플릿만 존재)**
  * [story_direction_templates.json](file:///D:/CCUT1.0.4/ccut_backend/config/story_direction_templates.json#L81)의 `shorts_hook_fast` 템플릿에서 `"pace": "fast"`로 구조화되어 있으나, `ProposalEngine` 내부에서 속도를 직접 가속하거나 컷 조절을 다르게 하는 알고리즘적 처리는 포팅되지 않아 **미지원** 상태입니다. (시뮬레이터인 `simulate_micro_candidate_layer.py`에만 개념적인 수식 존재)
* **`reduce_scenery`**: **NOT_CONNECTED (단절/미구현)**
  * 프로덕션 백엔드 엔진 및 설정 파일 전반에서 누락되었습니다. 오직 로컬 시뮬레이터인 `simulate_micro_candidate_layer.py`에만 정의되어 있습니다.
* **`human_priority`**: **NOT_CONNECTED (단절/미구현)**
  * 프로덕션 백엔드 엔진 및 설정 파일 전반에서 누락되었습니다. 오직 로컬 시뮬레이터인 `simulate_micro_candidate_layer.py`에만 정의되어 있습니다.

---

## 2. Proposal Regeneration 호출 현황

* **단일 소스 Proposal API**: `POST /proposals/{source_id}` (함수: `post_generate_proposals` (위치: [main.py](file:///D:/CCUT1.0.4/ccut_backend/main.py#L1530)))
  * **호출 여부**: 정상 호출되며, 내부적으로 `ProposalEngine.generate_proposals(source_id)`를 실행해 B안(User Mode)을 만들고, 결과를 DB의 `proposals` 테이블에 영구 저장합니다.
* **멀티 소스 Project Proposal API**: `POST /proposals/project` (함수: `post_generate_project_proposals` (위치: [main.py](file:///D:/CCUT1.0.4/ccut_backend/main.py#L1413)))
  * **호출 여부**: 정상 호출되며, `ProjectProposalRequest` payload로 `user_intent`를 직접 수신하여 `template_resolver.resolve_story_template`을 거쳐 제안서를 생성합니다.

---

## 3. 백엔드 Proposal API 수신 및 ProposalEngine 연동 감사

| API 경로 | 함수명 | 연동 상태 | 실제 Payload 예시 | 실제 Response 예시 | 끊기는 지점 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `POST /proposals/{source_id}` | `post_generate_proposals` | **PARTIAL** | (URL 파라미터로만 `source_id` 전달, 별도 body 없음) | `{"status": "PROPOSAL_READY", "source_id": "SRC_616AEFBA", "proposal_count": 2, "proposals": [...]}` | 1. 외부 API 호출 시 `user_intent`를 직접 payload로 받지 못하고 DB에 저장된 값만 참조함.<br>2. `ProposalEngine.generate_proposals`에서 `story_context={"user_intent": user_intent}` 형태로 넘겨주지만, 정작 `ProposalEngine` 내부는 `story_context`에 템플릿 결과 객체(`template_id` 등)가 담겨 있을 것을 전제로 설계되어 구조적 충돌 발생. |
| `POST /proposals/project` | `post_generate_project_proposals` | **PARTIAL** | `{"project_id": "PRJ_001", "source_ids": ["SRC_A", "SRC_B"], "target_length": 60, "user_intent": {"coverage": "balanced_sources", "must_keep": ["강아지"]}}` | `{"status": "PROPOSAL_READY", "project_id": "PRJ_001", "proposals": [...], "source_usage": {...}}` | 1. payload의 `user_intent`가 템플릿 매핑용(`coverage`)으로만 사용되며, 정작 **각 Semantic Fragment의 `edit_value` 점수를 재계산(rescore)하는 로직이 이 API 흐름상 존재하지 않음.**<br>2. 그 결과, `must_keep` 이나 `avoid` 등의 세부 키워드 필터링 및 인텐트 기반 점수 재반영이 멀티 소스 프로젝트 제안 생성 시 완전히 누락됨. |

---

## 4. ProposalEngine 내부 반영 확인 (`proposal_engine.py`)

* **`user_intent.coverage=balanced_sources` 처리 여부**: **WIRED**
  * `template_id == "balanced_multi_source_record"`일 때 `Balanced Source Constraint` 보정 로직(`_apply_balanced_source_constraints` (위치: [proposal_engine.py:L546](file:///D:/CCUT1.0.4/ccut_backend/engine/proposal_engine.py#L546)))이 올바르게 실행됩니다.
* **`source_id` 분산 선택 로직**: **WIRED**
  * `_apply_balanced_source_constraints`를 통해 다음 제약 사항이 가해집니다.
    * `min_source_coverage_ratio` (0.6): 전체 후보 소스 중 60% 이상이 포함되도록 누락된 소스의 조각을 강제 삽입.
    * `max_single_source_clip_ratio` (0.35): 특정 단일 소스 조각 비중이 35%를 초과하는 것을 제한.
    * **Source Rotation**: 시간순 정렬 이후 연속하여 동일 소스가 노출되는 것을 지양하는 교차 재배치 정렬 적용.
* **`fast_pace` / `reduce_scenery` / `human_priority` 처리 여부**: **NOT_CONNECTED**
  * 프로덕션 `ProposalEngine` 내부에서 위 필드나 인텐트 가중치에 맞춰 조각들을 다르게 선정하거나 길이를 조절하는 연산이 구현되어 있지 않습니다.
* **기존 proposal과 다른 sequence 생성 여부**: **PARTIAL**
  * `coverage=balanced_sources` 인텐트가 템플릿 형태로 인입된 경우에는 소스 분산/회전 제약조건에 의해 확연히 다른 시퀀스를 생성합니다.
  - 그러나 `must_keep`, `avoid` 등 점수 재계산과 연동되는 인텐트는 멀티 소스 제안 API 생성 과정에서 rescore가 누락되어 기존 proposal과 동일한 sequence를 생성합니다.

---

## 5. 실제 응답 로그 분석 (Evidence)

`ccut_backend/backend_live.log` 파일에서 추출한 실제 작동 로그 정보는 다음과 같습니다.

### 5.1 Intent 적용 전/후 및 Response 비교
* **Intent POST API 수신**:
  ```log
  [USER_INTENT_DEBUG] source_id: SRC_616AEFBA
  [USER_INTENT_DEBUG] user_intent payload: {'action': 'confirm_current_direction'}
  [USER_INTENT_DEBUG] target_length: None
  [USER_INTENT_DEBUG] tone: None
  [USER_INTENT_DEBUG] priority_axis: None
  ...
  INFO:     127.0.0.1:61722 - "POST /user-intent/SRC_616AEFBA HTTP/1.1" 200 OK
  ```
* **Proposal API 수신 및 생성**:
  ```log
  [PROPOSAL ENGINE] generate_proposals ENTER: SRC_616AEFBA
  [PROPOSAL ENGINE] generate_proposals_from_fragments ENTER: proj=SRC_616AEFBA, sources=['SRC_616AEFBA']
  [PROPOSAL ENGINE] Pool Diagnostics - Total: 71, None: 0, Zero: 0
  [PROPOSAL ENGINE] target_len normalized: 30.0
  [PROPOSAL ENGINE] Creating Market Proposal (A)...
  [PROPOSAL ENGINE][R2] Market max_frags=12 source_count=1 is_fast_path=True fragment_pool=71
  [PROPOSAL ENGINE] Market Proposal (A) - Selected 2 fragments, total 25.4s
  [PROPOSAL ENGINE] Creating User Proposal (B)...
  [PROPOSAL ENGINE][R4] User(Diversity) max_frags=12 source_count=1 is_fast_path=True fragment_pool=71
  [PROPOSAL ENGINE][R4-R1] No exclusive groups in B. Attempting fallback from pool (size=71)
  [PROPOSAL ENGINE][R4-R1] NO_EXCLUSIVE_GROUP_CANDIDATE: Could not find any fragments outside A's groups with ev >= 0.05
  [PROPOSAL ENGINE] User Proposal (B) - Selected 2 fragments, total 25.4s, low_edit_excluded=0
  ```
* **생성된 최종 Sequence**:
  ```log
  [R38_SEQ_AFTER_A] count=2
  [R38_SEQ_AFTER_A] 1 fid=SF_7D2BA1_SRC_616AEFBA_P001 sid=SRC_616AEFBA start=0.0 end=20.0
  [R38_SEQ_AFTER_A] 2 fid=SF_7D2BA1_SRC_616AEFBA_P071 sid=SRC_616AEFBA start=1400.0 end=1405.39
  
  [R38_SEQ_AFTER_B] count=2
  [R38_SEQ_AFTER_B] 1 fid=SF_7D2BA1_SRC_616AEFBA_P001 sid=SRC_616AEFBA start=0.0 end=20.0
  [R38_SEQ_AFTER_B] 2 fid=SF_7D2BA1_SRC_616AEFBA_P071 sid=SRC_616AEFBA start=1400.0 end=1405.39
  ```
  * **진단**: 중복 배제(`exclusive group`) 가용 조각의 `edit_value`가 0.05 미만으로 부족하여, A안과 B안이 완전히 동일한 sequence로 강제 통합(Fallback)되었음을 확인할 수 있습니다.
  * **ID 및 Created At**: 매 호출 마다 `PROP_A_[hash]_[source_id]` 형태로 UUID가 결합되어 고유한 `proposal_id`를 반환합니다.

---

## 6. 수정 필요 위치 기록 (기록만 수행)

> [!CAUTION]
> 본 보고서는 연동 단절을 복구하기 위해 수정이 권장되는 위치만을 기술하며, 실제 코드는 수정하지 않았습니다.

### 6.1 `ccut_backend/main.py`
1. **`post_generate_project_proposals` 함수 내 (위치: [main.py:L1477 부근](file:///D:/CCUT1.0.4/ccut_backend/main.py#L1477))**:
   * **원인**: 전달받은 `user_intent`를 사용해 fragments의 `edit_value`를 재계산(rescore)하는 과정이 누락되어 있음.
   * **수정안 기록**: `ProposalEngine`에 fragments를 넘겨주기 직전, `user_intent`가 존재할 경우 `SemanticFragmentGenerator(bams).rescore_fragment()`를 통해 `all_fragments` 내 모든 조각의 `edit_value`를 동적으로 재계산하여 메모리상에 반영하는 로직 추가 필요.
2. **`post_generate_proposals` 함수 내 (위치: [main.py:L1530 부근](file:///D:/CCUT1.0.4/ccut_backend/main.py#L1530))**:
   * **원인**: 단일 소스 생성 시 payload로부터 직접 `user_intent`를 수신할 수 없으며, API가 intent를 받도록 수정되어 있지 않음.
   * **수정안 기록**: API 메서드가 JSON body로 `user_intent: Optional[dict] = None`을 인자로 받도록 수정하고, 이를 `ProposalEngine` 호출 시 전달하도록 변경 필요.

### 6.2 `ccut_backend/engine/proposal_engine.py`
1. **`generate_proposals` 함수 내 (위치: [proposal_engine.py:L31](file:///D:/CCUT1.0.4/ccut_backend/engine/proposal_engine.py#L31))**:
   * **원인**: `story_context={"user_intent": user_intent}` 형태로 넘겨주고 있으나, 호출받은 `generate_proposals_from_fragments`는 `story_context`를 템플릿 Resolver의 반환 객체로 취급하므로 하위 분기문에서 속성이 무시되거나 에러를 낼 위험이 있음.
   * **수정안 기록**: `story_context`에 템플릿 정보가 없더라도, `user_intent` 구조체 내의 값을 인계받아 템플릿 매핑을 수행하거나 기본 템플릿을 생성할 수 있도록 보정 필요.
2. **`_create_user_proposal` 함수 내 (위치: [proposal_engine.py:L230](file:///D:/CCUT1.0.4/ccut_backend/engine/proposal_engine.py#L230))**:
   * **원인**: 매개변수로 `intent`를 넘겨받지만 정작 함수 본문 내에서는 `intent` 필드를 활용해 점수를 매기거나 회피/필수 장면 필터링을 수행하는 코드가 아예 없음. (점수 재계산은 오직 `SemanticFragmentGenerator` 단독으로 수행하게 분리되어 설계상 불일치함)
   * **수정안 기록**: `intent` 매개변수에서 `must_keep`, `avoid` 등을 직접 조회해 `edit_score` 내림차순 정렬 과정에 직접적인 보너스/페널티 스코어를 실시간으로 부여하거나, 불필요한 `intent` 매개변수를 완전히 제거하고 `main.py` 단에서 rescore가 완결되도록 API 흐름을 통일해야 함.
3. **`fast_pace` 구현 누락**:
   * **수정안 기록**: `shorts_hook_fast` 템플릿이 활성화되었을 때, `ProposalEngine` 시퀀스 조합 알고리즘 상에서 조각의 최대 허용 duration을 짧게 제한하고 context 대비 hook/payoff 비중을 상향 조정하는 제약 조건 파라미터 추가 반영 필요.
