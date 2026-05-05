# STEP 10-K-B3-Minimal Constraint Report: Balanced Sources implementation

## 1. 감사 환경 및 기준점
- **시작 HEAD:** `0fa1e85e62fe7ce43e6209bbd0def2283dba5289`
- **Branch:** `ccut-1.0.4-step9`
- **수정 파일:** `ccut_backend/engine/proposal_engine.py`

## 2. 주요 구현 내용
### A. Balanced Source Constraint 로직 적용
- `_create_user_proposal` 함수에서 `story_context.template_id`가 `balanced_multi_source_record`인 경우에만 `_apply_balanced_source_constraints`를 호출하도록 구현하였습니다.
- `hard_constraints`로부터 `min_source_coverage_ratio`, `min_fragments_per_selected_source`, `max_single_source_clip_ratio` 값을 읽어와 보정 로직에 반영합니다.

### B. 신규 Helper 함수 추가
1. **`_calculate_source_distribution(sequence)`**:
   - 시퀀스 내 소스별 점유율 및 최대 점유율을 계산합니다.
2. **`_apply_balanced_source_constraints(selected, candidates, hard_constraints)`**:
   - 부족한 소스를 후보군에서 보충 (Coverage 보장).
   - 단일 소스 과점유 여부 체크 및 경고 생성.
   - 소스 순환(Rotation) 배치를 통한 시각적 다양성 확보.

## 3. 출력 데이터 예시
### A. source_distribution
```json
{
  "source_count": 2,
  "total_fragments": 10,
  "by_source": {
    "SRC_A": { "count": 6, "ratio": 0.6 },
    "SRC_B": { "count": 4, "ratio": 0.4 }
  },
  "max_single_source_ratio": 0.6
}
```

### B. balance_policy
```json
{
  "applied": true,
  "template_id": "balanced_multi_source_record",
  "warnings": ["max_single_source_clip_ratio_exceeded"]
}
```

## 4. 검증 결과
- **py_compile:** `python -m py_compile ccut_backend/engine/proposal_engine.py` 실행 시 구문 오류 없음 확인.
- **Git Status:** 
  ```text
  M ccut_backend/engine/proposal_engine.py
  ?? docs/reports/STEP_10_K_B3_MINIMAL_CONSTRAINT_REPORT.md
  ```
- **판정:** **PASS**
  - 유저 의도(`balanced_sources`)가 실제 엔진의 제안 생성 로직에 반영되었으며, 메타데이터를 통해 검증 가능한 구조를 확립하였습니다.

---
*작성일: 2026-05-05*  
*수행자: Antigravity*
