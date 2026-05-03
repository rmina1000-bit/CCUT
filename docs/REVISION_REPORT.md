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
| STEP 10-E1 | Cognitive Signal Matrix Micro Simulation | PASS |
| STEP 10-E1.5 | Cognitive Signal Matrix 공식 기준 문서화 | PASS |
| STEP 10-F | Video-use 품질규칙 CCUT 흡수 설계 | PASS |
| STEP 10-G | 무료 사용자 편집 폼 설계 | PASS || STEP 10-I | 무료 폼 UI 최소 구현 설계 | PASS |
| STEP 10-I.2 | Proposal Resolver + Physical EDL Stabilization | PASS |
| STEP 10-I.3 | Fragment Count Simplification & Fast Path | PASS |

---

## Latest Revision (2026-05-01 13:00)

- **STEP 10-I.2 Proposal Resolver + Physical EDL Stabilization 완료**
- **STEP 10-I.3 Fragment Count Simplification & Fast Path 완료**
- **실측 측정 데이터 반영 (41s 영상)**:
  - raw/VF count: 2
  - semantic/SF count: 11
  - proposal A/B count: 11
  - FragmentMap count: 11
  - ExportInput clips count: 11
- **주요 성과**:
  - `Fast Path` 로직을 통해 단시간(<= 60s) 영상 분석 시 조각 수 폭주 방지 (48개 → 11개)
  - `Physical EDL` 기반 내보내기 흐름 확립 (ID 의존성 제거)
  - 프론트엔드/백엔드 불필요한 디버그 로그 대폭 정리
- **Pipeline Isolation**: PASS (기존 파이프라인 영향 없음)

---

## Validation Summary

| 항목 | 결과 |
|------|------|
| RenderEngine 구현 (`render_from_export_input`) | PASS |
| UI 통합 (export-input → render → render-result) | PASS |
| GitHub 위생 | PASS |
| 로컬 ↔ GitHub 동기화 | PASS |
| Fragment Count Optimization | PASS (11 frags for 41s) |
| Physical EDL Stability | PASS |

---

## Open Issues

- Resource Governor 미연동 (향후 STEP 10)
- PBE(Precision Boundary Editor) 비활성화 상태 유지 중
- 병렬 렌더링 미구현 (설계 단계)

---

## Next

- STEP 10-J 무료 폼 UI 실제 최소 구현 및 사용자 여정 확립
- STEP 10-F External Proposal Service Simulation v0 설계
- STEP 10 최종 안정화 / 회귀 테스트
�� 기준 확립
  - `FREE_VERSION_FEATURE_BOUNDARY.md`: 무료/유료 기능 경계 및 로컬 편집 무제한 원칙 고정
  - `PAID_FEATURE_POLICY.md`: 월 9,900원 요금제 및 "기억/조언" 중심 유료 기능 정의
  - `API_COST_GOVERNANCE_POLICY.md`: 외부 API 비용 사용자 별도 부담 및 CCUT의 관리 책임 명시
- **핵심 전략**: 무료는 "편집 도구", 유료는 "기획 파트너"로 서비스 성격 분리
- **Pipeline Isolation**: PASS (기본 파이프라인 영향 없음)

---

## Latest Revision (2026-05-01 12:00)

- **STEP 10-I.2 Proposal Resolver + Physical EDL Stabilization (HOLD)**
- **구조적 개선 완료**:
  - `proposalFragmentResolver.ts`: Proposal ID → Fragment 매칭 로직 유틸리티화
  - `exportClipBuilder.ts`: Resolved Fragment → Physical EDL (Time-range) 변환 로직 분리
  - `Index.tsx`: 매칭/추출 로직 제거 및 유틸리티 호출 구조로 간소화
  - `export_engine.py`: Physical EDL 필드(`start_sec`, `end_sec`) 우선 참조 로직 보완
- **발견된 이슈 (HOLD 사유)**:
  - **조각 수 과다 발생**: 41초 영상 분석 시 약 48개의 조각이 생성됨. 
  - 조각맵 표시 및 내보내기 흐름은 안정화되었으나, 너무 짧은 조각들이 많아 편집 가독성과 렌더링 효율이 저하될 위험이 있음.
- **다음 작업**: STEP 10-I.3 Fragment Count Simplification & Fast Path (조각 병합 및 분석 간소화)
- **Git 상태**: 로컬에 미커밋 수정 사항이 남아 있을 수 있음. 다음 세션 시작 시 `git status --short` 필수 확인.

---

## Validation Summary

| 항목 | 결과 |
|------|------|
| RenderEngine 구현 (`render_from_export_input`) | PASS |
| UI 통합 (export-input → render → render-result) | PASS |
| GitHub 위생 | PASS |
| 로컬 ↔ GitHub 동기화 | PASS |
| Working tree | Modified (STEP 10-I.2) |

---

## Open Issues

- **Fragment Count Overload**: 41s 영상 기준 48개 조각 생성 (병합 필요)
- Resource Governor 미연동 (향후 STEP 10)
- PBE(Precision Boundary Editor) 비활성화 상태 유지 중
- 병렬 렌더링 미구현 (설계 단계)

---

## Next

- STEP 10-I.3 Fragment Count Simplification & Fast Path
- STEP 10 최종 안정화 / 회귀 테스트
- 문서 구조 고정 및 방이전 자동화 체계 운영 시작

## Revision — Narrative Consultation Architecture Transition

### Date
2026-05-03

### Summary
CCUT1.0.4 introduced a pre-proposal narrative consultation structure.

### Before
Upload -> Analysis -> A/B Proposal

### After
Upload -> Analysis -> Narrative Draft -> User Consultation -> StoryIntent -> A/B Proposal

### Meaning
This revision changes CCUT from a direct automatic edit proposal tool into a local AI editing system that first interprets video data as a story, consults with the user in natural language, and only then generates A/B edit proposals.

### Stable Reference
E9-R2 stable commit:
56554c70e76ad03537193d5b560fd19457ce2477

### Remaining Work
The current Chat History / ChatGPT-like UX attempts are not accepted as final.
Next required work:
STEP 10-I.5.28-E9-R2-R3 — ChatGPT Form Narrative Chat Repair

### UX Requirement
CCUT must not invent a new chat grammar.
Narrative Consultation should follow a familiar ChatGPT-style conversation form:
- natural line wrapping
- accumulated message history
- calm white/gray-centered user and assistant messages
- minimal color emphasis
- input-first conversation
- suggestion chips only as secondary aids

## STEP 10-I.5.28-E9-R2-R5B - AI Staff Strategy Docs

- Baseline SHA: c9e9ced4f697a0a1018bd1d5598ef1763c9978bb
- Scope: Documentation only
- Created:
  - docs/ADOPTED_OPEN_SOURCE_AI_STRATEGY.md
  - docs/QWEN_AS_PRIMARY_AI_FAMILY_REVIEW.md
  - docs/CORE_AI_VS_CORE_COMPANION_POLICY.md
  - docs/CCUT_MODEL_TRAINING_STRATEGY.md
- Updated:
  - docs/TASK_BOARD.md
  - docs/SESSION_HANDOFF.md
  - docs/REVISION_REPORT.md
- Summary:
  - Defined AI as AI Staff / Core Companion, not CCUT Core.
  - Classified Qwen as Primary AI Staff candidate.
  - Classified Mistral as Secondary AI Staff candidate.
  - Classified Gemma and Llama as Caution AI Staff due to non-Apache model-specific terms.
  - Reconfirmed that CCUT Core owns decisions, evidence, and execution.
- Runtime impact: None.
- Code changes: None.

## STEP 10-I.5.28-E9-R2-R6 - Mock Narrative LLM Adapter

- Scope: Non-runtime mock adapter and contract only
- Created:
  - ccut_backend/ai/contracts/story_intent_patch_contract.py
  - ccut_backend/ai/boundary/mock_narrative_llm.py
  - tools/simulate_mock_narrative_llm.py
  - docs/NARRATIVE_LLM_MOCK_ADAPTER_SPEC.md
- Updated:
  - docs/TASK_BOARD.md
  - docs/SESSION_HANDOFF.md
  - docs/REVISION_REPORT.md
- Summary:
  - Added StoryIntentPatch and NarrativeLLMResult contract skeleton.
  - Added mock Narrative LLM adapter returning schema-shaped results without model calls.
  - Added standalone simulation script for contract verification.
  - No Qwen3-Instruct, external API, frontend fetch, backend main.py, config, DB, ProposalEngine, or runtime integration was added.
- Runtime impact: None.
- Code changes to existing runtime paths: None.

## STEP 10-I.5.28-E9-R2-R7 - Swappable Local Narrative LLM Provider Design

- Scope: Provider interface, candidate registry, and swap policy documentation
- Created:
  - ccut_backend/ai/contracts/narrative_llm_provider.py
  - ccut_backend/ai/boundary/narrative_provider_registry.py
  - docs/NARRATIVE_LLM_PROVIDER_SWAP_POLICY.md
  - docs/LOCAL_LLM_RUNTIME_OPTIONS.md
  - docs/QWEN_PROVIDER_CANDIDATE_PLAN.md
- Updated:
  - docs/NARRATIVE_LLM_MOCK_ADAPTER_SPEC.md
  - docs/TASK_BOARD.md
  - docs/SESSION_HANDOFF.md
  - docs/REVISION_REPORT.md
- Summary:
  - Defined NarrativeLLMProvider protocol for provider abstraction.
  - Added swappable provider candidate registry.
  - Kept Qwen3-Instruct as primary candidate, not hard dependency.
  - Preserved CCUT Core dependency only on StoryIntentPatch and NarrativeLLMResult contracts.
  - No actual AI model call, config change, API wiring, frontend fetch, or runtime integration was added.
- Runtime impact: None.

## STEP 10-I.5.28-E9-R2-R8 - Target Hardware Profile and Compatibility Probe

- Scope: Hardware tier definition and environment diagnostic tool
- Created:
  - ccut_backend/ai/boundary/hardware_profile.py
  - tools/inspect_local_ai_environment.py
  - docs/TARGET_HARDWARE_PROFILE.md
  - docs/DEVELOPER_MACHINE_POLICY.md
  - docs/HIGH_END_LAPTOP_AI_REQUIREMENTS.md
  - docs/LOCAL_LLM_COMPATIBILITY_PROBE.md
- Updated:
  - docs/TASK_BOARD.md
  - docs/SESSION_HANDOFF.md
  - docs/REVISION_REPORT.md
- Summary:
  - Established distinct hardware profiles: Developer Machine, Target High-End Laptop, and Minimum Supported Laptop.
  - Clarified that the developer machine is for verification, not product performance benchmarking.
  - Set high-end creator laptop class as the product viability reference for local LLM work.
  - Added a non-runtime diagnostic probe that does not load models or call external APIs.
- Runtime impact: None.

## STEP 10-I.5.28-E9-R2-R9 - Ollama Local Narrative Provider Probe

- Scope: Ollama runtime diagnostic and connectivity verification
- Created:
  - ccut_backend/ai/boundary/ollama_provider_probe.py
  - tools/probe_ollama_narrative_provider.py
  - docs/OLLAMA_PROVIDER_PROBE.md
  - docs/OLLAMA_LOCAL_RUNTIME_POLICY.md
- Updated:
  - docs/LOCAL_LLM_RUNTIME_OPTIONS.md
  - docs/QWEN_PROVIDER_CANDIDATE_PLAN.md
  - docs/TASK_BOARD.md
  - docs/SESSION_HANDOFF.md
  - docs/REVISION_REPORT.md
- Probe result:
  - ollama_running: true
  - models_found: qwen2:latest
  - selected_model: qwen2:latest
  - probe_status: MODEL_CALL_FAILED
  - error: timed out
  - latency_ms: 10004
- Summary:
  - Ollama server detection passed.
  - Model inventory detection passed.
  - First model call timed out on the developer machine.
  - This is not a product viability failure; it is a developer machine/runtime timeout finding.
  - No model pull, external API call, frontend connection, main.py API wiring, config change, or runtime integration was added.
- Runtime impact: None.

## STEP 10-I.5.28-E9-R2-R10-C - Qwen3 4B Ollama Candidate Install Plan

- Scope: Documentation and validation protocol only
- Created:
  - docs/QWEN3_4B_OLLAMA_INSTALL_PLAN.md
  - docs/QWEN3_4B_VALIDATION_PROTOCOL.md
  - docs/NARRATIVE_LLM_MODEL_BASELINE.md
- Updated:
  - docs/QWEN3_INSTRUCT_ACQUISITION_PLAN.md
  - docs/OLLAMA_MODEL_REGISTRATION_POLICY.md
  - docs/NARRATIVE_MODEL_SELECTION_MATRIX.md
  - docs/QWEN_PROVIDER_CANDIDATE_PLAN.md
  - docs/LOCAL_LLM_RUNTIME_OPTIONS.md
  - docs/TASK_BOARD.md
  - docs/SESSION_HANDOFF.md
  - docs/REVISION_REPORT.md
- Summary:
  - Set qwen3:4b as the first Narrative LLM validation baseline.
  - Recorded qwen3:0.6b as a manually installed smoke-test model.
  - Recorded qwen3:0.6b timeout as a timeout-policy finding, not a model adoption result.
  - Kept qwen2:latest as legacy/test-only.
  - Kept Qwen3-ASR as ASR-only.
  - Kept qwen3:8b as the high-end product candidate.
- Runtime impact: None.
- Model download or execution in this step: None.
