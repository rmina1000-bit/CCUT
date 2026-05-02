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
| STEP 10-I.5.2 | Fast Path Semantic Display Correction | PASS |
| STEP 10-I.5.3 | Polling Guard + Text-first Path | PASS |
| STEP 10-I.7 | Extract useAnalysisPipeline | PASS |
| STEP 10-I.8 | Fragment Map Masking | PASS |
| STEP 10-J | Free Form UI Implementation | PASS |
| STEP 10-I.5.4 | Fixed 30s investigation | DONE |
| STEP 10-I.5.5 | Semantic Source UI Fix | PASS |
| STEP 10-I.5.6 | React Router Future Warning Fix | PASS |
| STEP 10-I.5.7 | Remove Nested Button DOM Warning | PASS |
| STEP 10-I.5.8 | Quiet Polling Logs | PASS |
| STEP 10-I.5.9 | Separate Semantic Success from Proposal Failure | PASS |
| STEP 10-I.5.10 | Backend Semantic Boundary Fix | PASS |
| STEP 10-I.5.11 | Proposal 500 Trace & Schema Validation | DONE |
| STEP 10-I.5.18 | SOURCE_REUSED Registry Restoration | DONE |
| STEP 10-I.5.19 | Proposal Duration None Crash Fix | DONE |
| STEP 10-I.5.20 | Proposal TargetLength None Crash Fix | DONE |
| STEP 10-I.5.21 | Stabilization Evidence for Codex Audit | DONE |










## CURRENT 🔄

> [!IMPORTANT]
> STEP 10-I.5 파이프라인 안정화 완료. 
> 1. 백엔드 재시작 및 소스 재사용 시 상태 복구(Registry Restoration) 완비.
> 2. Proposal Engine의 데이터 누락(duration, target_length)에 대한 방어 로직 강화.
> 3. Codex 감사를 위한 런타임 증거 확보 및 보고서 생성 완료 (STEP 10-I.5.21).










## NEXT 📋

  - STEP 10-I.5.12 Deterministic Semantic Split (Remove Random)
  - STEP 10-I.5.13 Frontend resolved_aliases mapping Fix
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
