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

## 4-1. 브라우저 DOM 실측 절차 (EYE-01 2026-08-02 확정)

실행자가 화면을 스스로 재는 방법. **이 절차 밖으로 나가면 여섯 차수를 헛되이 쓴다.**

```
찾기   document.querySelectorAll('[role="button"]') + textContent 매칭
클릭   element.click()          (좌표 클릭보다 확실)
측정   getBoundingClientRect / scrollTop / scrollHeight / querySelectorAll
```

**★ innerText 절대 금지.**
`document.visibilityState === "hidden"` 인 창(브라우저 pane 미표시 등)에서는
`innerText` 가 **항상 빈 문자열**을 반환한다. 레이아웃 의존 API 이기 때문이다.
`textContent` · `getBoundingClientRect` · `click()` 은 같은 조건에서 정상 동작한다.

**★ 접근성 트리의 "button" 을 실제 `<button>` 태그로 믿지 마라.**
`read_page` 류가 `button "Freesia"` 로 보여주는 것이 DOM 에서는
`<div role="button">` 일 수 있다. 태그를 직접 확인하고 셀렉터를 정한다.

### 이 절차가 나온 경위 (되풀이 방지용 기록)
2026-08-02, 실행자가 여섯 차수 연속 "브라우저 pane 미표시로 실측 불가"라고 보고했다.
증상은 `버튼 17x17` · `textContent 공백` · `프로젝트 클릭 무반응` 이었다.
국장 지시서도 "pane 미표시 → 레이아웃 계산 정지"를 유력 가설로 적었다.

실측으로 **둘 다 틀렸다**:
- `bodyRect 1280x720`, 프로젝트 항목 `rect 215x58` — 레이아웃은 한 번도 멈추지 않았다
- 17x17 짜리는 사이드바 **아이콘 버튼**이었다. 엉뚱한 것을 재고 있었다
- 프로젝트 항목은 `<div role="button">` 이라 `querySelectorAll('button')` 에 안 잡혔다

**환경 제약이 아니라 실행자의 셀렉터 오류였다.**
"도구 탓"이 여섯 번 반복되면 도구가 아니라 자기 사용법을 의심한다.

### 이 절차로도 못 재는 것
"보기 좋은가" 는 여전히 국장 몫이다. DOM 수치는 구조·순서·개수·좌표를 증명할 뿐
미감을 증명하지 않는다. PRODUCT PASS 기준은 그대로다.

## 4-2. 자동 화면 검증 계약 (EYE-02 2026-08-02 확정)

§4-1 이 "어떻게 찾는가"였다면 이 절은 **"무엇을 좌표로 삼는가"**와
**"이 환경에서 무엇이 죽어 있는가"**다. 앞 절과 함께 읽는다.

### (1) 찾기 — 태그명으로 찾지 않는다
```
찾는다   [role="button"] · accessible name(textContent 매칭) · 고유 식별자(data-*)
안 찾는다 querySelectorAll('button')  — 대상이 <div role="button"> 이면 0건이 나온다
읽는다   textContent      (hidden 창에서도 정상)
안 읽는다 innerText        (visibilityState==="hidden" 이면 항상 빈 문자열)
```
data-* 를 심을 수 있으면 그것이 가장 확실하다. 이번 차수의 접힘 대상은
제품 코드가 이미 `data-fold-id` 를 달고 있어 `[data-fold-id="transcript"]` 한 줄로 잡혔다.

### (2) 좌표 규약 — 두 질문에 두 좌표
```
"제자리에 있는가"   documentY = rect.top + scrollTop     ← 문서 좌표
"화면이 튀는가"     rect.top                              ← 화면 좌표
scrollTop           원시값으로 제출만 한다. ★단독 PASS 기준 금지
```
scrollTop 이 변해도 앵커의 `rect.top` 이 안 움직였으면 화면은 안 튄 것이다.
브라우저 스크롤 앵커링이 위쪽 높이 변화를 보정하면 scrollTop 은 당연히 변한다 —
그것을 실패로 읽으면 없는 결함을 만든다.

### (3) ★이 환경에서 죽어 있는 API (EYE-02 실측)
브라우저 pane 이 표시되지 않으면 **합성(compositing)이 멈춘 것**이지
레이아웃이 멈춘 것이 아니다(§4-1 에서 확인). 그래서 갈린다:

| 살아 있다 | 죽어 있다 |
|---|---|
| `textContent` | `innerText` (항상 "") |
| `getBoundingClientRect` (bodyRect 1280x720) | `requestAnimationFrame` (1200ms 내 0회 발화) |
| `element.click()` | `IntersectionObserver` (독립 프로브 2000ms 0회 콜백) |
| `setTimeout` | `scrollIntoView({behavior:"smooth"})` (1500ms 후 이동 0px) |
| `el.scrollTop = N` 대입 | `computer{action:"screenshot"}` (5s timeout) |
| `scrollIntoView({behavior:"auto"})` (5000 → 18701 즉시) | |

**결론: 화면 합성에 의존하는 기능은 이 환경에서 측정하지 않는다.**
IntersectionObserver 로 판정하는 자동 접힘(CHAT-FOLD), rAF 로 도는 애니메이션,
smooth 스크롤은 **결과가 아니라 환경을 재게 된다.** 재면 반드시 거짓 FAIL 이 나온다.
막혔으면 그 항목만 `MEASURE_BLOCKED` 로 적고 나머지를 완주한다.

★죽었다고 선언하기 전에 **독립 프로브를 하나 세운다.** 제품 코드의 관찰자가 안 도는 것과
브라우저가 안 돌리는 것은 다른 이야기다. 이번에는 같은 root·rootMargin 으로
IntersectionObserver 를 하나 더 달아 0콜백을 확인한 뒤에야 환경 탓이라고 적었다.
그 프로브가 없으면 §4-1 이 경고한 "여섯 차수 도구 탓"으로 되돌아간다.

### (4) 이번에 실제로 통한 것 / 실패한 것 (raw)
```
통함  document.querySelectorAll('[role="button"]')            -> 10건, 전부 DIV, rect 215x58
통함  textContent 매칭 startsWith('Freesia') + el.click()     -> 프로젝트 진입 성공
통함  [data-fold-id] 로 채팅 스크롤 컨테이너 역추적            -> overflow-y:auto 조상
통함  DOM 노드에 data-m-id 를 직접 심어 전후 매칭              -> React 가 지우지 않음, 173건 추적
통함  textarea 에 네이티브 value setter + input + Enter keydown -> 실제 전송 성공
실패  requestAnimationFrame 루프로 접힘 순간 샘플링            -> 30s 타임아웃 (프레임 0)
실패  computer{action:"screenshot"}                            -> 5s 타임아웃
실패  scrollIntoView({behavior:"smooth"})                      -> 1500ms 후 0px
```

### (5) 그래도 못 재는 것
"보기 좋은가"는 여전히 국장 몫이다(§4-1 과 동일). 여기에 하나가 더 붙는다 —
**합성이 멈춘 환경에서는 "움직임"을 못 잰다.** 최종 위치는 재도 경로는 못 잰다.

## 5. 방이전 시
이 문서 + `CCUT_VERIFICATION_STATUS_TABLE.md` + `AGENT_EVIDENCE_RULES.md`를 방이전 전달문에 **반드시 포함**. 새 방 Claude는 즉시 `AGENT_EVIDENCE_RULES.md`의 Claude 자기강제 규칙을 적용한다.

**한 줄:** CCUT은 "코드가 돈다"가 아니라 **"국장의 눈과 위조불가 증거로 확인된다"**를 완성 기준으로 한다.
