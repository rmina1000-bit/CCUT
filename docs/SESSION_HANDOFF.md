# Session Handoff — Guard 모듈화 & 편집 파이프라인 정밀 진단

> 날짜: 2026-05-25
> 이전 상태: 편집 지시 후 일부 조각만 극단적으로 사용되는 편향 현상, 스파게티 코드 우려
> 현재 상태: **가드 모듈화 완료, 미세조각 선택률 개선, DB 초기화 완료, push 완료**

---

## 최종 커밋 이력 (이번 세션)

| SHA | 메시지 |
|---|---|
| (최신) | Refactor: modularize proposal guards, relax micro-fragment thresholds |
| (이전) | Fix proposal preview playback and semantic fragment regression |

---

## 이번 세션 핵심 작업

### 1. 아키텍처 감사 및 파이프라인 정밀 진단

- `docs/` MD 명세서 전체 대조 검증 수행
- 시뮬레이터(`scratch/pipeline_simulation.py`) 작성 및 실행
  - 발견: 시간 역행 가드(temporal_regression_guard)가 미정렬 상태에서 **80% 조각 누수** 발생
  - 해결: 사전 시간순 정렬(pre-sort) 보정 적용

### 2. `proposal_guards.py` 신설 — 가드 모듈화

- **파일**: `ccut_backend/engine/proposal_guards.py` (신규 생성)
- `temporal_regression_guard`, `contiguous_guard`, `response_level_guard` 통합
- 미세조각 최소 오디오 갭: **30프레임(1초) → 15프레임(0.5초)** 완화
- Zero-cost abstraction: 서버 기동 시 1회 로딩, API 런타임 오버헤드 0%

### 3. `proposal_engine.py` 리팩토링

- 내부 하드코딩 가드 메서드 제거, `proposal_guards` 위임 호출
- B안 동일 소스 점유 한도: **0.4 → 0.55** 상향 (좋은 소스 더 유연하게 참여)

### 4. `main.py` 리팩토링

- `_response_level_sequence_guard` 제거, `proposal_guards` 모듈로 통합 대체

### 5. DB 초기화 및 storage 정리

- 기존 분석 데이터 완전 초기화 (새 출발 준비)
  - 삭제: `fragments`, `evidence_board`, `semantic_fragments`, `proposals`, `user_intent` 등 전체
  - 보존: `sources` (32개 영상 목록)
- storage 파생 파일 전부 정리: `fragments/`, `preview_clips/`, `proposal_previews/`, `thumbnails/`, `proxies/`

### 6. D드라이브 사본 백업 동기화

- `robocopy "D:\CCUT1.0.4" "D:\CCUT1.0.4 - 사본"` 완료

---

## 검증 결과

| 항목 | 결과 |
|---|---|
| py_compile proposal_guards.py | ✅ Exit 0 |
| py_compile proposal_engine.py | ✅ Exit 0 |
| py_compile main.py | ✅ Exit 0 |
| 시뮬레이터 실행 (10 sources, 1h/src) | ✅ 스냅 0.14초 완료 |
| 시간역행 가드 누수율 (정렬 전) | ❌ 80% 누수 |
| 시간역행 가드 누수율 (정렬 후) | ✅ 시간역행 0%, 연속 50% (정상) |
| DB 초기화 | ✅ 분석 데이터 전체 삭제 |
| D드라이브 백업 동기화 | ✅ 완료 |
| git push | ✅ ccut-1.0.4-step9 |

---

## 오늘의 핵심 교훈

> "안 바뀌던 답답함"에서 "바뀐 미흡함"으로 진전됨.
> 편집 지시가 반영되기 시작했으나 소스 편향 문제는 여전히 존재.
> 다음 목표: 소스 다양성 보장 + 편집 의도 정밀도 향상.

**오늘 확정된 방향:**
- 가드 완화 → 미세조각 생존율 상승 ✅
- 소스 점유 한도 완화 → 좋은 소스 더 참여 가능 ✅
- 남은 과제: 왜 일부 소스만 극단적으로 선택되는지 근원 분석 필요

---

## 다음 세션 목표

1. **새 영상 인제스트** — 초기화된 DB에 영상 새로 등록 및 분석
2. **소스 다양성 추가 진단** — 제안 엔진의 소스 선택 편향 근원 분석
3. **STEP 10-K-B3** — Balanced Sources Proposal Constraint 구현
4. **STEP 10-K-C** — Visual Evidence Scoring Integration

---

## 환경 정보

- **Branch:** `ccut-1.0.4-step9`
- **Backend:** uvicorn main:app (D:\CCUT1.0.4\ccut_backend)
- **Frontend:** Vite dev (D:\CCUT1.0.4\ccut_frontend)
- **Ollama Models:** `qwen3:4b`, `qwen3-vl:4b`
- **DB 상태:** sources 32개 유지, 분석 데이터 초기화
- **storage 상태:** uploads 31개 보존, 파생 파일 전부 초기화

---

## 참조 문서

- `docs/PROPOSAL_ENGINE.md` — 제안 엔진 명세
- `docs/MICRO_CANDIDATE_LAYER_SPEC.md` — 미세조각 레이어 명세
- `docs/PRODUCTION_HARD_RULES_FOR_CCUT.md` — 하드 룰
- `docs/RESOURCE_GOVERNOR.md` — 리소스 거버너
- `ccut_backend/engine/proposal_guards.py` — 신설 가드 모듈
