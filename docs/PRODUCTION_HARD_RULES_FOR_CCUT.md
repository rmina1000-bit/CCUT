# Production Hard Rules for CCUT

## 1. 개요
CCUT 1.0.4의 편집 엔진은 예술적 창의성을 허용하되, 방송 송출 품질(Broadcast Quality)을 위협하는 행위는 **Hard Rule**을 통해 원천 차단합니다. 이 규칙들은 `video-use`의 안정적인 렌더링 파이프라인에서 영감을 얻어 설계되었습니다.

## 2. 규칙 카테고리

### A. Audio & Cutting Integrity
- **No Mid-word Cut**: 단어 중간을 자르면 오디오가 깨지므로 절대 금지합니다.
- **Word Boundary Snap**: 모든 편집점은 분석된 단어의 경계에 자동으로 붙습니다.
- **30ms Fade**: 컷 연결부의 급격한 파형 변화로 인한 잡음을 방지합니다.

### B. Rendering & EDL
- **EDL-First**: 물리적 렌더링 전에 논리적 편집표(EDL)를 먼저 검증합니다.
- **Subtitle Post-process**: 자막은 시각 효과의 영향을 받지 않도록 가장 나중에 입힙니다.
- **Self-Evaluation**: 렌더링이 완료된 파일은 AI가 다시 한 번 눈과 귀로 검사합니다.

### C. System & Safety
- **Read-only Source**: 원본 영상 파일은 어떠한 경우에도 변형되지 않습니다.
- **Sandboxed Output**: 결과물은 지정된 보안 경로 내에서만 생성됩니다.
- **Non-blocking VL**: 무거운 비주얼 분석이 전체 분석 속도를 늦추지 않도록 관리합니다.

## 3. 강제 조치 (Enforcement)

규칙 위반 시 시스템은 다음과 같이 대응합니다:
1.  **Automatic Correction**: 단어 경계 스냅처럼 즉시 수정 가능한 경우 자동 보정합니다.
2.  **Invalid Proposal**: 편집 제안 자체가 성립하지 않는 것으로 판단하여 제안 목록에서 제외합니다.
3.  **Halt Execution**: 시스템 무결성을 해칠 우려가 있는 경우 프로세스를 즉시 중단합니다.

---
**Status**: Rules Integrated (STEP 10-K-B2 PASS)
- [x] Hard rules defined in `production_hard_rules.json`.
- [x] Successfully linked to templates via `StoryTemplateResolver`.
- [x] Rule enforcement points identified in `ProposalEngine`.
