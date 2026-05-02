# STEP 10-I.5.25 Proposal Explanation & Storyline Trace Report

## 0. 개요
ProposalEngine에서 생성되는 A/B 제안에 대해 사용자에게 편집 의도와 조각 선택 근거를 투명하게 제공하기 위한 Explanation 로직을 구현하고 검증함.

## 1. 작업 결과
- **HEAD**: `5d505f893968c8beed8c723c2299e3fff14df5d7`
- **수정 파일**: `ccut_backend/engine/proposal_engine.py`
- **주요 추가 필드**: `proposal_explanation`

## 2. 상세 구현 내용
### 2.1 Source Summaries
- 각 소스 영상별로 지배적인 주제(Dominant Topic), 시각적 특징, 오디오 분석 상태를 요약함.
- `audio_text_status`: Transcript 존재 여부에 따라 `available` / `missing` 표시.

### 2.2 Storyline Trace
- 선택된 시퀀스를 3단계(Opening, Main, Closing)로 추적함.
- 멀티 소스 환경인 경우 "소스 간 교차 편집" 여부를 설명에 포함함.

### 2.3 Selection Reasons
- 조각별 선택 근거를 생성함.
- `hook` 역할, `market_value`, `edit_value` 점수를 기반으로 사람이 읽을 수 있는 문장으로 변환.

### 2.4 Quality Warnings
- 데이터 품질에 따른 경고를 자동으로 생성함.
- 예: "음성 분석 데이터 부재", "제네릭 서머리 비중 높음", "단일 소스 편중" 등.

## 3. 검증 결과
- **py_compile**: PASS
- **단일 소스 API (SRC_7561FF44)**: `PROPOSAL_READY` 확인됨.
- **Project API (/proposals/project)**: `PROPOSAL_READY` 및 `semantic_count: 132` 확인됨.
- **성능 영향**: LOW (메모리 내 연산만 수행하여 속도 저하 없음)

## 4. 특이사항
- 기존 `proposal_story`와 `proposal_reason` 필드를 유지하여 프론트엔드 하위 호환성을 보장함.
- 모든 로직은 이미 로드된 fragments pool과 sequence만을 사용하여 추가적인 I/O를 발생시키지 않음.

---
**Status: PASS**
