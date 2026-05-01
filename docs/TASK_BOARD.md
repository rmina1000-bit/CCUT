# CCUT Task Board

## DONE ✅

| STEP | 내용 |
|------|------|
| STEP 0 | 기준선 확보 |
| STEP 1 | Proxy / Segment / Fingerprint |
| STEP 2 | Evidence Board |
| STEP 3 | Quick Scan + Hypothesis |
| STEP 4 | Semantic Fragment |
| STEP 5 | User Intent 최종 반영 |
| STEP 6 | Proposal Engine |
| STEP 7 | ExportInput 생성 |
| STEP 8 | Render Engine / Export 실행 |
| STEP 9 | UI 최소연동 / 통합 확인 |
| -      | GitHub 위생 정리 + 로컬 동기화 |
| -      | 문서 구조 고정 + 방이전 자동화 체계 구축 |
| STEP 10-A | Structure Reinforcement Documentation |
| STEP 10-B | Virtual Fragment Factory Simulation v0 |
| STEP 10-C | Factory Simulation 구조 보정 |
| STEP 10-D | Resource Governor Simulation v0 |
| STEP 10-E1 | Cognitive Signal Matrix Micro Simulation |
| STEP 10-E1.5 | Cognitive Signal Matrix 공식 기준 문서화 |
| STEP 10-F | Video-use 품질규칙 CCUT 흡수 설계 |
| STEP 10-G | 무료 사용자 편집 폼 설계 |
| STEP 10-G.1 | Form → Edit Instruction Micro Simulation |
| STEP 10-H | 무료버전 MVP 범위 최종 정의 |
| STEP 10-I | 무료 폼 UI 최소 구현 설계 | PASS |
| STEP 10-I.2 | Proposal Resolver + Physical EDL Stabilization | PASS |
| STEP 10-I.3 | Fragment Count Simplification & Fast Path | PASS |
| STEP 10-I.4 | Index Decomposition Plan | PASS |
| STEP 10-I.5 | Extract Layout & Proposal hooks | PASS |
| STEP 10-I.5.1 | Mojibake Log Cleanup | PASS |










## CURRENT 🔄

> [!IMPORTANT]
> STEP 10-I.5.1 완료. `useProposalState` 내부의 깨진 한글 로그를 영문으로 정규화했습니다.
> 이제 개발자 콘솔에서 인코딩 문제 없이 로그를 확인할 수 있습니다.










## NEXT 📋

  - STEP 10-I.5 Hook Extraction (useWorkspaceLayout, useProposalState)
  - STEP 10-I.6 Hook Extraction (useFragmentWorkspace, useAnalysisPipeline)
  - STEP 10-J 무료 폼 UI 실제 최소 구현 및 사용자 여정 확립

  - STEP 10-F External Proposal Service Simulation v0 설계
 - STEP 10-G Factory Simulation 보정 (필요 시)





## HOLD ⏸

  - Resource Governor 연동
- 병렬 Worker 렌더링
- Cache 고급 최적화
- PBE(Precision Boundary Editor) 재연결
- SNS 업로드 연동

## DO NOT 🚫

- 실제 Web AI API 호출 구현
- Resource Governor 본구현
- Render/ExportInput/UI 파이프라인 변경

## 운영 원칙


```text
새 인계 파일을 계속 만들지 않는다.
docs/SESSION_HANDOFF.md를 업데이트한다.
작업 기록은 docs/REVISION_REPORT.md에 누적한다.
현재 작업상태는 docs/TASK_BOARD.md에 반영한다.
GitHub push와 SHA 보고까지 완료해야 작업 완료다.
```
