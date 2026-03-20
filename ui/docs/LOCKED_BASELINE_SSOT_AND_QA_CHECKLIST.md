# CCUT 1.0.2 — Locked Baseline SSOT & QA Checklist

## 1. 문서 목적

이 문서는 현재 CCUT 1.0.2에서 잠금된 인터랙션/구조 기준선을 **SSOT(Single Source of Truth)** 로 고정하기 위한 개발 문서다.

목표는 세 가지다.

1. 현재 무엇이 이미 확정되었는지 흔들리지 않게 고정한다.
2. 이후 안정화 작업과 polish 작업의 회귀 판단 기준을 명확히 만든다.
3. QA가 구현 상태를 Pass / Partial / Fail로 일관되게 판정할 수 있게 한다.

이 문서는 코드 설계 변경 문서가 아니라, **현재 검증 잠금 상태를 명시하는 기준 문서**다.

---

## 2. 현재 상태 요약

* 구조 편집 핵심 인터랙션은 모두 검증 잠금 완료
* `undo`는 `op-first / snapshot-fallback` 1단계 전환까지 완료
* `decision log`와 코어 구조는 이번 묶음에서 변경하지 않음
* 이후 단계는 새 우선순위가 정해지기 전까지 `구조 안정화 / 문서화 / polish`만 다룸

---

## 3. 기본 해석 원칙

### 3.1 구조 해석

* 현재 구현은 **CCUT 구조 철학을 잘 지킨 1차 완성본**으로 본다.
* `SyntheticCollapsedSeam`은 단순 seam이 아니라 **compressed structural chain의 표면 표현**으로 해석을 고정한다.
* 아래 잠금된 항목들은 모두 **회귀 금지 기준선**이다.

### 3.2 검증 원칙

* 검증은 항상 **작고 독립적인 단위**로 수행한다.
* 결과는 반드시 **Pass / Partial / Fail**로 판정한다.
* 가능하면 **DOM / state evidence** 기준으로 보고한다.
* 앱보다 검증 러너가 더 커지면 실패로 본다.
* 새로운 기능은 기존 interaction contract를 깨지 않는 범위에서만 허용한다.

### 3.3 금지 원칙

* combined runner 재도입 금지
* verification-only 파일 과증식 금지
* 앱보다 검증 도구가 더 복잡해지는 흐름 금지
* 새 기능을 기존 실패 원인의 우회 수단으로 쓰는 것 금지

---

## 4. 잠금된 기준선 14개

아래 14개는 현재 공식 **Pass 잠금 기준선**이다.

1. single click → focus-expand
2. same fragment click → restore
3. outside click → restore
4. double click → Time Lens
5. source recall only
6. normal boundary drag only
7. synthetic seam click → overlay open only
8. precision overlay internal boundary drag
9. replace-fragment UI only
10. Magnetic Fragment Flow only
11. Fragment Gravity System only
12. Time Lens sub-fragment preview only
13. pointer-based reorder only
14. undo op-first restore only

---

## 5. 기준선 상세 정의

### 5.1 single click → focus-expand

**의미**

* edit fragment를 single click 하면 해당 fragment가 focus-expand 상태로 들어간다.

**Pass 조건**

* 선택 fragment가 정확히 설정된다.
* detail panel이 focus-expanded 상태를 반영한다.
* 다른 경로(overlay, drag, replace)가 비의도적으로 열리지 않는다.

**회귀 금지 포인트**

* single click이 drag suppression에 의해 상시 무효화되면 안 된다.
* selected / focus state가 desync 되면 안 된다.

---

### 5.2 same fragment click → restore

**의미**

* 이미 focus-expanded인 같은 fragment를 다시 클릭하면 기본 상태로 복귀한다.

**Pass 조건**

* 같은 fragment 재클릭 시 focus-expanded 상태가 clean restore 된다.
* 선택 상태가 꼬이지 않는다.

**회귀 금지 포인트**

* 같은 fragment 재클릭이 중복 toggle loop를 만들면 안 된다.

---

### 5.3 outside click → restore

**의미**

* 외부 click으로 현재 active/focus view가 닫히고 idle 또는 기본 상태로 복귀한다.

**Pass 조건**

* outside interaction이 정상 restore를 일으킨다.
* overlay와 unrelated state를 건드리지 않는다.

---

### 5.4 double click → Time Lens

**의미**

* edit fragment double click 시 Time Lens 상태로 진입한다.

**Pass 조건**

* detail panel chip 또는 동등한 상태 표식이 `Time Lens`를 보여준다.
* 선택 fragment와 time lens 대상이 일치한다.

**회귀 금지 포인트**

* single click과 double click의 판정이 서로 오염되면 안 된다.

---

### 5.5 source recall only

**의미**

* edit fragment를 클릭하면 해당 fragment의 owning source가 원본 파노라마에 정확히 recall 된다.

**Pass 조건**

* `activeSource`가 대상 source로 전환된다.
* Original Panorama에서 해당 위치가 highlight 된다.
* selected fragment와 source recall 상태가 desync 되지 않는다.

---

### 5.6 normal boundary drag only

**의미**

* 인접 visible edit fragment 사이의 normal editable boundary를 drag 하면 양쪽 span이 반대 방향으로 변한다.

**Pass 조건**

* 예: `A2 / A3`처럼 양쪽 fragment duration이 함께 변화한다.
* fragment identity는 유지된다.
* selection / focus / timeLens는 안정 유지된다.
* seam / precision overlay path에 들어가지 않는다.

**회귀 금지 포인트**

* drag start만 되고 commit이 안 되는 상태 금지
* source guard가 normal boundary mutation을 막으면 안 됨

---

### 5.7 synthetic seam click → overlay open only

**의미**

* visible synthetic seam 클릭 시 local overlay가 열리고, hidden excluded chain이 드러나며, close가 clean 하게 동작한다.

**Pass 조건**

* visible synthetic seam이 존재한다.
* click 시 overlay가 정확히 열린다.
* excluded fragment를 포함한 chain id가 드러난다.
* close 후 overlay count가 0으로 돌아온다.

---

### 5.8 precision overlay internal boundary drag

**의미**

* 이미 열린 precision overlay 내부의 internal boundary drag 시, drag 중 local preview가 바뀌고 mouseup 후 main board commit이 일어난다.

**Pass 조건**

* drag 중 overlay local preview DOM이 실제로 바뀐다.
* mouseup 뒤 main board에 commit 된다.
* close가 정상 동작한다.
* main board는 preview 중 불안정하게 흔들리지 않는다.

**회귀 금지 포인트**

* preview 없이 commit만 되는 상태 금지
* overlay preview가 전역 board state를 오염시키면 안 됨

---

### 5.9 replace-fragment UI only

**의미**

* Hold Area의 source fragment를 Edit Structure의 target fragment 위에 drop 하면 `reserved -> edit` 교체가 일어난다.

**Pass 조건**

* Replace drag handle이 존재한다.
* target highlight가 뜬다.
* drop 후 source fragment가 edit로 들어간다.
* 기존 target fragment는 Hold Area로 이동한다.
* source hold position을 target이 승계한다.
* selected / active source / panorama selection이 새 fragment 기준으로 sync 된다.
* undo path가 동작한다.

**회귀 금지 포인트**

* reorder drag와 replace drag가 충돌하면 안 된다.

---

### 5.10 Magnetic Fragment Flow only

**의미**

* 구조 변화 시 fragment / boundary / seam이 이전 위치에서 새 위치로 자연스럽게 밀리고 안착한다.

**Pass 조건**

* replace와 reorder 둘 다에서 reflow가 보인다.
* fragment만이 아니라 boundary / seam도 같은 flow에 포함된다.
* 최종 settle 후 transform이 0,0으로 clean 하게 정리된다.

**회귀 금지 포인트**

* instant jump만 있고 flow가 없으면 안 된다.
* overlay path가 섞이면 안 된다.

---

### 5.11 Fragment Gravity System only

**의미**

* reorder drag 중 nearest structural slot 기준으로 target index가 안정적으로 계산된다.

**Pass 조건**

* tile 위와 board gap에서 같은 gravity index가 나온다.
* 작은 jitter에도 target slot wobble이 없다.
* 최종 reorder 결과가 gravity slot과 정확히 일치한다.
* Magnetic Flow가 유지된다.

**회귀 금지 포인트**

* midpoint 흔들림으로 target slot이 불안정하면 안 된다.

---

### 5.12 Time Lens sub-fragment preview only

**의미**

* Time Lens 상태일 때만 fragment 내부를 4~5개 sub-window로 나눠 frame range / duration을 읽기 전용으로 보여준다.

**Pass 조건**

* double click 후 Time Lens open 상태에서만 렌더된다.
* selected fragment와 같은 대상에 대해서만 보인다.
* window 개수가 4~5개다.
* 각 window에 frame range와 duration이 표시된다.
* selection change 또는 outside close 시 clean clear 된다.

**회귀 금지 포인트**

* mini-timeline처럼 편집 기능으로 확장되면 안 된다.

---

### 5.13 pointer-based reorder only

**의미**

* edit reorder drag는 pointer 기반으로 시작되며, 6px threshold를 넘을 때만 reorder mode가 활성화된다.

**Pass 조건**

* 6px 이하에서는 reorder drag가 시작되지 않는다.
* 6px 초과에서만 reorder drag가 활성화된다.
* drag 중 gravity slot target이 정상 추적된다.
* pointerup 시 최신 slot으로 reorder commit 된다.
* drag 직후 click suppression이 1회만 적용된다.
* single click / double click / Time Lens / replace / overlay 계약이 유지된다.

**회귀 금지 포인트**

* stale state 때문에 pointerup commit이 빠지면 안 된다.

---

### 5.14 undo op-first restore only

**의미**

* undo/redo는 op 기반 복원을 우선 시도하고, 조건이 맞지 않으면 snapshot 복원으로 fallback 한다.

**Pass 조건**

* `reorder / replace-fragment / boundary-resize / precision-boundary`는 `[op/undo] / [op/redo]`로 복원된다.
* `exclude / restore / move-to-hold / restore-from-hold / hold-area-reposition`은 snapshot fallback으로 안전하게 유지된다.
* 기존 interaction contract가 깨지지 않는다.

**회귀 금지 포인트**

* op-first 실패 시 조용한 fallback이 안 되면 안 된다.
* snapshot을 즉시 제거하면 안 된다.

---

## 6. 현재 남은 기술부채

아래는 현재 공식 기술부채다.

1. `HTML5 DnD`
2. drag 중 rerender 여지
3. full-snapshot undo의 잔여 의존

### 해석

* 현재 단계에서는 허용 가능
* 하지만 장기적으로는 구조적으로 축소 / 교체 대상이다

### 현재 snapshot-only로 남겨둔 경로

* `exclude`
* `restore`
* `move-to-hold`
* `restore-from-hold`
* `hold-area-reposition`

---

## 7. QA 체크리스트

### 7.1 기본 interaction

* [ ] single click → focus-expand
* [ ] same fragment click → restore
* [ ] outside click → restore
* [ ] double click → Time Lens
* [ ] source recall only

### 7.2 구조 편집 interaction

* [ ] normal boundary drag only
* [ ] synthetic seam click → overlay open only
* [ ] precision overlay internal boundary drag
* [ ] replace-fragment UI only
* [ ] pointer-based reorder only

### 7.3 보드 구조 동작

* [ ] Magnetic Fragment Flow only
* [ ] Fragment Gravity System only
* [ ] Time Lens sub-fragment preview only

### 7.4 undo/redo

* [ ] undo op-first restore only
* [ ] snapshot fallback path non-regression

### 7.5 공통 비회귀

* [ ] seam/precision overlay 비의도 진입 없음
* [ ] replace와 reorder 경로 충돌 없음
* [ ] drag 후 click suppression 오염 없음
* [ ] active source / selection / panorama sync 유지

---

## 8. 검증 순서 원칙

이후 새 작업이나 안정화 작업이 생기면 검증은 다음 원칙을 따른다.

1. 기존 잠금 기준선을 먼저 확인한다.
2. 새 변경은 가능한 한 **하나의 독립된 계약**으로 나눈다.
3. 구현 후에는 해당 계약만 따로 검증한다.
4. 필요한 경우에만 최소한의 verification-only 업데이트를 한다.
5. 기존 14개 기준선이 깨지면 새 기능은 잠그지 않는다.

---

## 9. 이후 작업 범위

새 우선순위가 정해지기 전까지는 아래만 다룬다.

### 9.1 구조 안정화

* ref/state drift 정리
* cleanup 누락 정리
* stale closure 가능성 정리
* drag / overlay lifecycle 정리
* 중복 상태 축소

### 9.2 문서화

* 이 문서 유지
* QA 체크리스트 확장
* 구현 변경 시 기준선 diff 기록

### 9.3 polish

* motion finishing
* spacing 정리
* wording 정리
* focus / hover / keyboard / accessibility finishing

### 금지

* 새로운 구조 기능을 임의로 추가하지 않는다.
* 새 우선순위 합의 없이 큰 아키텍처 이동을 하지 않는다.

---

## 10. 최종 상태 선언

현재 CCUT 1.0.2의 구조 편집 핵심 인터랙션 묶음은 다음 상태로 본다.

* 구조 편집 핵심 인터랙션: **검증 잠금 완료**
* undo 하이브리드 1단계: **검증 잠금 완료**
* decision log / core structure: **비변경 유지**
* 이후 단계: **구조 안정화 / 문서화 / polish만 허용**

이 문서는 이후 안정화와 polish 작업의 회귀 판단 기준으로 사용한다.
