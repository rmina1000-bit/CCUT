# STEP 6 Proposal Engine 보고서

## 1. 개요
Semantic Fragments와 User Intent를 결합하여 최종 편집 구성안(Proposal)을 생성하는 엔진을 구현하였습니다. 대중적 지표를 따르는 **Market Mode(A)**와 사용자 의도를 엄격히 반영하는 **User Mode(B)**의 듀얼 구조를 채택하였습니다.

## 2. 주요 구현 내용

### 2-1. 데이터 모델 및 영구 저장소
- **ProposalTable 추가**: `proposal_id`, `mode(A/B)`, `sequence`, `duration`, `reasoning`, `confidence` 등을 포함하는 테이블 구축.
- **BAMSManager 연동**: 제안 데이터의 생성 및 조회를 위한 `save_proposals`, `get_proposals` 메서드 구현.

### 2-2. Proposal 생성 로직 (A/B 모드 분리)
- **Market Mode (A)**: `market_value`(대중적 가치)를 기준으로 조각을 선택하여 범용적인 고품질 구성안 생성.
- **User Mode (B)**: `edit_value`(사용자 의도 반영 가치)를 기준으로 키워드 매치 및 가중치가 반영된 맞춤형 구성안 생성.

### 2-3. 고급 구성 기술
- **Bridge Fragment 예외 처리**: 선택된 주요 조각 사이에 위치하며, `time_proximity`가 높고 길이가 짧은(< 5s) 조각을 자동으로 '브릿지'로 삽입하여 흐름의 자연스러움 확보.
- **Target Length 유연화**: 설정된 목표 길이를 기반으로 ±10% 범위를 우선 타겟팅하며, 불가능할 경우 가장 근접한 조합을 도출하고 `fallback_reason`에 기록.

### 2-4. API 엔드포인트
- **POST `/proposals/{source_id}`**: 듀얼 모드 제안 생성 트리거.
- **GET `/proposals/{source_id}`**: 생성된 제안 목록 및 상세 구성(sequence) 조회.

## 3. 검증 결과 (SRC_3BD89C3B)

| 항목 | 결과 | 비고 |
| :--- | :--- | :--- |
| **Proposal 수** | 2개 (Mode A, Mode B) | 듀얼 구조 생성 확인 |
| **Target Length** | 30.0s 반영 완료 | ±10% 오차 범위 내 선정 확인 |
| **Market Mode 점수** | `market_value` (0.489) 기준 정렬 | 유저 의도와 독립적인 선정 확인 |
| **User Mode 점수** | `edit_value` (0.187) 기준 정렬 | Avoid/Must-keep 반영 확인 |
| **Bridge Logic** | 적용됨 | 시공간적 인접 조각 삽입 로직 검증 |

## 4. 규격 및 금지사항 준수 확인
- **영상 파일 생성 없음**: 제안은 오직 JSON 시퀀스 데이터로 존재함.
- **STEP 5 의존성**: User Intent가 반영된 후 Rescoring된 데이터를 기반으로 Proposal 생성 확인.
- **데이터 무결성**: 모든 제안에 `proposal_id`, `source_id`, `mode` 등 필수 필드 포함.

## 5. 최종 판정: PASS ✅
듀얼 모드 전략에 따른 지능형 Proposal 생성이 완료되었으며, 모든 정량적/정성적 요구사항을 충족합니다.

---
**보고서 생성 일시**: 2026-04-26 23:45
**파일 경로**: D:\CCUT1.0.4\docs\reports\STEP6_PROPOSAL_REPORT.md
