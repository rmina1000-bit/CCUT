# STEP 10-I.5.27-E7-M1 — Snapshot / Memory / Debug Log Audit

## 1. 개요 (Objective)
현재 CCUT의 체감 성능을 유지하면서, 브라우저 메모리 사용량 및 콘솔 로그 과다 출력 여부를 정밀 진단합니다. 특히 Chrome DevTools의 Heap Snapshot과 CCUT 내부 로직상의 Snapshot을 명확히 구분하고, 대규모 조각(300~500개) 환경에서의 리스크를 분석합니다.

## 2. 환경 정보 (Environment)
- **현재 SHA**: `f6d289bb6a7d14d5b39a105845eb3f85e3b3d516`
- **Git Status**: Clean (수정 사항 없음)
- **작업 내용**: 코드 수정 없이 조사 및 분석만 수행함.

## 3. 검색 결과 요약 (Keyword Search)
다음 키워드에 대해 전체 프로젝트 조사를 수행했습니다:
`snapshot`, `heap`, `memory`, `fragmentmap-debug`, `proposalResolver`, `resolved ids` 등.

### 주요 위치 및 검색 결과
| 키워드 | 주요 발생 파일 | 역할 및 빈도 |
|:---|:---|:---|
| `directionSnapshot` | `src/hooks/useProposalState.ts`, `src/proposal/proposalTypes.ts` | 재제안(Reproposal)용 사용자 지시 상태 (R1, R2...) |
| `snapshot_id` | `src/proposal/directionSnapshot.ts` | 제안 라운드 식별자 |
| `heap` | `ccut_frontend/package-lock.json` | Vitest 등 외부 라이브러리 의존성 내 존재 |
| `memory` | `ccut_backend/engine/blackbox.py`, `src/hooks/use-toast.ts` | 시스템 메모리 모니터링 및 Toast 상태 관리 |
| `fragmentmap-debug`| `src/pages/Index.tsx` | FragmentMap 렌더링 전 ID 매칭 진단 로그 |
| `proposalResolver` | `src/utils/proposalFragmentResolver.ts` | 제안 조각 해석 결과 요약 로그 |

---

## 4. CCUT 내부 Snapshot 분류
코드 내 존재하는 "Snapshot" 키워드는 다음과 같이 분류됩니다.

| 분류 | 위치 (파일/라인) | 역할 | 런타임 사용 | 메모리 영향 | 유지 필요성 |
|:---|:---|:---|:---|:---|:---|
| **B. DirectionSnapshot** | `directionSnapshot.ts` | 재제안 시 사용자 지시(Tone, Pace 등) 저장 | **Yes** (Reproposal 시) | 낮음 (단순 객체) | **필수** (기능 핵심) |
| **C. Proposal Snapshot** | `proposalTypes.ts` | 제안된 sequence(ID 목록) 저장 | **Yes** (A/B 표시) | 낮음 (ID 문자열 배열) | **필수** (UI 표시용) |
| **D. Undo Snapshot** | `CCUT-HANDOFF-SPEC.md` | Undo/Redo를 위한 편집 상태 저장 (구현 예정) | **No** (명세만 존재) | 중간 (Stack 누적 시) | **필수** (기능 구현 시) |
| **E. Debug Log** | `Index.tsx`, `proposalFragmentResolver.ts` | 매칭 과정 진단용 ID 출력 | **Yes** (콘솔 출력) | 매우 낮음 | **조건부** (개발 전용) |

---

## 5. Chrome DevTools Heap Snapshot 해석
**주의: CCUT의 `DirectionSnapshot`과 Chrome의 `Heap Snapshot`은 완전히 다른 개념입니다.**

- **Chrome Heap Snapshot**:
    - 브라우저가 실행 중인 모든 JavaScript 객체(DOM, Strings, Arrays, Closures)를 메모리에서 덤프한 것.
    - DevTools를 열고 있는 동안에만 관측되며, 앱이 명시적으로 저장하는 데이터가 아님.
    - CCUT의 특정 로직(예: `setEditFragments`)이 대량의 데이터를 State에 담고 있을 때 Heap 용량이 증가함.
- **CCUT 내부 Snapshot**:
    - "특정 시점의 편집 상태"를 기록한 논리적 데이터.
    - JSON 형태의 가벼운 객체로 관리됨.

---

## 6. 콘솔 로그 과다 여부 및 리스크 분석
현재 출력되는 주요 디버그 로그의 위험도를 평가합니다.

| 로그 프리픽스 | 출력 시점 | 출력 데이터 크기 | 조각 500개 시 위험도 | 운영 모드 권장 |
|:---|:---|:---|:---|:---|
| `[PERCEIVED_TIMING]` | 분석/제안 완료 후 1회 | 작음 (JSON 1개) | **낮음** | **유지** (성능 지표) |
| `[proposalResolver]` | 제안 해석 시마다 | 중간 (Summary + 샘플) | **낮음** (샘플링 출력 중) | **숨김** (DEBUG 전용) |
| `[fragmentmap-debug]`| State 변경 시 (useMemo) | **큼** (전체 ID 목록 포함 가능) | **높음** (콘솔 스팸 및 성능 저하) | **숨김** (DEBUG 전용) |

> [!WARNING]
> `[fragmentmap-debug]` 로그는 `Index.tsx`의 `useMemo` 안에 위치하여, 컴포넌트가 리렌더링되거나 State가 바뀔 때마다 실행됩니다. 조각이 500개 이상일 경우 ID 배열을 출력하는 과정에서 브라우저 메인 쓰레드에 부하를 줄 수 있습니다.

---

## 7. 조각당 Snapshot 정책 제안 (Proposed Policy)
국장님 의견에 따라 메모리 효율성을 극대화하기 위한 정책안입니다.

1.  **Fragment Thumbnail**: 조각당 **1개 URL** 원칙 (Base64 지양, Static URL 사용).
2.  **Semantic Summary**: 조각당 **1개** 텍스트 필드 유지.
3.  **DirectionSnapshot**: 사용자의 "재지시 명령" 라운드당 **1개** 생성 (Undo용).
4.  **Proposal Sequence**: Proposal 객체는 **ID 배열**만 참조 (Deep Copy 지양).
5.  **Debug Log**: `process.env.NODE_ENV === 'development'` 일 때만 활성화하거나 `DEBUG` 플래그 사용.
6.  **Heap Management**: 사용하지 않는 이전 `sourceEntries`는 분석 완료 후 필요 시 메모리에서 해제(Nullify) 고려.

---

## 8. 결론 및 제안
- **조사 결과**: CCUT 내부 스냅샷 로직은 매우 가볍고 메모리 효율적으로 설계되어 있음.
- **주요 리스크**: `Index.tsx`와 `proposalFragmentResolver.ts`에 산재한 **콘솔 로그**가 실제 대규모 데이터 환경에서 체감 속도를 떨어뜨릴 가능성이 큼.
- **다음 단계 제안**:
    1.  디버그 로그를 `console.debug`로 변경하거나 특정 플래그가 있을 때만 출력하도록 가드 설치.
    2.  `fragmentmap-debug`에서 전체 ID 목록 출력을 제거하고 개수(Count) 위주로 요약.
    3.  운영 모드 빌드 시 개발 로그 자동 제거 설정 적용.

---
**보고자**: Antigravity AI
**판정**: PASS (코드 수정 없이 정밀 분석 완료)
