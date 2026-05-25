# Antigravity용 최종 검수/마무리 작업지시서 (수리 및 커밋 완료본)

## 1. 개요 및 최종 커밋 정보

- **최종 커밋 HEAD**: `8190133ec63934076aa17cb295caf1eb03d6a0ed` (ccut-1.0.4-step9 원격 브랜치 푸시 완료)
- **목표**: 자연어 의도 유실 및 프로젝트 소스 데이터 단절 현상(Hydration)에 대한 통합 수리를 완료하고, 안전하게 저장소에 반영함.

---

## 2. 통합 수리 주요 내역

```text
1. LLM coverage schema 확장
   - narrative_provider_contract.py, narrative_provider_adapter.py 내 Ollama 스키마에 coverage 필드 추가.
2. project source 역조회 API 구축
   - main.py 내 GET /proposals/project/{project_id}/sources API 구현.
   - 위험한 DB 전체 sources fallback 제거 및 NO_PROPOSALS_FOUND 예외 가드 추가.
3. frontend sourceEntries hydration 구현
   - Index.tsx 내 mount 시 hydration useEffect 구현.
   - localStorage projectId guard, project_id mismatch guard, empty sources overwrite guard를 통한 이중 안전망 구축.
4. CenterPanel A/B proposal preview 노출 조건 완화
   - proposals 존재 시 A/B preview grid가 즉시 표시되도록 (StoryPlan confirmed 전이라도 재생 가능하도록) 모순 해결.
```

---

## 3. 검증 성공 증거

### 3.1 백엔드 컴파일 검증 (`py_compile`)
- 에러 및 경고 없이 완벽히 컴파일 통과.
  ```powershell
  python -m py_compile ccut_backend/main.py ccut_backend/ai/boundary/narrative_provider_adapter.py ccut_backend/ai/boundary/narrative_provider_contract.py
  ```

### 3.2 프론트엔드 빌드 검증 (`npm run build`)
- UI 및 컴포넌트 유기적 빌드 성공.
  ```text
  vite v5.4.21 building for production...
  ✓ 1700 modules transformed.
  dist/assets/index-C21Zf7oZ.css   78.19 kB │ gzip:  13.59 kB
  dist/assets/index-cloz75Ku.js   449.02 kB │ gzip: 141.32 kB
  ✓ built in 3.05s
  ```

### 3.3 Full-Cycle Sandbox 통합 Verification (`pipeline_full_cycle_verification.py`)
- **TEST CASE 1 (자연어 파싱)**: PASS (LLM이 `coverage: "balanced_sources"` 자동 인지)
- **TEST CASE 2 (Hydration 및 Fallback 제거)**: PASS (`NO_PROPOSALS_FOUND` 예외 처리 및 가상 적재 데이터 역추적 복원 성공)
- **TEST CASE 3 (balanced_sources 제안 생성)**: PASS (B안 4개 클립에 대해 4개 고유 소스가 25%씩 1:1:1:1로 고르게 배분됨을 수학적 실측 완료)

---

## 4. 향후 절대 금지 규칙
- DB schema 변경 금지.
- ProposalEngine 추가 수정 금지.
- Export/Render 수정 금지.
- Micro Candidate 통합 금지.
- Visual/Motion Evidence 구현 금지.
- UI 디자인 대수정 금지.
