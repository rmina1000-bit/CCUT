# STEP 10-K-B3-Audit Report: Balanced Sources Proposal Constraint

## 1. 감사 환경 및 기준점
- **시작 HEAD:** `0fa1e85e62fe7ce43e6209bbd0def2283dba5289` (Expected)
- **Branch:** `ccut-1.0.4-step9`
- **시스템 상태:** Windows PowerShell 기반 / `run_command` 도구의 샌드박스 이슈로 인해 실제 `git` 명령 확인은 실패하였으나, `list_dir` 및 `view_file`을 통해 코드 무결성 및 파일 존재 여부를 교차 검증함.

## 2. Git Status 및 잔여 파일 확인
- **git status:** `run_command` 제한으로 상세 출력 불가.
- **tools/quality_audit_collector.py:** 존재 확인 (`sizeBytes: 8783`).
  - 유저 지시서에 따라 `untracked` 상태로 간주하며, 이번 작업에서 수정하거나 포함하지 않음.

## 3. 데이터 파이프라인 감사 (입력 흐름)
- **경로:** `POST /proposals/project` → `user_intent` → `resolved_story_template` → `ProposalEngine`
- **검증 결과:**
  - `ccut_backend/main.py` (L1060): `template_resolver.resolve_story_template`을 통해 의도 해석 완료.
  - `ccut_backend/main.py` (L1102): `engine.generate_proposals_from_fragments` 호출 시 해석된 템플릿을 **`story_context`** 인자로 전달 중.
  - **결론:** 파이프라인은 이미 백엔드 엔진 깊숙이 연결되어 있음.

## 4. ProposalEngine 내부 주요 함수 목록
| 단계 | 함수명 | 역할 |
| :--- | :--- | :--- |
| **Entry** | `generate_proposals_from_fragments` | 전체 제안 생성 제어 및 A/B 분기 |
| **Scoring** | `market_score` (Local in `_create_market_proposal`) | 시장 가치 기반 점수 계산 |
| **Scoring** | `edit_score` (Local in `_create_user_proposal`) | 편집 가치 및 중복 페널티 기반 점수 계산 |
| **Selection** | `_create_market_proposal` | 하이라이트 중심 조각 선택 루프 |
| **Selection** | `_create_user_proposal` | 사용자 의도 중심 조각 선택 루프 |
| **Ordering** | `_insert_bridges` | 시간순 정렬 및 브릿지 조각 삽입 |
| **Description** | `_generate_story` / `_generate_explanation` | 제안 근거 및 요약 텍스트 생성 |

## 5. Source 추적 및 데이터 확장 가능성
- **source_id 추적:** Fragment 객체에 `source_id` 필드가 유지되고 있어 전 단계에서 추적 가능함.
- **source_distribution 추가 위치:** 
  - `ProposalEngine.generate_proposals_from_fragments` 내부에서 제안 리스트를 반환하기 직전에 각 제안별로 계산하여 삽입 가능.
  - 현재 `main.py` (L1111)에서 `source_usage`를 계산하고 있으나, 이를 엔진 내부로 이동하여 더 정밀한 통계(점유율 등)를 제공하는 것이 유리함.

## 6. Balanced Constraint 적용 및 수정 계획
- **핵심 지점:** `_create_user_proposal` 루프 내의 **Source Soft Balance** 로직 (L203-209).
- **수정 후보:**
  - 현재 하드코딩된 `share > 0.4` 및 페널티 로직을 `story_context['hard_constraints']` 참조 방식으로 전환.
  - `min_source_coverage_ratio` (0.6) 보장을 위해 선택 루프 종료 후 미사용 소스 강제 보충(Forced Injection) 로직 추가 필요.
- **수정 대상 파일:**
  - `ccut_backend/engine/proposal_engine.py`

## 7. 판정 및 차기 단계 제언
- **판정: PASS**
- **근거:** 파이프라인 단절 없음. 설정 데이터(`story_direction_templates.json`)가 엔진에 도달하고 있음을 확인. 엔진 내부의 선택 알고리즘만 "데이터 참조형"으로 고도화하면 목표 달성 가능.
- **차기 단계:** `STEP 10-K-B3 Balanced Sources Proposal Constraint` 구현 착수 가능.

---
*작성일: 2026-05-05*  
*감사자: Antigravity*
