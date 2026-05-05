# Report: Native Seek Respect Repair (STEP 10-K-C1-R3)

## 1. 개요
브라우저 기본 `<video controls>`를 사용할 때, 사용자가 진행바를 통해 임의의 위치로 이동(Seek)하면 CCUT의 시퀀스 동기화 로직이 이를 감지하지 못하고 이전 재생 위치로 강제 복구(Snap-back)시키는 문제를 해결하였다.

---

## 2. 기존 문제점 및 원인
*   **문제 현상:** 사용자가 진행바를 클릭하여 앞/뒤로 이동해도, 약 0.1초 후에 영상이 원래 재생되던 조각의 위치로 되돌아감.
*   **원인:** `onTimeUpdate` 이벤트가 매 프레임마다 현재 조각의 종료 시간(`seqEndRef`)을 체크하는데, 사용자가 seek를 하더라도 `seqIdxRef`가 갱신되지 않아 로직상 "현재 조각이 끝났다"고 판단하거나 "현재 조각의 시작점으로 되돌려야 한다"고 오작동함.

---

## 3. 수정 내용

### [isUserSeekingRef 도입]
*   `isUserSeekingARef`, `isUserSeekingBRef` (useRef)를 추가하여 사용자가 현재 진행바를 조작 중인지 추적함.
*   `onSeeking`: 사용자가 조작을 시작하면 `true`로 설정.
*   `onSeeked`: 조작이 끝나면 `false`로 설정.

### [onTimeUpdate 방어 로직]
*   `isUserSeekingRef.current`가 `true`일 경우 `onTimeUpdate` 로직을 즉시 종료하여 시퀀스 동기화 코드가 `currentTime`을 건드리지 못하게 함.

### [reSyncSequence 구현]
*   `onSeeked` 이벤트 발생 시 호출됨.
*   사용자가 이동한 새로운 `v.currentTime` 값을 기반으로, 해당 시간이 어느 조각(Fragment)에 해당하는지 시퀀스 리스트에서 재탐색함.
*   찾은 조각의 인덱스로 `seqIdxRef`를 업데이트하고, `seqEndRef` 및 누적 재생 시간(`seqElapsedSecRef`)을 동기화함.
*   이를 통해 사용자가 이동한 위치에서부터 시퀀스 재생이 자연스럽게 이어지도록 함.

---

## 4. 검증 결과

| 항목 | 결과 | 비고 |
| :--- | :---: | :--- |
| **앞으로 Seek** | **PASS** | 이동한 위치에서 멈춤 없이 재생 유지 |
| **뒤로 Seek** | **PASS** | 이전 조각으로 이동 시 해당 조각부터 다시 시퀀스 시작 |
| **조각 전환 유지** | **PASS** | Seek 후에도 현재 조각이 끝나면 다음 조각으로 정상 전환됨 |
| **Snap-back 제거** | **PASS** | 이전 위치로 강제 복구되는 현상 소멸 |
| **npm run build** | **PASS** | 문법 오류 없음 |

---

## 5. 최종 판정

### **[RESULT] PASS**
*   **사유:** 사용자의 의도적인 탐색(Seek) 동작을 최우선으로 존중하도록 로직을 보정하였으며, 탐색 완료 후 시퀀스 상태를 새로운 위치에 맞게 재동기화함으로써 네이티브 컨트롤과 CCUT 엔진 간의 정합성을 확보함.
