# CCUT 1.0.4 진행상황 및 완성 로드맵

branch: ccut-1.0.4-step9  
최종 갱신: 2026-06-13  
HEAD: 1c3793b

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

## 대기 (PENDING)

- ENFORCE 2종 활성화 (dry-run 로그 검토 후 결정)
- 단계6 — continuity 최소 구현 (Jaccard 토큰 유사도)
- 단계7 — static UI 배지 (forced_time_split 표시)
- fragments 테이블 오염 정리 (SF_/_copy_ 혼입 — 감사 선행 필수)
- A제안 첫 조각 멈춤 (seek 위반 6곳, backend mp4 통합 필요)
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
