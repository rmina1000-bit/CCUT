# Report: Mirror A Preview Logic to B (STEP 10-K-C1-R7)

## 1. 개요
Draft A안의 정상적인 탐색 및 진행바 동기화 로직을 B안에도 완벽히 이식하여, 두 제안 영상의 사용자 경험(UX)을 동일하게 맞추고 B안에서 발생하던 진행바 튕김 현상을 해결하였다.

---

## 2. 주요 수정 및 점검 내용

### [A/B 로직 동기화 및 복구]
*   **Draft A 복구:** 이전 작업 중 누락되었던 A안의 `onTimeUpdate` 내 `setProposalTimeA` 갱신 로직을 복구함. (A안이 "정상"으로 보였던 것은 이전 상태값이 유지되었기 때문이며, 실제로는 재생 시 진행바가 자동으로 따라오지 않았을 가능성이 높음)
*   **Draft B 이식:** A안의 성공적인 전역 시간(Global Time) 계산 공식을 B안의 `onTimeUpdate`에도 동일하게 적용함.
    *   `fragStart` 계산: 현재 재생 중인 조각의 물리적 시작 시간 추출.
    *   `global` 계산: `seqElapsedSecBRef`(누적 시간) + `v.currentTime - fragStart`(현재 조각 내 진행 시간).
    *   상태 갱신: `setProposalTimeB(global)`를 통해 진행바 위치를 실시간 동기화.

### [튕김 현상 방지]
*   사용자가 직접 탐색바를 조작 중일 때(`isDraggingProposalSeekBRef.current`)는 `onTimeUpdate`에 의한 강제 상태 갱신을 차단함.
*   이로써 사용자가 바를 끌고 있을 때 비디오 재생 시점이 현재 위치로 바를 되돌리는(Snap-back) 충돌 현상을 제거함.

---

## 3. 검증 결과

| 항목 | 결과 | 비고 |
| :--- | :---: | :--- |
| **Draft A 진행바 동기화** | **PASS** | 재생 시 바가 실시간으로 따라옴 |
| **Draft B 진행바 동기화** | **PASS** | 재생 시 바가 실시간으로 따라옴 |
| **B안 바 튕김 해결** | **PASS** | 탐색 후 바가 0으로 돌아가지 않고 유지됨 |
| **A/B 독립성** | **PASS** | A 조작이 B에 영향을 주지 않으며 그 반대도 마찬가지임 |
| **npm run build** | **PASS** | 빌드 및 문법 오류 없음 |

---

## 4. 최종 판정

### **[RESULT] PASS**
*   **사유:** A안의 검증된 로직을 B안에 구조적으로 이식하여 두 플레이어의 동작을 일치시켰으며, 전역 시간축(Global Timeline) 기반의 탐색 시스템이 안정적으로 작동함을 확인함.
