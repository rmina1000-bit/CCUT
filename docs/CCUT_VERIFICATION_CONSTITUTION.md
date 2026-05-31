# CCUT_VERIFICATION_CONSTITUTION.md
# CCUT 검증 헌법 (영구 운영 규칙 — 코드보다 상위)

> 방을 이전해도, 세션이 초기화돼도 반드시 유지된다. Claude·안티2·ChatGPT 모두에게 강제된다. 행동 규칙 세부는 `AGENT_EVIDENCE_RULES.md`, 현재 검증 상태는 `CCUT_VERIFICATION_STATUS_TABLE.md` 참조.

## 0. 존재 이유 (잊지 말 것)
2026-05-31, 안티2가 브라우저를 띄우지 않고 `match=true`·"실시간 검증 시작"이라 보고했고, Claude가 그 텍스트를 "확정"으로 국장께 전달했다. 국장이 화면을 직접 보고 있었기에 적발됐다. mock을 막는 firewall은 있었으나 **"실제로 브라우저를 실행했는지 증명"하는 시스템이 없었다.** 이 헌법이 그 구멍을 막는다.

```
텍스트는 위조된다. 실행 부산물과 국장의 눈은 위조되지 않는다.
타이머·"passed"·"match=true"·"실행 중"·"실측 완료"는 증거가 아니다.
mock 통과는 "로봇 생존"일 뿐, 제품 검증이 아니다.
```

## 1. PASS 3등급 (절대 섞지 말 것)

| 등급 | 조건 | 의미 |
|---|---|---|
| **SCRIPT PASS** | 테스트 실행됨. mock 가능. | 컴파일·실행됨. **제품 PASS 아님.** |
| **EVIDENCE PASS** | trace.zip + video.webm + screenshot + console.txt + network log + **timestamp(지시시각 이후)** 전부 존재 | 진짜 브라우저 실행이 위조불가 부산물로 증명됨. |
| **PRODUCT PASS** | 국장이 **실제 브라우저 화면에서 직접** 봄 | 최종. 사용자 경험 확정. |

**루프:** 평소 회귀·반복 = EVIDENCE / 핵심·최종 = PRODUCT. (2차 EVIDENCE → 1차 PRODUCT)

## 2. 위조불가 증거 정의 (EVIDENCE PASS 세부)
1. **trace.zip** — 실행 안 하면 존재 불가. network·DOM·console 포함. **timestamp가 지시 이후**(옛 부산물 재활용 차단). **진짜 프로젝트** network 요청 포함.
2. **video.webm** — **국장이 재생해 직접** 봄(안티2가 "닭 아님" 말하는 것 금지).
3. **screenshot PNG** — **국장이 Claude에 업로드 → Claude 픽셀 검수.** 안티2 채팅 PNG 주장은 단독 증거 아님.
4. **state.json** — 진짜 `P_SF_` ID·DOM `currentSrc` 실측. mock ID(`SF_A_1`)면 무효.
5. **timestamp** — 모든 부산물이 이 배치 지시 이후.

## 3. 금지 (위반 시 자동 반려)
```
타이머 = 증거 아님.
"passed"·"PASS"·"match=true"·"실행 중"·"실측 완료" 텍스트 = 증거 아님.
expected === actual 자기비교 금지(한쪽은 DOM raw).
옛 부산물 재활용 금지(timestamp 차단).
mock 녹화를 PRODUCT 근거로 금지(state.json 진짜ID로 교차).
SCRIPT/EVIDENCE/PRODUCT 등급 섞기 금지.
국장이 못 본 것을 PRODUCT PASS라 선언 금지.
```

## 4. ★매 작업지시서 삽입 블록 (Claude는 모든 지시서에 이 블록을 넣는다)
```
[검증 헌법]
- 텍스트 보고는 증거가 아니다. 타이머·passed·match=true·실행 중도 아니다.
- SCRIPT PASS ≠ 제품 PASS.
- EVIDENCE PASS = trace.zip / video.webm / screenshot / console / network / timestamp 전부 존재.
- PRODUCT PASS = 국장이 실제 브라우저에서 직접 확인.
- 안티2는 PASS를 선언하지 말고 증거만 제출한다. 판정은 국장·Claude.
- expected를 양쪽에 박는 자기비교 금지. 한쪽은 DOM raw 실측.
```

## 5. 방이전 시
이 문서 + `CCUT_VERIFICATION_STATUS_TABLE.md` + `AGENT_EVIDENCE_RULES.md`를 방이전 전달문에 **반드시 포함**. 새 방 Claude는 즉시 `AGENT_EVIDENCE_RULES.md`의 Claude 자기강제 규칙을 적용한다.

**한 줄:** CCUT은 "코드가 돈다"가 아니라 **"국장의 눈과 위조불가 증거로 확인된다"**를 완성 기준으로 한다.
