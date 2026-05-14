# STEP 2-A-FINAL: Qwen3-ASR Runtime Audit 최종판정 보고서

**작성일**: 2026-05-14  
**브랜치**: ccut-1.0.4-step9  
**커밋**: 013c71cf8a6ae48c2664193b024f6affae342570  
**판정등급**: PARTIAL PASS / HOLD

---

## 1. 테스트 소스 정보

| 항목 | 값 |
|------|-----|
| source_id | `SRC_8826CB9E` |
| source 파일 | `D:\CCUT1.0.4\storage\uploads\TEST_ASR_0511.mp4` |
| duration | 1405.387755 초 |
| size | 1,094,117,681 bytes (~1.02 GB) |
| audio codec | AAC, 44100 Hz |

---

## 2. 소스 정상성 검증

- **파일 접근**: 정상
- **ffprobe 메타데이터**: duration / size / audio 모두 정상 반환
- **오디오 트랙**: AAC 44100 Hz — Qwen3-ASR 입력 요건 충족

---

## 3. Evidence Board 결과

| 항목 | 값 |
|------|-----|
| total evidence rows | 48 |
| nonempty_text | 7 |
| empty_text | 41 |
| max_text_len | 2,731 자 |

비고: 전체 48개 Evidence row 중 41개 (85.4%)가 빈 텍스트.  
유의미한 텍스트 저장은 7개에 그침.

---

## 4. Fragment Transcript 결과

| 항목 | 값 |
|------|-----|
| total fragments | 48 |
| nonempty_transcript | 7 |

Fragment 단위 전사 성공률: **14.6%** (7 / 48)

---

## 5. Semantic Fragment 결과

| 항목 | 값 |
|------|-----|
| total | 95 |
| real_summary (정상 요약) | 26 |
| fallback (폴백) | 69 |
| fallback_pct | **72.6%** |

fallback 비율이 72.6%로, Semantic Fragment의 대다수가 ASR 텍스트 부재로  
폴백 처리됨. 요약 품질 저하 직결.

---

## 6. Proposal 생성 결과

| Proposal | sequence_count |
|----------|---------------|
| A | 1 |
| B | 1 |

Proposal은 구조상 생성됨. 그러나 기반 Evidence 품질이 낮으므로  
편집 제안의 신뢰도는 담보되지 않음.

---

## 7. 오염 사례 (Quality Failure Cases)

### VF7 — 중국어 오인식

```
好一点，好一点。
```

- 한국어 음성을 중국어(Mandarin)로 오인식
- CJK 문자 100%, reject 대상

---

### VF13 — 반복 환각 (Repetition Loop)

```
对呀，反正就这样，就这样，就这样，就这样，就这样。
```

- 동일 phrase "就这样" 5회 이상 반복
- 중국어 오인식 + 반복 환각 복합 오염

---

### VF24 — "위에" 반복 환각 (2,731자)

```
위에, 위에, 위에, 위에, 위에, ... (2,731자)
```

- 단일 token "위에"가 수백 회 반복
- Evidence Board 최대 텍스트 길이(2,731자) 전체가 오염된 단일 토큰
- unique token ratio 약 0, token_count 매우 큼 → reject 명백

---

## 8. 최종 판정

| 판정 항목 | 결과 |
|-----------|------|
| Qwen3-ASR Adapter Contract Fix | **CODE PASS** |
| Qwen3-ASR Runtime | **PARTIAL PASS** |
| Qwen3-ASR Product Use | **HOLD** |

---

## 9. 판정 사유

### CODE PASS 근거

- Adapter 인터페이스 계약(반환 형식, DB 저장 경로)은 수정 후 정상 작동.
- `evidence_board.text` 컬럼에 텍스트가 저장되는 기술적 흐름 자체는 성공.

### PARTIAL PASS 근거

- 48개 fragment 중 7개에서 텍스트 저장 성공 (기능적으로 작동함을 확인).
- 그러나 저장된 텍스트 품질이 제품 사용 수준 미달.

### HOLD 근거

1. **중국어 오인식**: 한국어 음성을 Mandarin으로 오인식하는 구조적 문제.
2. **반복 환각 (Hallucination Loop)**: 동일 token/phrase 수백~수천 회 반복 생성.
3. **Word Timestamp 부재**: fragment 단위 시간 정렬 불가. Semantic Fragment 연동 불완전.
4. **fallback_pct 72.6%**: Semantic Pipeline 전반의 신뢰도 저하.

**결론**: Text-first 기본 ASR로서 Qwen3-ASR은 현 상태로 제품 사용 부적합.

---

## 10. 다음 단계

- ASR Text Quality Guard 설계 문서 참조 → `docs/ASR_TEXT_QUALITY_GUARD.md`
- Whisper / faster-whisper 기반 ASR 전환 검토 (STEP 2-B 이후)
- Qwen3는 텍스트 추출자 역할에서 **텍스트 분석/편집 판단자**로 역할 전환 검토

---

본 보고서는 STEP 2-A-FINAL 공식 판정 문서입니다. 코드 변경을 수반하지 않습니다.
