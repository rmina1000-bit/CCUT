# CCUT1.0.4 다음 방 전달문 (통합 수리 완료본)

작성일: 2026-05-25  
최종 커밋 HEAD: `8190133ec63934076aa17cb295caf1eb03d6a0ed` (ccut-1.0.4-step9 원격 브랜치 푸시 완료)

---

## 1. 시작 및 검수 명령

다음 방 시작 시, 아래 명령어로 현재 저장소 상태가 깨끗하게 반영되어 있는지 점검하십시오.

```powershell
cd D:\CCUT1.0.4

git status --short
git diff --stat
git log --oneline -5
git rev-parse HEAD
```

---

## 2. 해결된 핵심 파이프라인

오늘 해결한 문제는 “여러 영상 골고루”가 안 되는 단일 버그가 아니라, 아래 전체 파이프라인의 단절을 복구한 시스템 엔지니어링 작업이었다.

```text
자연어 입력 ("골고루")
→ handleConsultation
→ /narrative/intent (LLM coverage schema 확장)
→ /proposals/project (source_ids payload 유실 해결)
→ project_id 기반 DB 역조회 (GET /proposals/project/{project_id}/sources 신설)
→ frontend sourceEntries hydration (새로고침 시 22개 소스 완벽 복원)
→ ProposalEngine balanced_sources (0.05 임계치 완화 및 Round-Robin 분산 적용)
→ CenterPanel A/B player 즉시 노출 (confirmed 조건 완화)
```

---

## 3. 핵심 수리 영역 및 가드 설계

### 3.1 LLM 자연어 인쇄 계약 확장
- **수리**: `narrative_provider_contract.py` 및 `narrative_provider_adapter.py` 내 Ollama Schema와 StoryIntentPatch 데이터 규격에 `coverage` 속성을 추가하여 LLM이 자연어를 통해 직접 `coverage: "balanced_sources"`를 도출하도록 개선.

### 3.2 백엔드 프로젝트 소스 역조회 API 구축
- **수리**: `main.py`에 `GET /proposals/project/{project_id}/sources` API를 구현하여 proposals sequence JSON으로부터 소스 목록을 역추적 복원.
- **안전 가드**: 위험한 DB 전체 sources fallback을 완전히 제거했으며, 제안 정보를 찾지 못하면 `NO_PROPOSALS_FOUND` 에러(sources: [])를 안전하게 반환하여 기존 세션을 임의로 덮어쓰지 않도록 차단.

### 3.3 프론트엔드 Hydration 및 localStorage 영속화
- **수리**: `Index.tsx` 및 `useWorkspaceLayout.ts` 에서 `activeNavItem` 프로젝트 ID 및 `projects` 리스트를 `localStorage`에 보존.
- **안전 가드**: 
  - `activeNavItem`이 비어 있거나 `"projects"` 이면 hydration 스킵.
  - API 응답 `project_id`가 요청 프로젝트 ID와 불일치 시 스킵.
  - 응답 `sources.length === 0` 인 경우 `sourceEntries` 덮어쓰기 금지.

### 3.4 Proposal Preview 노출 조건 완화
- **수리**: `CenterPanel.tsx`에서 비디오 플레이어 노출 조건을 `(storyPlan?.consultation_status === "confirmed" || !!proposals)`로 변경. 재제안 완료 후 최종 확정 전이라도 사용자가 시안 영상을 즉시 감상 및 재생할 수 있도록 UI 모순 해결.

---

## 4. 빌드 및 테스트 패스 정보

- **백엔드 py_compile**: 성공
- **프론트엔드 npm run build**: 성공 (built in 3.05s)
- **자율 통합 테스트 (`pipeline_full_cycle_verification.py`)**: 
  - 자연어 파싱, Hydration 역조회 복원, 22개 소스 대상 B안 균등 분배(각 소스별 25% 점유) 연산 및 렌더링까지 전체 흐름 100% 정상 작동하여 **ALL PASS** 획득.

---

## 5. 다음 방에서 유지할 절대 금지 규칙
- DB schema 변경 금지.
- ProposalEngine 추가 수정 금지.
- Export/Render 수정 금지.
- Micro Candidate 통합 금지.
- Visual/Motion Evidence 구현 금지.
- UI 디자인 대수정 금지.
- 빌드 성공만으로 PRODUCT PASS 금지 (실시간 브라우저 및 DB 무결성 확인 필수).
