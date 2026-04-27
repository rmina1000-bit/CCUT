# STEP 0-1 정확한 상태 보고서

작성: 2026-04-27
검수: 코덱스

## Git 상태

### 커밋 / 태그
- Baseline Commit: `a8ea11c`
- 태그: `v1.0.3-baseline` (`a8ea11c`)
- 태그: `v1.0.3-baseline-complete` (STEP 0-1 정리 완료 시점)

### Working Tree
- Status: clean
- Untracked files: 없음
- Modified files: 없음

### 복구 가능 여부
- `git checkout v1.0.3-baseline` 으로 초기 baseline 시점 복구 가능
- `git checkout v1.0.3-baseline-complete` 으로 STEP 0-1 정리 완료 시점 복구 가능
- `baseline_smoke_test.md` 포함
- `docs/VIDEO_USE_SAFETY_RULE.md` 포함

## 파일 구조

### 생성 및 확인 파일
- `baseline_smoke_test.md` (루트)
- `docs/VIDEO_USE_SAFETY_RULE.md` (docs 폴더)

### 파일 위치
```text
D:\CCUT1.0.4\
├── baseline_smoke_test.md
├── STEP_0_1_정확한_상태보고서.md
├── docs\
│   └── VIDEO_USE_SAFETY_RULE.md
└── ccut_backend\
    └── ccut_app.db
```

## DB 상태

### 테이블 목록 (전체 12개)
1. `decisions` (row: 0)
2. `evidence_board` (row: 2)
3. `export_input` (row: 1)
4. `fragments` (row: 2)
5. `programs` (row: 0)
6. `proposals` (row: 2)
7. `published` (row: 0)
8. `quick_scan` (row: 1)
9. `semantic_fragments` (row: 2)
10. `sources` (row: 2)
11. `subtitles` (row: 0)
12. `user_intent` (row: 1)

### evidence_board 확인
- 테이블 존재: 예
- Row count: 2
- 스키마:
  - `fragment_id`
  - `source_id`
  - `start`
  - `end`
  - `time_offset`
  - `text`
  - `audio_energy`
  - `silence`
  - `scene_change`
  - `motion_score`
  - `keyframe`
  - `speaker`
  - `confidence`
  - `fallback_reason`
  - `worker_sources`
  - `metadata_json`
  - `last_updated`

### evidence_board 샘플
- `VF1_SRC_3BD89C3B` / `SRC_3BD89C3B` / `start=0.0` / `end=30.0` / `confidence=1.0`
- `VF2_SRC_3BD89C3B` / `SRC_3BD89C3B` / `start=29.5` / `end=54.38` / `confidence=1.0`

## 검증 결과

- Git 저장소 초기화 확인
- Baseline 태그 확인
- 파일 위치 정확히 확인
- DB 전체 테이블 목록 확인
- evidence_board 존재 및 row count 확인
- STEP 0-1 정리 완료 시점 태그 확보

## Pass 판정

- STEP 0: 기준선 백업 완료
- STEP 1: 법적 안전선 문서화 완료
