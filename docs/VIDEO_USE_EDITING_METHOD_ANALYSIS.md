# Video-use Editing Method Analysis

## 1. 개요
CCUT 1.0.4가 벤치마킹하는 `video-use` 방식은 단순히 "AI가 알아서 하는 편집"이 아니라, 데이터 무결성과 워크플로우의 안정성을 보장하는 엄격한 **편집 규약(Editing Protocols)**의 집합입니다.

## 2. 핵심 철학 (The video-use Way)

### A. Transcript-First Editing
- 영상의 시각적 요소보다 대사(Transcript)를 편집의 기본 단위로 삼습니다.
- 문장(Sentence)이나 단어(Word) 경계를 기준으로 컷을 생성하여 오디오의 부자연스러움을 원천 차단합니다.

### B. Audio Primary, Visuals On-Demand
- 오디오 흐름(Narrative Flow)을 먼저 완성한 뒤, 이에 맞는 시각적 조각(Visuals)을 매칭합니다.
- 모든 시각 데이터는 필요할 때만(On-demand) 깊게 분석하여 시스템 부하를 최소화합니다.

### C. Ask → Confirm → Execute → Iterate Loop
- 사용자의 모호한 요청을 명확한 스토리 전략(Story Strategy)으로 구체화하고, 사용자의 확인(Confirm)을 거친 후 실제 렌더링을 수행합니다.
- 결과가 마음에 들지 않으면 다시 의도를 수정(Iterate)하여 최종본을 확정합니다.

### D. EDL-First Render
- 물리적인 영상 파일을 직접 자르기 전에, 논리적인 편집 목록(Edit Decision List)을 먼저 생성합니다.
- 실제 렌더링은 마지막 단계에서 한 번만 수행하여 비파괴 편집(Non-destructive editing)을 유지합니다.

## 3. CCUT 적용 방식

| video-use 특징 | CCUT 1.0.4 구현 방식 |
| :--- | :--- |
| **No preset UI** | Narrative Consultation (ChatGPT-style Chat) |
| **Production Rules** | `production_hard_rules.json` (엄격한 제약 조건) |
| **Self-Eval Loop** | `qa_checks`를 통한 제안 품질 검증 |
| **Fast Path** | 초기 분석은 가볍게, 심층 분석(VL)은 필요한 조각에만 적용 |

## 4. 결론
CCUT은 `video-use`의 무질서해 보이는 유연성 이면에 숨겨진 **"Hard Production Rules"**를 데이터화하여, AI 편집의 결과가 항상 방송 송출 수준의 품질을 유지하도록 설계합니다.

---
**Status**: Method Analysis Complete (STEP 10-K-B1-R1)
