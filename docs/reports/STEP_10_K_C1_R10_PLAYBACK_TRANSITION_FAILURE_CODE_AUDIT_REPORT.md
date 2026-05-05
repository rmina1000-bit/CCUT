# STEP 10-K-C1-R10 PLAYBACK TRANSITION FAILURE CODE AUDIT REPORT

## 1. 시작 HEAD
- `6c7928a4effe38dc03d6a7cf4cb1aca1d7d189c9`

## 2. git status
- `ccut_frontend/src/components/CenterPanel.tsx` (Modified - R9.1 Rollback 적용됨)
- `docs/reports/STEP_10_K_C1_R9_ROLLBACK_TO_LAST_KNOWN_GOOD_A_PREVIEW_STATE_REPORT.md` (Created)

## 3. 조사 파일 목록
- `ccut_frontend/src/components/CenterPanel.tsx`
- `ccut_frontend/src/pages/Index.tsx`
- `ccut_frontend/src/hooks/useProposalState.ts`
- `ccut_frontend/src/proposal/proposalTypes.ts`

## 4. 관련 state/ref/function 줄 번호 (CenterPanel.tsx 기준)
- **A/B video ref**: L177 (`videoRefA`), L178 (`videoRefB`)
- **A/B current segment index state (Ref)**: L267 (`seqIdxARef`), L272 (`seqIdxBRef`)
- **A/B proposal global time state**: L223 (`proposalTimeA`), L224 (`proposalTimeB`)
- **A/B playing state**: L220 (`isPlayingA`), L221 (`isPlayingB`)
- **playFrag 함수**: L357-L401
- **getVideoUrlForFrag 함수**: L317-L330
- **seekProposal 함수**: L515-L551
- **resolveProposalTime 함수**: L494-L513
- **onTimeUpdate 핸들러**: L1016 (A), L1165 (B)
- **onEnded 핸들러**: 없음 (onTimeUpdate의 `near` 로직이 대신함)
- **onLoadedMetadata 핸들러**: L1062 (A), L1211 (B)
- **proposal-level seek bar input**: L1094 (A), L1243 (B)
- **A/B sequence origin**: `buildSeqFrags` (L345)가 `proposals`에서 가져옴
- **sequence item 구조**: `Fragment` 타입 (L4), `start_frame`, `end_frame` 필드 사용

## 5. 실제 재생 흐름 (Text Diagram)
1. **재생 시작**: 사용자가 플레이어 클릭 → `startSeq` 호출
2. **상태 설정**: `isSeqARef = true`, `seqIdxARef = 0`, `seqElapsedSecARef = 0` 초기화
3. **조각 재생**: `playFrag` 호출 → `video.src` 확인 및 설정 → `currentTime` 설정 → `play()`
4. **진행 업데이트**: `onTimeUpdate` 발생 → `globalTime` 계산 (`seqElapsedSec` + `currentTime` 오프셋) → `setProposalTime`으로 바 이동
5. **조각 종료 감지**: `v.currentTime >= seqEndARef` 조건 만족 (Transition 발생)
6. **다음 조각 전환**:
   - `seqElapsedSecARef`에 현재 조각 길이 누적
   - `seqIdxARef` 1 증가
   - `playFrag` 재호출 (다음 조각 재생)
7. **시퀀스 종료**: `nextIdx >= frags.length`이면 `stopSeq` 호출 및 리셋

## 6. 조사 질문 답변
1. **1번 조각 종료 시 실제로 어떤 onEnded 코드가 실행되는가?**: 명시적 `onEnded`는 없으며 `onTimeUpdate` 내의 `near` 감지 블록(L1026/L1175)이 실행됨.
2. **onEnded에서 next index를 계산하는가?**: `onTimeUpdate` 내에서 `nextIdx = seqIdxARef.current + 1`을 계산함 (L1030/L1179).
3. **next index 계산 후 실제 video src가 2번 조각으로 바뀌는가?**: `playFrag` 내부에서 `getVideoUrlForFrag`를 통해 URL을 비교한 뒤, 다르면 `src`를 교체하고 `load()`를 호출함.
4. **2번 조각으로 바뀌기 전에 current segment index가 다시 0으로 초기화되는 코드가 있는가?**: 코드상으로 전환 중에 0으로 초기화하는 로직은 없으나, `startSeq` 재호출 시 0으로 초기화됨. 만약 클릭 이벤트가 중복 발생하거나 특정 `useEffect`가 트리거되면 발생 가능.
5. **onTimeUpdate에서 segment index를 0으로 되돌리는 조건이 있는가?**: 없음. 마지막 조각 이후에는 `-1`로 설정됨.
6. **onLoadedMetadata에서 currentTime 또는 index를 0으로 되돌리는 코드가 있는가?**: 없음. (R9.1에서 리셋 로직 제거됨)
7. **seekProposal에서 다음 조각 이동과 일반 seek 이동이 충돌하는가?**: 사용자가 바를 잡고 있을 때는 `onTimeUpdate` 리턴 로직(L1017)으로 보호되지만, `onPointerUp` 직후 `seekProposal`과 `onTimeUpdate`의 경합 가능성 존재.
8. **A/B가 같은 state/ref를 공유해서 서로 덮어쓰는가?**: `activePlayerRef`(L183)를 공유함. 한쪽이 재생될 때 다른 쪽을 `stopSeq` 하는 과정에서 공유 Ref 상태가 꼬일 가능성 있음.
9. **React key 또는 video src 변경으로 video element가 remount되며 상태가 초기화되는가?**: `key`가 없으므로 remount는 안 되지만, `src` 변경 시 브라우저가 `currentTime`을 0으로 리셋하고 `onTimeUpdate`를 한 번 더 발생시킬 수 있음.
10. **sequence item duration이 실제 video duration과 달라 조기 종료/리셋을 유발하는가?**: `ce - cs` 계산(L1036)과 실제 프레임 타임 오차(1/30s 단위)로 인해 `near` 체크가 튀거나, 마지막 조각에서 `video.duration`에 도달하기 전 `near`가 안 걸리면 멈춰버릴 수 있음.

## 7. 리셋 가능성이 있는 코드 위치
- **L1045 / L1194**: `nextIdx`가 범위 밖으로 나갔다고 판단하여 `stopSeq`가 호출되는 지점. 전환 로직이 중복 트리거되어 인덱스가 순식간에 끝까지 도달할 수 있음.
- **L553-L568**: `useEffect` 내의 `appState` 감시 로직. `appState`가 `complete`로 유지되더라도 의도치 않은 리렌더링 시 `stopSeq`가 호출될 여지가 있음.

## 8. 가장 유력한 원인 1~3순위
1. **순위 1: `onTimeUpdate` 중복 트리거 (Double Transition)**: `playFrag` 호출 후 실제 비디오가 새 위치로 Seek 되기 전, 브라우저가 이전 조각의 종료 시간(`currentTime >= seqEnd`)을 가진 `onTimeUpdate`를 한 번 더 발생시킴. 이로 인해 인덱스가 연속으로 증가하여 시퀀스가 조기 종료됨.
2. **순위 2: Source Switching 시 `currentTime` 0 리셋 간섭**: `src` 변경 시 브라우저가 `currentTime`을 0으로 밀어버리는데, 이때 `onTimeUpdate`가 `seqElapsedSec`를 더한 `global` 시간을 0 근처로 계산하여 바가 처음으로 튀거나 리셋됨.
3. **순위 3: `activePlayerRef` 공유 및 `stopSeq` 간섭**: A 재생 시 B를 중지시키는 과정에서 `setActivePlayerSafe`와 `isSeqARef` 상태가 미세한 차이로 경합하여 재생 루프가 파괴됨.

## 9. 최종 판정 및 제안
- **최종 판정**: 현재 문제는 "로직의 부재"가 아니라 "브라우저 이벤트(onTimeUpdate)의 비결정적 실행과 상태 업데이트 간의 경합"으로 인한 **시퀀스 조기 종료(Early Termination)**임.
- **다음 수정 작업 제안**:
  1. `onTimeUpdate` 내부에 **`isTransitioningRef` 플래그**를 도입하여 조각 전환 중 중복 진입 차단.
  2. `v.currentTime`이 실제로 새 조각의 `start_frame` 범위에 도달했는지 확인하는 유효성 검사 추가.
  3. `near` 체크 임계값 최적화 또는 `onEnded`를 통한 명시적 종료 처리 검토.
