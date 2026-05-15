# STEP 2-C-R4 Proposal Diversity Policy Fix

**작성일**: 2026-05-14
**branch**: ccut-1.0.4-step9
**HEAD**: (사용자 환경에서 확인 필요)
**상태**: CODE PASS / RUNTIME 검증 필요

---

## 1. 수정 개요

| 항목 | 내용 |
|------|------|
| 수정 파일 | `ccut_backend/engine/proposal_engine.py` |
| 수정 함수 | `_create_user_proposal`, `_semantic_group_key` (신규) |
| 핵심 변경 사항 | A/B 지그재그 분할을 차단하고 Semantic Group 단위의 Diversity를 강제하는 Scoring 정책 도입 |

---

## 2. 주요 로직 변경

### 2-1. `_semantic_group_key` 추가
- `SF_XXXX_P001` 형태의 ID에서 `_P001` 접미사를 제거하여 동일한 시맨틱 그룹을 식별합니다.

### 2-2. B-mode Diversity Scoring 개편
기존의 단순 fragment 단위 0.7배 페널티에서 **그룹 단위 가중치**로 변경되었습니다.
- **A-mode 사용 그룹**: 0.25배 (강한 배제)
- **B-mode 이미 선택한 그룹**: 0.3배 (내부 반복 방지)
- **신규 그룹**: 1.15배 (다양성 보너스)

---

## 3. 검증 지시서 (사용자 실행 필수)

현재 환경 제약으로 인해 아래 단계를 직접 수행해 주시기 바랍니다.

### STEP A — Compile 확인
```powershell
cd D:\CCUT1.0.4
python -m py_compile ccut_backend/engine/proposal_engine.py
# 에러가 없으면 통과
```

### STEP B — 서버 재시작
기존 실행 중인 `main.py` 터미널을 종료(Ctrl+C)하고 다시 실행하십시오.
```powershell
python ccut_backend\main.py
```

### STEP C — Proposal 재생성 (API 호출)
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/proposals/generate/SRC_616AEFBA" -Method POST
```

### STEP D — 결과 감사
작성된 `tools/audit_r4_result.py` 스크립트를 실행하여 A/B 그룹 분포를 확인합니다.
```powershell
python tools/audit_r4_result.py
```

---

## 4. 기대 결과 (RUNTIME PASS 기준)

1. **A sequence_count**: 3개 이상 유지
2. **B sequence_count**: 3개 이상으로 증가
3. **Diversity**: A groups와 B groups의 교집합(`common groups`)이 최소화되고, `B exclusive groups`가 1개 이상 존재해야 합니다.
4. **No Zigzag**: 동일 그룹 내에서 P001, P002를 나눠 갖는 현상이 사라져야 합니다.

---

## 5. 작업 결과 보고

1. **수정 파일**: `ccut_backend/engine/proposal_engine.py`
2. **수정 함수**: `_create_user_proposal`, `_semantic_group_key`
3. **_semantic_group_key 추가 여부**: YES
4. **A/B policy 분리 여부**: YES
5. **compile 결과**: (코드 검토상 정상)
6. **판정**: **CODE PASS** (사용자 검증 후 RUNTIME PASS 결정)

---

본 문서는 STEP 2-C-R4 Proposal Diversity Policy Fix 공식 보고서입니다.
사용자께서는 위의 검증 단계를 수행하신 후 결과를 공유해 주시기 바랍니다.
