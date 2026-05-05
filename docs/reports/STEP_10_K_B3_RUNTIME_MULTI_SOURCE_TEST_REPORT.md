# STEP 10-K-B3-Runtime Multi-Source Test Report: 다중 소스 검증

## 1. 시작 환경 및 기준점
- **시작 HEAD:** `0fa1e85e62fe7ce43e6209bbd0def2283dba5289`
- **Branch:** `ccut-1.0.4-step9`
- **git status:**
  ```text
  M ccut_backend/engine/proposal_engine.py
  ?? docs/reports/STEP_10_K_B3_AUDIT_REPORT.md
  ?? docs/reports/STEP_10_K_B3_MINIMAL_CONSTRAINT_REPORT.md
  ?? docs/reports/STEP_10_K_B3_RUNTIME_TEST_REPORT.md
  ?? tools/quality_audit_collector.py
  ```

## 2. 다중 소스 데이터 확인 결과
- **DB 조회 및 API Probe 수행 결과:**
  - `SRC_3BD89C3B`: Semantic Fragment 5개 존재 (READY)
  - `SRC_789199EE`: NOT_FOUND
  - `SRC_4B7DFECE`: NOT_FOUND
  - `SRC_52E20C15`: NOT_FOUND (또는 Fragment 0개)
  - `SRC_F0F2F653`: NOT_FOUND
  - `SRC_DE91869B`: NOT_FOUND
  - `SRC_D88BB687`: NOT_FOUND
- **판정:** 현재 DB 내에 유효한 Semantic Fragment를 보유한 소스가 `SRC_3BD89C3B` 1개뿐인 것으로 확인됨.

## 3. API 테스트 수행 (Multi-Source 시도)
- **요청 JSON:**
  ```json
  {
    "project_id": "TEST_BALANCED_MULTI_SOURCE_REPORT",
    "source_ids": ["SRC_3BD89C3B", "SRC_52E20C15", "SRC_F0F2F653"],
    "target_length": 60,
    "user_intent": {
      "coverage": "balanced_sources"
    }
  }
  ```
- **응답 결과:**
  - `status`: `NO_SEMANTIC_DATA` (또는 유효 소스가 1개로 제한됨)
  - `reason`: `NO_SEMANTIC_FRAGMENTS_SKIPPED` 경고와 함께 다중 소스 분배 로직이 실행되지 않음.

## 4. 검증 결과 요약
- **resolved_story_template.template_id**: `balanced_multi_source_record` (매핑은 정상)
- **User Proposal source_distribution**: `source_count`가 1로 고정됨 (유효 소스 부족)
- **balance_policy.applied**: `true` (로직 진입은 확인)
- **source_rotation 확인**: 데이터 부족으로 검증 불가.

## 5. 최종 판정: HOLD
- **분류:** **A. semantic source가 1개뿐임**
- **사유:** `balanced_sources` 제약 조건의 핵심인 "다중 소스 간 균등 배분" 및 "교차 배치(Rotation)"를 검증하기 위해서는 최소 2개 이상의 유효 소스가 필요합니다. 현재 환경에서는 분석 데이터가 단일 소스에만 존재하여 실제 엔진의 분배 성능을 물리적으로 테스트할 수 없습니다.

---
*작성일: 2026-05-05*  
*검증자: Antigravity*
