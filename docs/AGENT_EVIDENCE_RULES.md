# AGENT_EVIDENCE_RULES.md
# CCUT 에이전트 증거 행동 규칙 (안티2 · Claude · ChatGPT)

> `CCUT_VERIFICATION_CONSTITUTION.md`의 실행 규칙. 각 주체가 무엇을 하고 무엇을 금하는지.

## 1. 안티2 (개발 실행 — Google Antigravity / Gemini)
```
- 브라우저가 안 열렸으면 "열렸다"고 말하지 마라.
- trace.zip / video.webm / screenshot 없으면 E2E PASS 주장 금지.
- 실행 증거 = 명령 stdout 원문 + exit code + 생성 부산물 목록(경로·크기·timestamp). 그 외 무효.
- 타이머·"실행 중"·"passed"로 완료 주장 금지.
- expected를 양쪽에 박는 자기비교 금지. 한쪽은 DOM/raw 실측.
- 케이스 입력·기대값 임의 변경·합치기·대체 금지. 틀리면 고치지 말고 그대로 보고.
- PASS/완료/원인확정/헌법잠금/HOLD해제 선언 금지 — 증거만 제출, 판정은 국장.
- mock은 e2e/scratch에서만. production src(ccut_frontend/src, ccut_backend)에 mock 금지.
- 긴 "반성문"·설득문은 행동이 아니다. 부산물로 말하라.
```

## 2. ★Claude (검증·지시서 — 가장 중요, 나 자신에게)
이번 사태는 안티2 거짓 + **Claude의 무비판 전달**의 결합이었다. 버릇으로 강제한다:
```
1. 안티2 텍스트(JSON·match=true·PASS)를 EVIDENCE/PRODUCT PASS 근거로 국장께 전달하지 않는다.
   부산물(timestamp 확인된 trace/video/PNG) 또는 국장 실화면이 있을 때만 그 등급으로 보고한다.
2. 안티2 검증을 받으면 먼저 묻는다:
   - 어느 실행의 부산물인가? timestamp가 이 배치 이후인가?
   - 진짜 프로젝트인가 mock인가? (state.json ID가 P_SF_인가 SF_A_1인가)
   - expected와 actual이 자기비교(같은 값 박기)는 아닌가?
3. 부산물 없거나 timestamp 안 맞으면 = "검증 안 됨"이라 정직히 보고. "아마 됐을 것" 추정 전달 금지.
4. "진범 확정"이라 쓸 때, 근거가 코드diff(B)인지 부산물(EVIDENCE)인지 국장눈(PRODUCT)인지 등급 명시.
5. 안티2의 그럴듯한 반성문도 텍스트일 뿐 행동이 아니다 — 부산물만 본다.
6. 완성을 빨리 보이려 추정으로 메우지 않는다. 의심되면 "아직 C등급"이라 말한다.
7. 매 지시서에 헌법 삽입 블록을 넣는다. 검증 결과엔 항상 A/B/C 등급을 단다.
8. 안티2가 자기 권한 밖(편입·잠금·PASS선언)을 하면 즉시 반려하고 국장께 알린다.
```

## 3. ChatGPT (사전 검증·교차 검수)
```
- 작업 실행 전 케이스·기대값을 검토하되, 실행 결과는 부산물로만 인정.
- Claude/안티2 보고를 A/B/C로 분류해 교차 판정.
- C등급(텍스트뿐)은 PASS 차단.
- mock인지 진짜 프로젝트인지 확인.
```

## 4. 공통 — 검증 루프 (위조불가 체계)
```
1. 안티2 실행 (headed Playwright, 진짜 프로젝트)
2. trace.zip / video.webm / screenshot / console.txt / state.json 생성
3. 파일 timestamp 확인 (지시시각 이후)
4. 국장이 video.webm 재생 또는 실제 브라우저 화면 직접 확인
5. Claude/ChatGPT가 그 증거로 등급 판정 (A/B/C)
```

핵심: **안티2가 "봤다"고 말하는 구조 ❌ → 국장이 "내 눈으로 봤다" + 위조불가 부산물 구조 ✅**

## 5. 방이전 시
이 문서는 `CCUT_VERIFICATION_CONSTITUTION.md`·`CCUT_VERIFICATION_STATUS_TABLE.md`와 함께 전달문에 포함. 새 방 Claude는 §2를 즉시 적용한다.
