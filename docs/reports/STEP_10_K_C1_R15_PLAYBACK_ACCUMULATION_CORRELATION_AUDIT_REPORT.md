# STEP 10-K-C1-R15 PLAYBACK ACCUMULATION CORRELATION AUDIT REPORT

## 1. 시작 HEAD
- `b34393302c452054d89e0e20f0e0bc4007af007f` (Stable Baseline)

## 2. git status
- `ccut_frontend/src/components/CenterPanel.tsx` (R13/R14 수정 포함 상태)
- `docs/reports/STEP_10_K_C1_R13_REMOVE_DEAD_RESYNC_SEQUENCE_CODE_REPORT.md`
- `docs/reports/STEP_10_K_C1_R14_REMOVE_FIRST_FRAGMENT_SRC_FALLBACK_REPORT.md`

## 3. 조사 파일 목록
- `ccut_frontend/src/components/CenterPanel.tsx`
- `ccut_frontend/src/hooks/useProposalState.ts`
- `ccut_frontend/src/pages/Index.tsx`
- `ccut_frontend/src/services/videoService.ts`

## 4. 재생 파이프라인 요약
1. **Trigger**: `startSeq` -> `playFrag(index 0)` 호출.
2. **Source Control**: `playerSrc` 상태를 통해 `video.src` 선언적 제어.
3. **Playback**: 소스 로드 완료(`onLoadedMetadata`) 시 예약된 `startSec`로 `currentTime` 이동 후 `play()`.
4. **Monitoring**: `onTimeUpdate`에서 `v.currentTime`이 `seqEnd`에 도달하는지 감시.
5. **Transition**: 종료 감지 시 `seqElapsedSec` 업데이트, `seqIdx` 증가, 다음 조각에 대해 `playFrag` 재호출.

## 5. buildSeqFrags 분석 (L348)
- Proposal 데이터(`key_fragments` 또는 `sequence`)에서 ID 리스트를 추출하여 `allSourceFragments`에서 실제 Fragment 객체를 매핑함.
- **특이사항**: `key_fragments`와 `sequence` 필드 중 존재하는 것을 우선 사용하며, 매핑 실패 시 필터링함.

## 6. playFrag 분석 (L360)
- `sameVideoSource`가 `true`이면 `currentTime`만 설정(`doSeekPlay`), `false`이면 `playerSrc` 상태 변경 및 `pendingLocalTime` 예약.
- **잠재 이슈**: `sameVideoSource`가 파일명만 비교하여 경로가 다른 동일 파일명 소스를 구분하지 못할 위험이 있음.

## 7. onTimeUpdate 분석 (L997, L1184)
- `globalTime = seqElapsedSec + (v.currentTime - fragStart)` 공식을 사용하여 진행바 위치 결정.
- **잠재 이슈**: 전환 직후 `v.currentTime`이 아직 `fragStart`에 도달하지 않은 상태(이전 조각의 시간)에서 이 계산이 실행되면 `globalTime`이 일시적으로 뒤로 튀거나 누적 시간에 오차를 만듦.

## 8. 누적 재생 현상 원인 후보 1~3순위
1. **1순위: currentTime 설정 무시 (Seek Failure)**: 소스 변경이나 브라우저 이벤트 루프 지연으로 인해 `playFrag`의 `currentTime` 설정이 무시되고, 영상이 이전 위치에서 계속 재생되어 "누적"된 것처럼 보임.
2. **2순위: 썸네일/초기화 로직의 간섭**: L608의 `ref.current.src` 직접 조작이 재생 중인 플레이어를 강제 리셋하거나 소스를 덮어씌움.
3. **3순위: 누적 시간 계산 오차**: `Math.max(ce - cs, 1)` 등 최소 1초 보정 로직이 실제 짧은 조각들의 합과 어긋나면서 진행바가 실제 영상보다 앞서거나 뒤처짐.

## 9. 마지막 이상코드 후보 및 상관관계 판정
- **L608: `ref.current.src` 직접 조작** -> **(A) 직접 관련**. 재생 중 `proposals` 업데이트 시 플레이어를 파괴함.
- **L1003: `v.currentTime - fragStart` 계산** -> **(A) 직접 관련**. 조각 전환 찰나의 `globalTime` 튐 현상 주범.
- **L316: `sameVideoSource` 파일명 기반 비교** -> **(A) 직접 관련**. 멀티 소스 환경에서 잘못된 소스 판단 유발.
- **L345: `playerVideoUrl` 중복 정의** -> **(B) 간접 관련**. `playerSrc`와 초기화 시점 경합 가능성.
- **L380: `doSeekPlay` 내의 에러 억제(`.catch(() => {})`)** -> **(A) 직접 관련**. 재생 실패 원인을 숨기고 누적 재생을 방치함.

## 10. 수정하면 안 되는 영역
- `useProposalState.ts`, `Index.tsx` 등 전역 상태 관리 로직 (현재 문제가 프론트엔드 컴포넌트 내부 로직에 국한됨).
- `buildSeqFrags`의 기본 매핑 로직 (데이터 구조 자체는 정상).

## 11. 최종 판정
- **AUDIT ONLY / NO CODE CHANGE**
- 현상은 **"표시상의 누적 시간 계산 취약성"**과 **"재생 위치 점프 실패"**가 복합적으로 작용한 결과임.
- 다음 단계에서 **명령적 DOM 조작 완전 제거** 및 **전환 동기화 로직 강화** 필요.
