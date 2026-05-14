# STEP 2-C-R3B: Proposal A/B Split Logic Audit

**작성일**: 2026-05-14
**branch**: ccut-1.0.4-step9
**HEAD**: a9ca53272072756c5c655c8f27b66aac6fac7b5b
**상태**: Selection Policy 정상 동작 확인 (의도된 A/B 분할)

---

## 1. 감사 배경

SRC_616AEFBA의 동일한 Semantic Group (summary가 동일한 P001~P005 구간)이 Proposal A와 B에 의해 기계적으로 분할되는 원인을 분석한다.

- **Proposal A**: P001, P003, P005 선택 (홀수 인덱스)
- **Proposal B**: P002, P004 선택 (짝수 인덱스)

---

## 2. 핵심 로직 분석 (`ccut_backend/engine/proposal_engine.py`)

### 2-1. Selection Guard: `_is_contiguous_to_selected` (L837-866)

- **임계값**: 0.15초
- **동작**: 현재 선택하려는 조각의 `start`가 이미 선택된 조각의 `end`와 0.15초 이내로 붙어있으면 **Skip** 한다.
- **목적**: '편집 제안'으로서의 가치를 위해, 단일 소스의 너무 긴 구간이 통째로 들어가는 것을 방지하고 컷 전환(Jump-cut) 효과를 유도한다.

### 2-2. Mode B의 중복 페널티: `edit_score` (L227-232)

- **로직**: `if f.id in overlap_ids: base *= 0.7`
- **동작**: Proposal A가 이미 선택한 fragment ID에 대해 0.7배의 점수 페널티를 부여한다.
- **목적**: A안과 B안이 최대한 서로 다른 장면을 제안하도록 강제한다.

---

## 3. 분할 시뮬레이션 (SRC_616AEFBA 사례)

| Fragment | Edit Value | A 선택 여부 | B 스코어 (0.7 penalty) | B 선택 여부 |
|----------|------------|------------|------------------------|------------|
| **P001** | 0.165 | **선택** (첫 조각) | 0.115 (Penalized) | Skip (Contiguous to P002) |
| **P002** | 0.165 | Skip (Contiguous to P001) | **0.165** (Highest) | **선택** (A가 버린 최고점) |
| **P003** | 0.165 | **선택** (P001과 이격) | 0.115 (Penalized) | Skip (Contiguous to P002) |
| **P004** | 0.165 | Skip (Contiguous to P003) | **0.165** (Highest) | **선택** (P002와 이격) |
| **P005** | 0.165 | **선택** (P003과 이격) | 0.115 (Penalized) | Skip (Contiguous to P004) |

### 결과 해석

1. **Proposal A**는 시간 순서대로 탐색하며 하나 건너 하나씩(P001, P003, P005)을 "최선"으로 선택한다.
2. **Proposal B**는 A가 선택한 조각들에 페널티를 받으므로, **A가 버린 조각들(P002, P004)**이 상대적으로 최고점이 되어 이를 우선적으로 선택한다.
3. 그 결과, 동일한 고득점 구간 내에서 A와 B가 지그재그로 장면을 나누어 가지게 된다.

---

## 4. 추가 제약 사항: Hard Guard (L868-916)

- 선택이 완료된 후 `_hard_guard_final_sequence`가 다시 한 번 적용된다.
- 이 함수는 `min_gap_sec = 1.0`을 적용하여, 선택 단계(0.15s)보다 더 엄격하게 동일 소스의 근접 조각을 제거한다.
- 현재 P001, P003 사이에는 P002(약 9.5초~20초)라는 큰 간격이 존재하므로 이 가드를 안전하게 통과한다.

---

## 5. 최종 판정

| 항목 | 판정 |
|------|------|
| 분할 로직 존재 여부 | **확인됨** (Overlap Penalty + Contiguous Guard) |
| 지그재그 분할 원인 | **의도된 동작** (A/B 차별화 정책의 결과) |
| B가 2개인 이유 | P002, P004 선택 후 나머지(P001, P003, P005)는 시간상 인접하여 Guard에 의해 차단됨 |
| 시스템 무결성 | **PASS** (버그가 아닌 정책에 따른 정교한 선택 결과임) |

### 결론

Proposal B의 조각 수가 적은 것은 "점수 부족"이나 "에러"가 아니라, **"Proposal A와의 중복을 피하면서도 동시에 물리적 연속성을 끊어야 한다"**는 두 가지 정책이 충돌하며 발생한 자연스러운 결과입니다. 

만약 B의 조각 수를 늘리고 싶다면:
1. `edit_value` 임계값을 낮추어 다른 Semantic Group의 조각들도 후보군에 넣거나,
2. Contiguous Guard의 threshold를 0으로 설정하여 연속 구간을 허용해야 합니다 (권장하지 않음).

---

본 문서는 STEP 2-C-R3B Proposal A/B Split Logic 공식 감사 보고서입니다.
