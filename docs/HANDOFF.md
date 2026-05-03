# CCUT1.0.4 Handoff

## Current Branch
- branch: ccut-1.0.4-step9
- repo: https://github.com/rmina1000-bit/CCUT.git
- local path: D:\CCUT1.0.4

## Confirmed Stable Commit (AI Boundary Closure)
- latest SHA: `603c46861d0817e4f47e6539545b0eb3a3c3bc24`
- commit message: Update handoff docs for AI boundary and Qwen baseline

## Current Status: AI Boundary & Narrative LLM Preparation
CCUT 1.0.4 has completed the foundational design for swappable local AI providers.

1. **AI Boundary Implementation**: All AI services are now decoupled from the CCUT Core via an AI Boundary.
2. **Qwen Baseline**: `qwen3:4b` is designated as the primary validation baseline for Narrative LLM.
3. **Ollama Integration**: Ollama is the primary local runtime candidate. `qwen3:0.6b` was tested (smoke-test) but showed latency issues.
4. **Separation of Concerns**:
   - Qwen3-ASR: Specialized for audio transcription (ASR-only).
   - Qwen3-Instruct: Specialized for narrative consultation (Narrative LLM).
   - qwen2:latest: Legacy/Test-only.

## Next Required Step
**R10-D: Ollama Timeout / keep_alive / num_predict / JSON Response Stabilization**

This step will address the latency/timeout issues observed during the `qwen3:0.6b` smoke test and stabilize the JSON output format for the `StoryIntentPatch` contract.

## Antigravity 고정 지시
모든 작업 전후 반드시 `PROJECT_NAVIGATION.md`를 확인하고, 현재 작업이 전체 흐름 중 어디인지 표시한다.

## 작업 완료 조건
```text
1. 로컬 수정 완료
2. git add / git commit
3. git push origin ccut-1.0.4-step9
4. git rev-parse HEAD 확인
5. git rev-parse origin/ccut-1.0.4-step9 확인
6. 두 SHA 일치 + git status clean = 완료
```

## 절대 금지
- AI를 CCUT Core에 Hard-link 금지 (AI Boundary 필수)
- 사용자 협의 전 편집 제안 영상 노출 금지
- StoryIntent 없이 ProposalEngine에 사용자 의도 반영 주장 금지
- 모델 자동 다운로드 금지
