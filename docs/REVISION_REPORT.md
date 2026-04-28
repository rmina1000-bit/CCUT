# CCUT Revision Report

## Latest Baseline

- **Branch:** `ccut-1.0.4-step9`
- **SHA:** `e76bbe725f57410c7e92ba2be00eba852bf2d055`
- **Date:** 2026-04-28

---

## Completed Steps

| STEP | 내용 | 상태 |
|------|------|------|
| STEP 0 | 기준선 확보 | PASS |
| STEP 1 | Proxy / Segment / Fingerprint | PASS |
| STEP 2 | Evidence Board | PASS |
| STEP 3 | Quick Scan + Hypothesis | PASS |
| STEP 4 | Semantic Fragment | PASS |
| STEP 5 | User Intent 최종 반영 | PASS |
| STEP 6 | Proposal Engine | PASS |
| STEP 7 | ExportInput 생성 | PASS |
| STEP 8 | Render Engine / Export 실행 | PASS |
| STEP 9 | UI 최소연동 / 통합 확인 | PASS |
| STEP 10-A | Structure Reinforcement Documentation | PASS |
| STEP 10-B | Virtual Fragment Factory Simulation v0 | PASS |
| STEP 10-C | Factory Simulation 구조 보정 | PASS |
| STEP 10-D | Resource Governor Simulation v0 | PASS |





---

## Important Fixes (2026-04-28)

### GitHub 위생 정리
- 임시 파일 13종 삭제 (`check_db.py`, `fix_mojibake*.py`, `_archive_backend_20260420/`, `ccut_backend/logs/hook_distribution/` 300+ JSON 등)
- 정리 스크립트 `clean_step89.ps1` 삭제
- `.gitignore` 보강 (`*.log`, `*.bak`, `**/logs/` 등)

### 코드 수정
- **Index.tsx**: Mojibake 한글 문자열 3종 정상화
  - `"백엔드 분석 기반 추천 편집안입니다."`
  - `"분석 중 오류가 발생했습니다. 콘솔을 확인해 주세요."`
  - `"[Reproposal] sourceFragments가 없어 재제안을 건너뜁니다."`
- **main.py**: `D:/test_video.mp4` 하드코딩 제거 → `video_path: str = ""`
- **CenterPanel.tsx**: `http://localhost:8000` 하드코딩 → `videoService.API_BASE_URL`

---

## Latest Revision (2026-04-29)

- **Common Core v1 문서 추가**
- **Virtual Fragment Factory 문서 추가**
- **Web AI Contract v0.1 문서 추가**
- **External Proposal Service 방향 문서 추가**
- **PROJECT_NAVIGATION / EXECUTION_PLAN / TASK_BOARD / HANDOFF / SESSION_HANDOFF 갱신**
- **기준 SHA 일괄 정정 (`ddbd6e2779e51bf9e45b9d832830ee14b3716340`)**

---

## Latest Revision (2026-04-29 01:00)

- **STEP 10-B Virtual Fragment Factory Simulation v0 완료**
- **시뮬레이션 문서 및 스크립트 추가**
- **factory_result.json / factory_summary.json 생성 및 검증 완료**
- **기존 핵심 파이프라인(Render/Export) 영향 없음 확인**

---

## Latest Revision (2026-04-29 01:10)

- **STEP 10-C Factory Simulation 구조 보정 완료**
- **Source/Room/Task/Worker/Evidence 최소 계약 필드 확정 및 반영**
- **시뮬레이션 스크립트 내 ID 연결성 및 Time Range 검증 로직 추가**
- **factory_summary.json 내 상세 검증 필드(PASS/FAIL) 추가**

---

## Latest Revision (2026-04-29 01:20)

- **STEP 10-D Resource Governor Simulation v0 완료**
- **Resource Policy v0 정의 및 Mock Scenario(NORMAL/PRESSURE/OVERLOAD) 적용**
- **Governor Decision 로직 및 로그 생성 시뮬레이션 완료**
- **OVERLOAD 상태에서 THROTTLE/DELAY 발생 확인 및 검증 PASS**





---

## Validation Summary

| 항목 | 결과 |
|------|------|
| RenderEngine 구현 (`render_from_export_input`) | PASS |
| UI 통합 (export-input → render → render-result) | PASS |
| GitHub 위생 | PASS |
| 로컬 ↔ GitHub 동기화 | PASS |
| Working tree | Clean |

---

## Open Issues

- Resource Governor 미연동 (향후 STEP 10)
- PBE(Precision Boundary Editor) 비활성화 상태 유지 중
- 병렬 렌더링 미구현 (설계 단계)

---

## Next

- STEP 10 최종 안정화 / 회귀 테스트
- 문서 구조 고정 및 방이전 자동화 체계 운영 시작
