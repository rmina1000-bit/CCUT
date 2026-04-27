# STEP 5 User Intent 최종 반영 보고서

## 1. 개요
사용자의 명시적인 편집 의도(must_keep, avoid, target_length, priority_axis)를 시스템에 반영하고, 이에 따라 기존 Semantic Fragments의 우선순위(`edit_value`)를 재계산하는 작업을 완료하였습니다.

## 2. 주요 작업 내용

### 2-1. 데이터 모델 및 영구 저장소 구축
- **UserIntentTable 추가**: `source_id`, `must_keep`, `avoid`, `tone`, `target_length`, `priority_axis` 필드를 포함하는 전용 DB 테이블 생성.
- **BAMSManager 연동**: 유저 의도 데이터를 CRUD할 수 있는 `save_user_intent`, `get_user_intent` 메서드 구현.

### 2-2. 의도 기반 Rescoring 엔진 구현
- **SemanticFragmentGenerator 확장**: `rescore_all_fragments` 및 관련 헬퍼 함수 구현.
- **match_must_keep (+0.2)**: Semantic 정보(summary, topic) 내 키워드 매칭 시 가산점 부여.
- **match_avoid (-0.3)**: 키워드 매칭 시 감점 부여.
- **apply_priority_axis**: 사용자 선호도(visual, speech, emotion)에 따른 Evidence 신호 가중치 실시간 반영.
- **Rescoring Pipeline**: 의도 변경 시 즉시 모든 조각의 `edit_value`를 재계산하고 DB를 업데이트함.

### 2-3. API 엔드포인트 구현
- **POST `/user-intent/{source_id}`**: 사용자 의도 반영 및 Rescoring 트리거.
- **GET `/user-intent/{source_id}`**: 현재 반영된 유저 의도 정보 조회.

## 3. 검증 결과 (SRC_3BD89C3B)

| 상태 | Intent 조건 | Edit Value (SF_EB4C) | 비고 |
| :--- | :--- | :--- | :--- |
| **Base** | default | 0.487 | 기본 가중치 적용 |
| **Must Keep** | keyword: "general" | 0.687 | +0.2 가산점 확인 |
| **Avoid** | keyword: "general" | 0.187 | -0.3 감점 확인 |
| **Priority** | visual: 1.2 | 0.537 | 가중치에 따른 수치 변화 확인 |

## 4. 규격 및 금지사항 준수 확인
- **target_length**: DB에 저장 작업만 수행 완료. 실제 길이 조정 로직은 STEP 6(Proposal)에서 구현 예정.
- **emotion**: 감정 분석 전까지 Placeholder 가중치로 처리하여 과판단 방지.
- **코드 무결성**: 기존 Semantic/Structural 데이터의 ID 및 타임스탬프 정합성 유지.

## 5. 최종 판정: PASS ✅
사용자 의도가 Semantic Fragment 계층에 정확히 투영되었으며, Rescoring 엔진이 논리적으로 올바르게 동작함을 확인하였습니다.

---
**보고서 생성 일시**: 2026-04-26 23:00
**파일 경로**: D:\CCUT1.0.4\docs\reports\STEP5_USER_INTENT_REPORT.md
