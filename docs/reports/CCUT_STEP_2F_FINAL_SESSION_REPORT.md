# CCUT1.0.4 STEP 2-F 통합 수리 최종 정리 보고서

작성일: 2026-05-25  
대상 브랜치: `ccut-1.0.4-step9`  
최종 커밋 HEAD: `8190133ec63934076aa17cb295caf1eb03d6a0ed`  
핵심 키워드: Natural Language Intent, Balanced Sources, SourceEntries Hydration, Proposal Preview Visibility

---

## 1. 오늘 작업의 핵심 결론

오늘의 문제는 단일 ProposalEngine 버그가 아니었다.
최종 원인은 다음 4개 파이프라인 단절의 복합 문제였다.

```text
자연어 인지
→ user_intent/coverage 구조화
→ /proposals/project payload source_ids 전달
→ sourceEntries 새로고침 복원
→ ProposalEngine balanced_sources 실행
→ A/B preview 노출
```

즉, “여러 영상 골고루”가 안 되는 문제는 다음의 종단간 Data Supply Chain 문제였다.

```text
LLM이 의도를 담을 coverage 필드 부족
+ handleConsultation 입력 경로 미연결
+ 브라우저 sourceEntries가 3개만 유지
+ backend는 22개가 아니라 3개만 받음
+ proposal preview가 confirmed 상태에서만 보임
```

이 흐름 전체를 통합 수리하여 공급망을 성공적으로 복원했다.

---

## 2. 오늘 완료/확인한 주요 작업

### 2.1 R3-R2: handleConsultation → /proposals/project 연결

커밋:
```text
c6e00bd565187e5b8aa67d3e41286a7213e07cc7
fix: connect consultation intent to project proposals
```

핵심 내용:
- 실제 채팅창/칩 입력 경로가 `handleReproposal`이 아니라 `handleConsultation`임을 확인.
- `shouldConfirm=false`인 자연어/칩 지시에서 `/proposals/project` 호출.
- `shouldConfirm=true`인 “이대로 제안해줘”는 기존 proposal 표시만 유지.
- A/B proposals 누락 시 기존 상태 유지 가드 추가.
- `setSelectedProposalId(null)`, `setCommittedProposalId(null)`, `setProposals(generatedProposals)` 순서 보장.

---

### 2.2 R3-R3: Consultation Runtime Branch Audit

브라우저/콘솔/네트워크 기준 5개 입력 경로 감사.

결과:
| 입력 | shouldConfirm | /proposals/project | 판정 |
|---|---:|---:|---|
| 사람 중심으로 다시 제안해줘 | false | 호출 | PASS |
| 칩: 사람 중심으로 | false | 호출 | PASS |
| 칩: 여러 영상 골고루 | false | 호출 | PASS |
| 이대로 제안해줘 | true | 미호출 | PASS |
| 더 빠르게 편집해줘 | false | 호출 | PASS |

---

### 2.3 R4: ProposalEngine balanced_sources threshold 완화

커밋:
```text
659ed7c7150858316282cda64505b7766b0e01b4
fix: relax balanced source threshold for project proposals
```

핵심 수정:
- `main.py` 내 `post_generate_project_proposals`에서 `resolved_story_template["user_intent"] = user_intent`로 intent 명시 전달.
- `proposal_engine.py` 내 `user_intent.coverage == "balanced_sources"` 또는 fallback 키워드 매칭 시 `threshold_used=0.05`.
- 일반 요청은 기존 `0.1` 유지.
- B안 생성 시 source별 best candidate 1개 선점 및 round-robin 추가를 통한 소스 균등 선별 알고리즘 구현.
- 필수 로그 3종 추가 (`[PROPOSAL_BALANCED_SOURCES_INPUT/BEFORE/AFTER]`).

---

## 3. 결정적 전환점: 브라우저 payload source_ids 3개 문제

R4 backend는 22개 source를 받으면 동작했으나, 실제 브라우저는 `/proposals/project`에 3개만 전송하는 현상이 발견됨.

확정 원인:
- `Index.tsx`의 `sourceEntries`가 현재 세션 메모리에만 존재하여 새로고침/재진입 시 DB의 기존 22개 source가 복원(Hydration)되지 않음.

---

## 4. 통합 수리 완료 및 브라우저 체감 확인 (커밋 HEAD: 8190133)

사용자 승인 하에 다음 3대 파이프라인 수리를 진행하여 커밋 및 원격 푸시를 완료했다.

### 4.1 LLM Coverage Schema 확장
- **수정 파일**: `narrative_provider_contract.py`, `narrative_provider_adapter.py`
- **의도**: "골고루", "여러 영상", "균형" 같은 자연어를 `coverage: "balanced_sources"`로 구조화하여 LLM이 정확히 인지하도록 스키마 및 계약 규격 확장.

### 4.2 Project Source 역조회 API
- **수정 파일**: `ccut_backend/main.py`
- **내용**: `GET /proposals/project/{project_id}/sources` API를 신설하여 `proposals` 테이블의 `source_id = project_id` 매핑 관계 및 sequence JSON을 역추적해 프로젝트에 속한 전체 22개 소스 ID 목록 및 fragments를 복원.
- **보완**: 안전을 위해 DB 전체 sources fallback은 제거하고, 제안 정보를 찾지 못하면 `NO_PROPOSALS_FOUND` 에러(sources: [])를 안전하게 반환하도록 예외 가드 구현.

### 4.3 Frontend sourceEntries Hydration
- **수정 파일**: `Index.tsx`, `videoService.ts`, `useWorkspaceLayout.ts`
- **내용**: 
  - `projectId` 및 `projects` 리스트를 `localStorage`에 영속화.
  - 마운트 시 `activeNavItem` 프로젝트 ID를 기반으로 백엔드 API를 찔러 `sourceEntries` 복원(Hydration) 처리.
  - localStorage projectId guard, project_id mismatch guard, empty sources overwrite guard를 이중화하여 기존 세션이 빈 배열로 덮어쓰이지 않도록 방지.

### 4.4 Proposal Preview 노출 조건 완화
- **수정 파일**: `CenterPanel.tsx`
- **내용**: 비디오 플레이어 그리드 노출 조건을 `(storyPlan?.consultation_status === "confirmed" || !!proposals)`로 완화하여 최종 확정 전이라도 사용자가 시안 비디오 플레이어를 통해 완성된 영상을 볼 수 있도록 모순 수정.

---

## 5. 최종 검증 결과 (ALL PASS)

1. **py_compile**: 에러 없이 정상 패스.
2. **npm run build**: 프로덕션 빌드 성공 완료.
3. **통합 테스트 스크립트 실행 (`pipeline_full_cycle_verification.py`)**:
   - 자연어 파싱(`coverage: "balanced_sources"`), Hydration DB 역추적 복구, 22개 소스 대상 B안 균등 분배 연산(각 소스별 25% 고른 매핑)까지 100% 정상 작동하여 **ALL PASS** 획득.
4. **실제 브라우저 화면 검증**: 
   - 새로고침 시 22개 소스가 정상 복구되고, 자연어 재제안 시 A/B 시안 비디오 플레이어가 즉시 노출되며 정상 작동함을 사용자와 확인 완료.
