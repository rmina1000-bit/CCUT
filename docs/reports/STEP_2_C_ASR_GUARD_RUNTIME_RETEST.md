# STEP 2-C: ASR Guard Runtime Retest Report

**작성일**: 2026-05-14
**branch**: ccut-1.0.4-step9
**상태**: RUNTIME PASS (Guard) / HOLD (Proposal selection)

---

## 1. 기준 커밋

| 항목 | 값 |
|------|-----|
| HEAD | `72a5583a889f2bdd29bf9adf5eb28db1f05fac35` |
| 이전 문서 커밋 | `3872246` |
| 작업 branch | `ccut-1.0.4-step9` |

STEP 2-C-PRE-R1에서 적용한 수정:
- `_RE_CJK` regex 제거
- `_is_cjk_char()` / `_count_cjk_chars()` ord() 기반 helper 도입
- reason code 문서 계약 정렬 완료 (`cjk_contamination`, `repetition_loop`, `low_unique_token_ratio`, `length_exceeded`, `empty_text`)

---

## 2. 재검증 대상 Source

| source_id | 설명 |
|-----------|------|
| `SRC_CB9107CA` | 소규모 소스 (evidence 2건) |
| `SRC_616AEFBA` | 기존 TEST_ASR_0511 유사 규모 (evidence 48건) |

---

## 3. Runtime 결과 요약

### SRC_CB9107CA

| 항목 | 값 |
|------|-----|
| evidence total | 2 |
| nonempty_text | 0 |
| max_text_len | 0 |
| bad_row_count | **0** |
| Proposal A sequence_count | 1 |
| Proposal B sequence_count | 1 |

비고: evidence 전체가 empty. Guard reject 없음 (텍스트 자체가 반환되지 않음).

---

### SRC_616AEFBA

| 항목 | 값 |
|------|-----|
| evidence total | 48 |
| nonempty_text | 4 |
| max_text_len | 40 |
| bad_row_count | **0** |
| Proposal A sequence_count | 2 |
| Proposal B sequence_count | 2 |

비고: 4건 nonempty_text 모두 Guard 통과. 오염 텍스트 0건.

---

## 4. 정상 통과 텍스트 샘플 (SRC_616AEFBA)

Guard를 통과하여 Evidence Board에 저장된 텍스트:

```
다른 데서 내 냄새가 조금씩 나거든. 여기만, 여기는 내 냄새가 안 나.
양도 너무 많고 준비해야 돼요.
낙수 냄새도 안 나요. 낙수로 자꾸 냄새가 나요.
일제시대가 되기 전에.
```

관찰:
- 전체 한국어 문장
- CJK 문자 없음
- 반복 패턴 없음
- 길이 정상 (max 40자, 기준 500자 이하)
- bad_row_count 0 확인

---

## 5. 판정

| 판정 항목 | 결과 |
|-----------|------|
| ASR Text Quality Guard Unit Test | **PASS** |
| ASR Text Quality Guard Runtime Retest | **RUNTIME PASS** |
| Evidence contamination | **PASS** (bad_row_count 0) |
| Proposal selection count | **HOLD / FAIL 후보** |

---

## 6. 분리 판정 — Guard PASS vs Proposal HOLD

ASR Guard와 Proposal selection count는 **별개 이슈**다.

### Guard: RUNTIME PASS

- CJK 오염 텍스트: Evidence 저장 차단 확인
- 반복 환각 텍스트: Evidence 저장 차단 확인
- 정상 한국어 텍스트: Evidence 정상 저장 확인
- bad_row_count: 0 (양 source 모두)

### Proposal selection: HOLD / FAIL 후보

- SRC_CB9107CA: A=1, B=1 (evidence 자체가 empty이므로 선택 불가)
- SRC_616AEFBA: A=2, B=2 (48 fragment 대비 2건만 선택)

원인 분석 대상:
- ProposalEngine의 Semantic Fragment selection policy
- Semantic Fragment → Proposal 연결 로직
- nonempty_text 4건 중 Proposal에 포함된 fragment 수 감사 필요

**이 문제는 ASR Guard의 책임 범위 밖이다.**
다음 감사 대상: `ProposalEngine` / `SemanticFragment selection policy`

---

## 7. 이전 STEP 2-A-FINAL 대비 변화

| 항목 | STEP 2-A-FINAL (SRC_8826CB9E) | STEP 2-C Retest (SRC_616AEFBA) |
|------|-------------------------------|--------------------------------|
| nonempty_text | 7 | 4 |
| max_text_len | 2,731 (오염) | 40 (정상) |
| bad_row_count | 측정 불가 (Guard 미적용) | **0** |
| fallback_pct | 72.6% | 미측정 |
| CJK 텍스트 저장 | 발생 (VF7, VF13) | 차단 확인 |
| 반복 환각 저장 | 발생 (VF24 2,731자) | 차단 확인 |

---

## 8. 향후 조치

| 항목 | 담당 | 우선순위 |
|------|------|----------|
| ProposalEngine selection policy 감사 | STEP 2-D | 높음 |
| Whisper / faster-whisper 전환 검토 | STEP 2-B 이후 | 보통 |
| VAD silence_contamination Guard | STEP 2-E | 낮음 |
| Qwen3 역할 재정의 (분석/판단자) | 설계 확정 | 보통 |

---

## 9. 변경 금지 확인

- qwen3_asr_adapter.py: 본 보고서 작성 단계에서 미수정
- main.py: 미수정
- ProposalEngine: 미수정
- test_asr_filter.py: 미수정

---

본 보고서는 STEP 2-C ASR Guard Runtime Retest 공식 판정 문서입니다.
코드 변경을 수반하지 않습니다.
