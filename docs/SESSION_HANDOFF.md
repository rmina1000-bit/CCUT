# CCUT 1.0.4 Session Handoff

## 1. 현재 기준선

- **Branch:** `ccut-1.0.4-step9`
- **SHA:** `e76bbe725f57410c7e92ba2be00eba852bf2d055`
- **Local path:** `D:\CCUT1.0.4`
- **Repo:** `https://github.com/rmina1000-bit/CCUT.git`
- **Last updated:** 2026-04-30

## 2. 완료 단계

- STEP 0 기준선 확보: **PASS**
- STEP 1 Proxy / Segment / Fingerprint: **PASS**
- STEP 2 Evidence Board: **PASS**
- STEP 3 Quick Scan + Hypothesis: **PASS**
- STEP 4 Semantic Fragment: **PASS**
- STEP 5 User Intent 최종 반영: **PASS**
- STEP 6 Proposal Engine: **PASS**
- STEP 7 ExportInput 생성: **PASS**
- STEP 8 Render Engine / Export 실행: **PASS**
- STEP 9 UI 최소연동 / 통합 확인: **PASS**
- STEP 10-A Structure Reinforcement Documentation: **PASS**
- STEP 10-B Virtual Fragment Factory Simulation v0: **PASS**
- STEP 10-C Factory Simulation 구조 보정: **PASS**
- STEP 10-D Resource Governor Simulation v0: **PASS**
- STEP 10-E1 Cognitive Signal Matrix Micro Simulation: **PASS**
- STEP 10-E1.5 Cognitive Signal Matrix 공식 기준 문서화: **PASS**
- STEP 10-F Video-use 품질규칙 CCUT 흡수 설계: **PASS**
- STEP 10-G 무료 사용자 편집 폼 설계: **PASS**
- STEP 10-G.1 Form → Edit Instruction Micro Simulation: **PASS**
- STEP 10-H 무료버전 MVP 범위 최종 정의: **PASS**
- STEP 10-I 무료 폼 UI 최소 구현 설계: **PASS**
- STEP 10-I.2 Proposal Resolver + Physical EDL Stabilization: **PASS**
- STEP 10-I.3 Fragment Count Simplification & Fast Path: **PASS**
- STEP 10-I.4 Index Decomposition Plan: **PASS**
- STEP 10-I.5 Extract Layout & Proposal hooks: **PASS**
- STEP 10-I.5.1 Mojibake Log Cleanup: **PASS**
- STEP 10-I.5.2 Fast Path Semantic Display Correction: **PASS**
- STEP 10-I.5.3 Polling Guard + Text-first Path: **PASS**
- STEP 10-I.7 Extract useAnalysisPipeline: **PASS**
- STEP 10-I.8 Fragment Map Masking: **PASS**
- STEP 10-J Free Form UI Implementation: **PASS**
- STEP 10-I.5.4 Fixed 30s investigation: **DONE**
- STEP 10-I.5.5 Semantic Source UI Fix: **PASS**










## 3. 현재 완성 흐름

```text
영상 업로드
→ Whisper 분석 (background)
→ Signal Trigger 자동 추출 (SignalProcessor)
→ Semantic Fragment 자동 생성 (SemanticFragmentGenerator)
→ Proposal 자동 생성 (ProposalEngine)
→ UI polling 완료
→ Proposal 확정 시 Resolver가 Alias 시간 강제 적용
→ FragmentMap에 3~12초 가변 길이 조각 정상 노출
→ Export/Render 파이프라인
```

## 4. 최신 변경 요약 (2026-05-01)

- **Semantic Source UI Fix (STEP 10-I.5.5):**
  - `Index.tsx`: Semantic 분석 완료 시 `semanticRows`가 존재하면 raw 30s fragment 대신 이를 최우선 소스로 사용하도록 로직 변경.
  - `mapFragments`: `duration` 필드보다 `start/end` 기반의 정밀 계산을 우선하도록 순위 조정.
  - `proposalFragmentResolver.ts`: 시간 범위 추출 로직을 `Index.tsx`와 동일하게 정밀화.
  - 이로써 /proposals 500 발생 시의 fallback proposal도 semantic ID 체계를 유지하게 됨.

- STEP 10-I.6 Hook Extraction (useFragmentWorkspace)
- STEP 11 Phase: External Proposal Service Integration







## 6. 금지사항

```text
- localStorage / PBE 재활성화 금지
- 병렬화 (parallel render) 금지
- 원본 영상 반복 분석 금지
- Evidence 없이 Semantic 생성 금지
- Semantic 없이 Proposal 생성 금지
- Proposal 없이 Export 직접 연결 금지
- main/master 브랜치 push 금지
- 새 SESSION_HANDOFF 파일 생성 금지 (이 파일만 업데이트)
```

## 7. 다음 작업 전 확인 명령

```powershell
git branch --show-current
git rev-parse HEAD
git rev-parse origin/ccut-1.0.4-step9
git status --short
```

기대값:
```
ccut-1.0.4-step9
e76bbe725f57410c7e92ba2be00eba852bf2d055
e76bbe725f57410c7e92ba2be00eba852bf2d055
M ccut_frontend/src/pages/Index.tsx (등 STEP 10-I.2 관련 수정 사항 표시)
```

> [!IMPORTANT]
> STEP 10-I.5.5 완료. Semantic Fragment가 UI 및 Proposal Fallback의 기본 데이터 소스로 확정되었습니다.
> 이제 30.0s 고정 노출 현상이 해결되었으며, 분석 실패 시에도 Semantic 조각 기반의 제안이 유지됩니다.




