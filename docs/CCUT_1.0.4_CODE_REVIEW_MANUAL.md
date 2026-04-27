# CCUT 1.0.4 공통 코드 검수 매뉴얼

## 목적
안티그래비티가 작업한 코드를 CCUT 1.0.4 기준으로 검수한다.

이 검수는 스타일 평가가 아니다.
이 검수는 성능 개선 제안이 아니다.
이 검수는 기능 추가 제안이 아니다.

오직 아래 기준 위반 여부만 확인한다.

---

# 1. 검수 기준 문서

반드시 아래 문서를 기준으로 검수한다.

docs/01_PROJECT_NAVIGATION_v3_2_1.md

---

# 2. 최우선 검수 원칙

다음 4가지만 본다.

1. Evidence 없이 Semantic 생성 여부
2. Semantic 없이 Proposal 생성 여부
3. Proposal 없이 Export 연결 여부
4. Resource Governor 우회 여부

---

# 3. 절대 금지 위반

- 기존 코드 삭제
- UI 선행 변경
- GPU/멀티워커 최적화 선행
- Evidence 없이 Fragment/Proposal 생성
- frontend heuristic Proposal 생성
- 하드코딩 경로
- D:/CCUT_1.0.3 참조
- Qwen main 직접 import
- Worker DB 직접 write
- fallback 없이 중단
- confidence/fallback_reason 누락

---

# 4. 필수 데이터 흐름

Video → Proxy → Segment → Evidence → Semantic → Intent → Proposal → ExportInput → Render

이외 흐름 = FAIL

---

# 5. 검수 보고 형식

## 최종 판정
PASS / FAIL / HOLD

## 핵심 위반

| 항목 | 결과 | 근거 |
|---|---|---|
| Evidence→Semantic | |
| Semantic→Proposal | |
| Proposal→Export | |
| Resource Governor | |

## 파일별 검수
- 파일:
- 역할:
- 변경:
- 판정:
- 문제:
- 근거:

## 수정 필요
1.
2.

## 진행 가능 여부
가능 / 불가능

---

# 6. 한 줄 기준

CCUT은 영상 → 의미 데이터 변환 시스템이다.
