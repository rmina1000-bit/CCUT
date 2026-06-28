# CCUT 1.0.4 진행상황 및 완성 로드맵

branch: ccut-1.0.4-step9  
최종 갱신: 2026-06-14  
직전 작업: 영상 6중 버그 해결 + 아카이브 전면 + 조각 검색 토대 (보고서: docs/reports/SESSION_REPORT_2026-06-14_video_archive.md)

---

## 완료 (DONE)

### 조각화 재설계 트랙 (2026-06-13 국장 화면 PRODUCT PASS)

| 커밋 | 단계 | 내용 | PASS 기준 |
|------|------|------|-----------|
| e1ef25e | 단계1 | 소스 프로파일 게이트 pre/profile_source | SRC_12C414A7 static, SRC_052AB3BD pending |
| c5b2983 | 단계2 | 발화 경계 스냅 refine_boundaries_to_words | 합성 케이스 A/B/D + SRC_B1A26714 9/15 일치 |
| f76996b | 단계3 | 경계붕괴 방어(worker 필터) + 자식 재분류(clone 제거) | SRC_B1A26714 27개 다양 분포 |
| 0e71af8 | 단계3.5/3.6/3.6.1 | 과분쇄 댐퍼 + 기근 레스큐(저임계→모션→VF) + 균등분할 | SRC_8E415949 14.8s 격자 소멸 |
| 1c3793b | M1-M2 | 모션 변곡점 경계 (curve, D1 raw-snap, B2 배선, __file__ proxy) | SRC_8E415949 3~17.5s 가변 분포 확인 |

**영상 3부류 체계 (확립):**
- ① 발화 영상: Whisper 텍스트 경계 (최상)
- ② 컷 있는 영상: scene 변곡점 경계 (양호)
- ③ 원테이크 영상: 모션 변곡점 → forced_time_split 정직 표식

**환경변수 게이트 (현재 모두 dry-run):**
- CCUT_PROFILE_ENFORCE=0 (무음 소스 ASR 스킵 — 관찰 중)
- CCUT_SNAP_ENFORCE=0 (발화 경계 스냅 적용 — 관찰 중)

**운영 DB 현황 (2026-06-13 10:47 재생성):**

| source_id | 조각 수 | 길이 범위 | 비고 |
|-----------|---------|-----------|------|
| SRC_8E415949 | 14 | 3.0~17.5s | 원테이크, 모션 변곡점 |
| SRC_052AB3BD | 7 | 3.5~15.0s | 발화, 모션 변곡점 |
| SRC_B85D3189 | 6 | 5.0~13.25s | 모션 변곡점 |
| SRC_B1A26714 | 27 | 5.2~15.4s | 컷+발화, scene 경계 |

### 휴지통 화면 + 앱 시작 화면 정상화 (2026-06-28, ChatGPT PRODUCT PASS)

브랜치 ccut-1.0.4-step9 / HEAD de3de22 (push 완료)

**(A) 윈도우식 전용 휴지통 — 커밋 276774c**
- videoService.ts: listTrash() / purgeProject() 신규 (기존 백엔드 trash/purge API 연결)
- TrashPanel.tsx 신규(204줄): 목록·복원·영구삭제·휴지통비우기·빈상태·확인모달
- LeftNav.tsx: 네비 "휴지통" 항목 / Index.tsx: 분기+레이아웃 2곳
- 1차 ArchivePanel 재활용안은 아카이브와 동일하여 폐기·원복(cmp IDENTICAL) 후 전용 페이지로 재설계
- 검증: 삭제 프로젝트 6건 목록, 영구삭제 시 6→3건, 복원·비우기 정상

**(B) 앱 시작 첫 화면 정상화 — 커밋 de3de22**
- 원인: useWorkspaceLayout.ts가 activeNavItem(메뉴값까지)을 localStorage에 복원
- 수정: proj_ 접두사(작업중 프로젝트)만 복원, 그 외는 새 프로젝트 메인("projects")
- 검증: 휴지통/아카이브/SNS/내계정/설정 5개 메뉴 전부 재시작 시 메인 복귀

ChatGPT 판정: PRODUCT PASS (둘 다)
- 잔여(P1, 다음 안정화): 휴지통 비우기 다건 purge 부분실패 처리 보강
- 다음 메인(검수 권고): ASR 20분 측정 복귀
- 교훈 확정: 큰 파일 Edit 금지(in-place), CRLF는 newline="" 보존, 백엔드 변경 후 재시작+StartTime 확인

---

## 진행 중 (IN PROGRESS)

### 모션 파라미터 캘리브레이션
- 기본값: fps_sample=2.0 / smooth_window=4 / k_smooth=1.0 / k_raw=0.5 / min_gap_sec=3.0
- D2(raw 동반 조건) 실데이터 기각 사례 미실증 → 모니터링
- B1A26714 ±2.0s 일치율 9/15 (M-0 기준 6/15 → 개선)

### 단계4 — role 단일화
- semantic_engine.py의 소문자 role 레거시 경로 제거
- ai_engine.py classify_role 단일 사용

### 단계5 — edit_value 재설계
- 조각별 신호 기반 재계산 (duration + hook_score + boundary_confidence)

---

## 아카이브 UX 트랙 (2026-06-14)

> 설계 문서: `docs/ARCHIVE_DESIGN.md` · 작업 보고: `docs/reports/SESSION_REPORT_2026-06-14_video_archive.md`

| 항목 | 상태 |
|------|------|
| 프로젝트 관리: source_count 필터 + 원본 수 + 드릴다운(원본/제안/내보내기 인라인 재생) | ✅ 완료 |
| AI 제안 이력: program 귀속 배지 + 즉석 렌더 [재생] + [열기] 복귀 + 삭제안내 | ✅ 완료 |
| 원본 카드: 해시 + 사용 이력 펼침 + 이름변경 + 재생 + 삭제(원본만/전체) | ✅ 완료 |
| SNS/아카이브 이름 동기화 + last_updated_at + 캐시버스터 | ✅ 완료 |
| soft-delete (30일 휴지통 + 강한 경고 + 복원/완전삭제) | ✅ 완료 |
| 원본 클립 레벨 추적 (어느 구간이 사용됐는지) | 🟢 FUTURE |

---

## 조각 검색 트랙 (2026-06-14 신설) — CCUT의 C 이념

> 채팅 자연어 조각 검색. 큐원VL+임베딩. 메모리 `ccut_fragment_search_feature` 참조.

| 항목 | 상태 |
|------|------|
| fragment_index 테이블 + FTS5 + 임베딩/VL/검색/채팅 엔진 5종 | ✅ 완료 |
| 채팅 검색 API + 결과 카드 (cross-lingual 한↔영) | ✅ 완료 |
| **단계 6: 전체 조각 인덱싱** (현재 28개 → 전체, ~1시간) | 🔴 다음 방 |
| **단계 5: 제안 고급화** (curated 가중치 → 편집 품질) | 🔴 다음 방 |

---

## 영상 파이프라인 (2026-06-14 — 6중 버그 해결 완료)

> 함정 메모리 `ccut_video_pipeline_gotchas` 참조. concat 재인코딩/faststart/keyframe/캐시버스터.

| 항목 | 상태 |
|------|------|
| faststart + 이중 storage 경로 + fps + keyframe + 캐시 + concat SPS/PPS | ✅ 6중 전부 해결 |
| 기존 export 47개 일괄 재렌더 (단일 stream, 1/4 크기) | ✅ 완료 |
| A제안 첫 조각 멈춤 | ✅ 해결 (concat copy → 재인코딩이 근본) |

---

## 대기 (PENDING)

- ENFORCE 2종 활성화 (dry-run 로그 검토 후 결정)
- 단계6 — continuity 최소 구현 (Jaccard 토큰 유사도)
- 단계7 — static UI 배지 (forced_time_split 표시)
- fragments 테이블 오염 정리 (SF_/_copy_ 혼입 — 감사 선행 필수)
- export_input.clips start/end=null 비정상 데이터 (생성 단계 검증 필요)
- PBE 잔여 로드맵 (아래)

---

## PBE 트랙

**미커밋 stash (pop 전 반드시 확인):**

| stash | 내용 | 주의 |
|-------|------|------|
| stash@{0} | 싱글-left 수정 + TRACE 5개 (2026-06-01) | PBE 재개 1번 작업 |
| stash@{1} | R14R15_pbe_frontend_wip (2026-05-30) | |
| stash@{2} | PBE 2450줄 Temp (2026-05-28) | **pop 금지 — 감사 후 처분** |

**PBE 재개 순서:**
1. stash@{0} apply → TRACE 5개 제거 → 커밋
2. PBE-D3 경계클릭 fragment ID 수정
3. fps 30 하드코딩 통일 (Index.tsx L1426/1444 등 5곳)
4. ID regex 중복 제거 (FragmentTile:42, pbeBoundaryOps:41, fragmentIdentity:44)
5. dead code 제거 (applyBoundaryAdjustments 0 call sites)
6. S|S 중간 경계 역전 확인

---

## 격리 branch

- audit/step20-viewer-addiction-unapproved (488346b) — 변동 없음, 격리 유지

---

## 주요 함정 기록

| 항목 | 내용 |
|------|------|
| 안티2 허위보고 | 052AB3BD "보존" 주장 vs 실변화 ([20,20,20.8]→[10.1×6]) |
| generate() 검증 | save_semantic_fragments 무력화 필수 |
| fragments 테이블 | SF_/_copy_ 혼입 — VF 접두사 필터 없이 읽기 금지 |
| 구/신코드 혼재 | created_at 확인 습관 (SRC_F4D0994F = 5/29 구코드 산물) |
| M-0 가설 기각 | t=97/103.5/145 "가짜 피크" → 실제는 샘플 시각 어긋남, D1이 해소 |
| Claude Code 해석 오류 | 원시 숫자는 정확, 원인 귀속 오류 사례 있음 — 산문 해석 검증 필요 |
| CWD 의존 경로 | bat 실행 시 storage 경로 깨짐 → __file__ 앵커로 해소 (M-2.2) |

## [완료] 휴지통 화면 + 앱 시작 화면 정상화 (2026-06-28, ChatGPT PRODUCT PASS)
브랜치 ccut-1.0.4-step9 / HEAD de3de22 (push 완료)
(A) 윈도우식 전용 휴지통 — 커밋 276774c
- videoService.ts: listTrash() / purgeProject() 신규 (기존 백엔드 trash/purge API 연결)
- TrashPanel.tsx 신규(204줄): 목록·복원·영구삭제·휴지통비우기·빈상태·확인모달
- LeftNav.tsx: 네비 "휴지통" 항목 / Index.tsx: 분기+레이아웃 2곳
- 1차 ArchivePanel 재활용안은 아카이브와 동일하여 폐기·원복(cmp IDENTICAL) 후 전용 페이지로 재설계
- 검증: 삭제 프로젝트 6건 목록, 영구삭제 시 6→3건, 복원·비우기 정상
(B) 앱 시작 첫 화면 정상화 — 커밋 de3de22
- 원인: useWorkspaceLayout.ts가 activeNavItem(메뉴값까지)을 localStorage에 복원
- 수정: proj_ 접두사(작업중 프로젝트)만 복원, 그 외는 새 프로젝트 메인("projects")
- 검증: 휴지통/아카이브/SNS/내계정/설정 5개 메뉴 전부 재시작 시 메인 복귀
ChatGPT 판정: PRODUCT PASS (둘 다)
잔여(P1, 다음 안정화): 휴지통 비우기 다건 purge 부분실패 처리 보강
다음 메인(검수 권고): ASR 20분 측정 복귀
교훈 확정: 큰 파일 Edit 금지(in-place), CRLF는 newline="" 보존, 백엔드 변경 후 재시작+StartTime 확인
