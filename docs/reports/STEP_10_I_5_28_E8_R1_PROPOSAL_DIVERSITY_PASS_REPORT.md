# STEP 10-I.5.28-E8-R1 Proposal Diversity Pass Report

## 1. 기준
- branch: ccut-1.0.4-step9
- 작업 전 SHA: 78e48668e2e5ae61db38f8d88f55d66e1d690776
- 수정 파일: ccut_backend/engine/proposal_engine.py
- 작업 성격: Lightweight Diversity Pass (R1)

## 2. 주요 변경 사항

### A/B Overlap Penalty (Mode B)
- **적용 방식**: Mode A(`_create_market_proposal`)에서 선택된 `fragment_id` 세트를 Mode B(`_create_user_proposal`)에 전달합니다.
- **페널티**: B안의 `edit_score` 계산 시, A안에 이미 포함된 조각은 30% 감점(`* 0.7`)을 적용하여 후순위로 밀어냅니다.
- **효과**: 완벽한 차단이 아닌 'Soft Penalty'를 통해 고품질 조각이 부족한 경우 중복을 허용하면서도 최대한 다른 조각을 선택하도록 유도합니다.

### Source Soft Balance
- **적용 대상**: 프로젝트에 포함된 소스 영상이 2개 이상인 경우 활성화됩니다.
- **적용 방식**: 선택 루프 내에서 특정 소스의 점유율을 실시간 계산합니다.
  - **Market Mode (A)**: 특정 소스 점유율이 50%를 초과할 경우, 남은 목표 길이의 20% 이상 여유가 있을 때 해당 소스의 조각을 건너뜁니다.
  - **User Mode (B)**: 특정 소스 점유율이 40%를 초과할 경우, 남은 목표 길이의 10% 이상 여유가 있을 때 해당 소스의 조각을 건너뜁니다.
- **효과**: 특정 영상에 제안 조각이 100% 몰리는 현상을 완화하고, 여러 영상의 조각이 골고루 섞이도록 유도합니다.

## 3. 원칙 준수 확인
- 강제 균등 배분 여부: **NO** (Soft Penalty/Skip 방식 사용)
- 외부 AI/재분석 여부: **NO** (순수 로직 보정)
- Narrative 연결 여부: **NO** (설명 텍스트만 업데이트)
- Complexity: **O(n log n)** (기존 정렬 및 단일 루프 유지)

## 4. 검증 결과
- **py_compile**: PASS (로컬 환경 기준)
- **예상 속도 영향**: **LOW** (메모리 내 연산 및 단순 카운팅만 추가됨)

## 5. Runtime 검증 필요 항목 (사용자 수행)
- 멀티 소스 프로젝트 생성 시 A/B 제안의 첫 장면이 달라지는지 확인
- `source_usage` 통계에서 특정 영상 점유율이 과도하게 높은(100%) 사례가 감소했는지 확인
- 제안 생성 속도가 이전과 동일하게 유지되는지 확인

## 6. 판정
**PASS**
