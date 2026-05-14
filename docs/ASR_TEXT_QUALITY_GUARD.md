# ASR Text Quality Guard — 설계 문서

**버전**: v0.1 (설계 단계)  
**작성일**: 2026-05-14  
**단계**: STEP 2-B-0  
**상태**: DESIGN PASS 후보

---

## 1. 목적

Raw ASR 출력을 **그대로 Evidence Board에 입력하지 않는다.**

Qwen3-ASR(및 향후 모든 ASR Provider)의 출력은 반드시  
품질 검증 단계를 통과한 `accepted_text`만 Evidence로 승격한다.

```
[ASR Adapter 반환]
       |
[ASR Text Quality Guard]  <-- 본 문서의 적용 위치
       |
[accepted_text --> Evidence Board 저장]
[rejected_text --> reject_reason 기록, Evidence 미저장]
```

---

## 2. 데이터 분리 구조

Evidence Row에 다음 필드를 분리하여 관리한다.

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `raw_asr_text` | str | ASR Adapter가 반환한 원본 텍스트 (무조건 보존) |
| `accepted_text` | str 또는 null | 품질 검증 통과 텍스트 (Evidence 승격 대상) |
| `rejected_text` | str 또는 null | 품질 검증 실패 텍스트 (Evidence 미승격) |
| `reject_reason` | str 또는 null | 거부 사유 코드 (예: `repetition_loop`, `cjk_contamination`) |
| `language` | str | 감지된 언어 코드 (예: `ko`, `zh`, `unknown`) |
| `provider` | str | ASR 제공자 (예: `qwen3`, `whisper`, `faster-whisper`) |
| `quality_flags` | list[str] | 복합 품질 플래그 목록 |

원칙: `raw_asr_text`는 감사/디버그 목적으로 항상 보존.  
Evidence Board 노출 텍스트는 `accepted_text`만 사용.

---

## 3. Reject 조건

아래 조건 중 **하나라도** 해당하면 해당 텍스트는 REJECTED 처리한다.

### 3-1. CJK 오염 (한자/중국어 오인식)

```
condition: CJK 문자 수 >= 4
reject_reason: "cjk_contamination"
```

```
condition: CJK 문자 비율 > 15%
reject_reason: "cjk_ratio_exceeded"
```

대상 CJK 범위: U+4E00 ~ U+9FFF (CJK Unified Ideographs)

---

### 3-2. 반복 환각 (Repetition Loop)

```
condition: 동일 token이 10회 이상 연속 또는 누적 반복
reject_reason: "repetition_loop"
```

```
condition: unique_token_ratio < 0.2 AND token_count > 20
reject_reason: "low_unique_token_ratio"
```

예시:
- "위에, 위에, 위에..." (2,731자) → `repetition_loop`
- "就这样, 就这样..." → `repetition_loop` + `cjk_contamination`

---

### 3-3. 비정상 길이 (Length Anomaly)

```
condition: 30초 기준 500자 초과
reject_reason: "length_exceeded"
```

계산식: `len(text) / duration_sec > (500 / 30)`  
한국어 평균 발화 속도 기준 상한치.

---

### 3-4. Silence 구간 오염

```
condition: 구간이 silence/no-speech 판정이고 text가 존재
reject_reason: "silence_contamination"
```

speech_activity 메타데이터 필요. 향후 VAD 연동 시 적용.

---

### 3-5. Empty Text

```
condition: text == "" 또는 text.strip() == ""
action: Evidence 저장하지 않음 (silent skip)
reject_reason: "empty_text"
```

빈 텍스트는 Evidence row 자체를 생성하지 않는다.

---

## 4. Accept 조건

다음 기준을 **모두** 만족해야 `accepted_text`로 승격한다.

| 조건 | 설명 |
|------|------|
| 언어 | 한국어(ko) 중심 텍스트 |
| 반복 없음 | unique_token_ratio >= 0.2 또는 token_count <= 20 |
| 길이 정상 | 30초 기준 500자 이하 |
| Speech 일치 | speech 구간에서 발생한 텍스트 |
| 의미 있는 내용 | 단일 음절/단어 단독 나열이 아닌 구/문장 |

---

## 5. 결과 구조 예시

### ACCEPTED 케이스

```json
{
  "fragment_id": "VF03",
  "raw_asr_text": "그래서 이 부분이 핵심인데요.",
  "accepted_text": "그래서 이 부분이 핵심인데요.",
  "status": "ACCEPTED",
  "language": "ko",
  "provider": "qwen3",
  "reject_reason": null,
  "quality_flags": []
}
```

### REJECTED 케이스 — 반복 환각

```json
{
  "fragment_id": "VF24",
  "raw_asr_text": "위에, 위에, 위에, 위에, 위에...(2731자)",
  "accepted_text": "",
  "status": "REJECTED",
  "language": "ko",
  "provider": "qwen3",
  "reject_reason": "repetition_loop",
  "quality_flags": ["repetition_loop", "length_exceeded"]
}
```

### REJECTED 케이스 — CJK 오염

```json
{
  "fragment_id": "VF07",
  "raw_asr_text": "好一点，好一点。",
  "accepted_text": "",
  "status": "REJECTED",
  "language": "zh",
  "provider": "qwen3",
  "reject_reason": "cjk_contamination",
  "quality_flags": ["cjk_contamination", "cjk_ratio_exceeded"]
}
```

### REJECTED 케이스 — CJK + 반복 복합

```json
{
  "fragment_id": "VF13",
  "raw_asr_text": "对呀，反正就这样，就这样，就这样，就这样，就这样。",
  "accepted_text": "",
  "status": "REJECTED",
  "language": "zh",
  "provider": "qwen3",
  "reject_reason": "cjk_contamination",
  "quality_flags": ["cjk_contamination", "repetition_loop"]
}
```

---

## 6. 적용 위치

```
ASR Adapter (qwen3_asr_adapter.py)
    |  반환: raw transcript dict
ASR Text Quality Guard  <-- 여기에 삽입
    |  반환: {accepted_text, status, reject_reason, quality_flags}
Evidence Board Writer
    |  evidence_board.text <- accepted_text만 저장
```

설계 기준 위치: ASR Adapter 반환 직후, `evidence_board.text` 저장 전.  
Guard는 별도 모듈(`asr_text_quality_guard.py`)로 분리하여 독립 테스트 가능하게 설계.  
Guard 호출은 `ingest_pipeline` 또는 ASR 처리 레이어에서 단일 진입점으로 관리.

주의: 현 단계에서는 설계만 확정. 코드 구현은 다음 단계(STEP 2-B-1 이후)에서 진행.

---

## 7. 향후 방향

### ASR Provider 전환

| Provider | 상태 | 비고 |
|----------|------|------|
| Qwen3-ASR | **HOLD** | 한국어 오인식/환각 문제로 Text-first ASR 부적합 |
| Whisper (OpenAI) | 검토 예정 | 다음 단계 후보 |
| faster-whisper | 검토 예정 | 경량화 / 로컬 운용 가능 |

### Qwen3 역할 재정의

- **현재 역할 (HOLD)**: 음성 → 텍스트 변환 (ASR)
- **향후 역할 (검토)**: 텍스트 분석 / 편집 판단자
  - Whisper 전사 결과를 받아 요약/편집 판단 수행
  - Semantic Fragment 요약, Proposal 랭킹에 활용
  - 직접 전사는 수행하지 않음

### Quality Guard 확장

- VAD(Voice Activity Detection) 연동으로 silence 구간 자동 감지
- 다국어 혼합 발화 처리 로직 추가
- Guard 통과율 메트릭을 Audit Report에 자동 포함

---

## 8. 변경 금지 항목 (현 단계)

다음 파일은 본 설계 문서 단계에서 수정하지 않는다.

- `qwen3_asr_adapter.py` — 수정 금지
- `main.py` — 수정 금지
- `ProposalEngine` 관련 모듈 — 수정 금지
- Factory Matrix 구현 — 금지
- Runtime PASS 선언 — 금지

---

본 문서는 STEP 2-B-0 설계 확정 문서입니다. 구현은 STEP 2-B-1 이후 별도 작업지시서에 따릅니다.
