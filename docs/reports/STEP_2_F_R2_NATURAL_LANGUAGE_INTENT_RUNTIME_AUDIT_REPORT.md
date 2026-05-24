# CCUT1.0.4 STEP 2-F-R2 Natural Language Intent Runtime Audit 보고서

이 보고서는 `ccut-1.0.4-step9` 브랜치(최신 기준 커밋: `cfffce92e324cc3a3fd7f85cfd8edaf690702305`) 기준의 CCUT 1.0.4 소스코드(`D:\CCUT1.0.4`)를 분석하여 **자연어 지시 → ProposalEngine 재생성** 흐름의 런타임 연동 상태를 정밀 진단한 결과입니다.

> [!IMPORTANT]
> **코드 수정 금지** 원칙에 따라, 본 보고서는 연동 상태 진단 및 끊기는 지점, 수정 필요 위치에 대한 **기록만 수행**하며 어떠한 코드나 UI 수정도 수행하지 않았습니다.

---

## 1. 자연어 입력 처리 경로 (프론트엔드)

### 1.1 입력 수신 및 라우팅 흐름
* **자연어 채팅창 입력 (문장형 Intent)**:
  * **수신 컴포넌트**: [CenterPanel.tsx](file:///D:/CCUT1.0.4/ccut_frontend/src/components/CenterPanel.tsx#L756)
  * **함수명**: `handleSendFull`
  * **전달 경로**: 채팅 메시지 전송 시 `onReproposal?.(raw)`을 호출하고, 이는 `Index.tsx`를 통해 `useProposalState.ts`의 `handleReproposal` 함수로 전달됩니다.
* **의견 제안 칩 버튼 클릭 (버튼형 Intent)**:
  * **수신 컴포넌트**: [CenterPanel.tsx](file:///D:/CCUT1.0.4/ccut_frontend/src/components/CenterPanel.tsx#L1006)
  * **함수명**: 칩 버튼 `onClick` 이벤트 핸들러
  * **전달 경로**: 버튼 클릭 시 `onConsultation?.(intentText)`를 호출하고, 이는 `Index.tsx`를 통해 `useProposalState.ts`의 `handleConsultation` 함수로 전달됩니다.

> [!WARNING]
> **경로 불일치**: 버튼 Intent와 자연어 문장 Intent가 프론트엔드 내에서 서로 다른 핸들러(`handleConsultation` vs `handleReproposal`)를 타도록 분리되어 있습니다.

### 1.2 상태 갱신 여부
* `handleConsultation`은 `narrativeService.interpretIntent(text)`를 통해 백엔드 해석 API(`/narrative/intent`)를 호출한 후 반환된 패치 데이터로 `storyPlan.story_intent` 객체를 실제 업데이트합니다.
* 그러나, 프론트엔드와 백엔드 모두에서 **인텐트 갱신 완료 후 실제 제안서 재생성 API를 연결하여 호출하는 제어부 흐름이 아예 누락**되어 있습니다.

---

## 2. Proposal 재생성 호출 및 결과 재사용 여부

* **재생성 API 호출 여부**: **NOT_CONNECTED (호출 안 됨)**
  * 사용자가 자연어를 입력하거나 의견 제안 칩 버튼을 클릭하더라도 백엔드의 `/proposals/project` 또는 `/proposals/{source_id}` 재생성 API는 **전혀 호출되지 않습니다.**
* **기존 결과 재사용 여부**: **YES (무조건 재사용)**
  * 제안서 재생성 프로세스가 트리거되지 않으므로, 최초 분석 단계에서 받아온 `proposals` 상태를 그대로 유지 및 재사용합니다.
  * **proposal_id**: 변경 없이 기존 ID 유지.
  * **preview_url**: 변경 없이 기존 프리뷰 비디오 URL 유지.
  * **sequence**: 변경 없이 기존 편집 시퀀스 카드 유지.
  * **localStorage / Cache**: 제안서 내용이나 시퀀스 자체를 브라우저 캐시에 저장하는 로직은 없으나, React `useState` 상태가 유지되고 재요청이 나가지 않아 자연스럽게 기존 결과가 유지되는 형태입니다.

---

## 3. Micro Candidate 런타임 연결 여부

* ** simulates_micro_candidate_layer.py 런타임 호출 여부**: **NOT_CONNECTED**
  * `tools/simulate_micro_candidate_layer.py`는 백엔드 서버(Uvicorn) 구동 및 서비스 API 파이프라인 상에서 전혀 실행되거나 유기적으로 호출되지 않습니다.
* **시뮬레이션 JSON 데이터 로드 여부**: **NOT_CONNECTED**
  * `artifacts/micro_candidate_simulation/*.json` 파일들은 백엔드 `ProposalEngine`이나 다른 런타임 분석 엔진에서 **전혀 로드하지 않으며 참조조차 하지 않습니다.**

---

## 4. 감사 보고 요약

* **파일명**:
  * **프론트엔드**:
    * [useProposalState.ts](file:///D:/CCUT1.0.4/ccut_frontend/src/hooks/useProposalState.ts)
    * [CenterPanel.tsx](file:///D:/CCUT1.0.4/ccut_frontend/src/components/CenterPanel.tsx)
    * [Index.tsx](file:///D:/CCUT1.0.4/ccut_frontend/src/pages/Index.tsx)
  * **백엔드**:
    * [main.py](file:///D:/CCUT1.0.4/ccut_backend/main.py)
    * [proposal_engine.py](file:///D:/CCUT1.0.4/ccut_backend/engine/proposal_engine.py)
* **함수명**:
  * **자연어 Intent 전송**: `CenterPanel.handleSendFull` → `useProposalState.handleReproposal`
  * **버튼 Intent 클릭**: `CenterPanel.onClick` → `useProposalState.handleConsultation`
* **API 경로**:
  * 인텐트 해석 API: `POST /narrative/intent`
  * 제안 재생성 API: `POST /proposals/project` (멀티) 및 `POST /proposals/{source_id}` (단일)
* **실제 Payload 비교**:
  * **초기 생성 시**: `{"project_id": "...", "source_ids": [...], "target_length": 60}`
  * **자연어/버튼 입력 시**: 재생성 호출 자체가 차단되어 API가 나가지 않음.
* **실제 Response proposal_id 비교**: 재생성 생략으로 인해 이전 응답의 proposal_id를 100% 재사용.
* **preview_url 변경 여부**: 변경 없음.
* **sequence 변경 여부**: 변경 없음.
* **연결 상태**: **NOT_CONNECTED**
* **끊기는 지점**:
  * 프론트엔드 `useProposalState.ts`의 `handleReproposal` 함수 내부:
    ```typescript
    if (proposals) {
      console.warn("[Reproposal] Local strategyEngine is legacy fallback only. Backend narrative reproposal is required.");
      setDirectionSnapshot(nextSnapshot);
      return; // <--- 여기서 리턴하여 백엔드 재생성 API를 호출하지 않고 차단함
    }
    ```
  * 프론트엔드 `useProposalState.ts`의 `handleConsultation` 함수 내부:
    * `/narrative/intent` API를 호출해 인텐트 해석은 수행하지만, 해석된 인텐트를 실어서 제안서를 다시 생성하는 `/proposals/project` 또는 `/proposals/{source_id}` 호출 로직 자체가 없습니다.

---

## 5. 수정 필요 위치 기록 (기록만 수행)

### 5.1 `ccut_frontend/src/hooks/useProposalState.ts`
1. **`handleReproposal` 및 `handleConsultation` 함수**:
   * **수정안**: 인텐트 해석이 완료되거나 `directionSnapshot`이 변경될 때, `videoService.requestProjectProposals`를 새 인텐트 payload(`user_intent`)와 함께 재호출하여 proposals 상태를 강제 갱신(`setProposals`)하는 연동 비동기 호출부 작성이 필요합니다.
   * **수정안**: 분리되어 작동하는 두 제어 핸들러의 결과가 궁극적으로 동일한 백엔드 제안서 갱신 파이프라인으로 흘러들어가도록 통합 제어가 요구됩니다.

### 5.2 `ccut_backend/main.py`
1. **`post_generate_project_proposals` 함수 내 (위치: [main.py:L1477 부근](file:///D:/CCUT1.0.4/ccut_backend/main.py#L1477))**:
   * **수정안**: `requestProjectProposals` API에 `user_intent`가 포함되어 전달되었을 때, `ProposalEngine`에 fragments 리스트를 넘겨주기 전 `SemanticFragmentGenerator(bams).rescore_fragment()`를 실행하여 각 조각의 `edit_value`를 실시간 반영하도록 백엔드 점수 보정 로직 연동이 필요합니다.
