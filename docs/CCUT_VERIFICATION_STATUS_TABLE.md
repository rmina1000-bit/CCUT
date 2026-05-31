# CCUT_VERIFICATION_STATUS_TABLE.md
# CCUT 검증 상태표 (A/B/C 등급 기록 — 살아있는 문서, 매 검증 후 갱신)

> 규칙은 `CCUT_VERIFICATION_CONSTITUTION.md`. 이 문서는 **현재까지 무엇이 어느 등급인지** 기록한다.
> **A** = 국장 실화면 직접 확인 / **B** = 위조불가 부산물(git diff·firewall EXIT·국장 콘솔 스크린샷) / **C** = 안티2 텍스트뿐(PASS 금지)
> 최종 갱신: 2026-05-31

---

## 1. 믿을 수 있는 것 (A / B)

| 항목 | 등급 | 근거 |
|---|---|---|
| 조각맵 썸네일 404 해소 (D5-REAL) | A+B | 국장 콘솔 스크린샷 `THUMB_RESOLVE naturalWidth=1080/1920 fallbackUsed=0`(진짜 P_SF_ ID), 조각맵 실제 풍경 썸네일 |
| 비례바창 열림 (회귀수정) | A | 국장 실화면 — 경계 클릭 시 PBE 모달 열림 |
| 클릭 정합성 (A2\|A3→A2\|A3) | A | 국장 실화면 image6, 모달 제목 `A2 \| A3` |
| apply 후 짧은 라벨 | A | 국장 실화면 — apply 거치면 A1·A1_M·A2 |
| firewall 무기 (mock 자동차단) | B | EXIT=0/1 정확 동작, 실제로 오염 잡아냄 |
| 진범 위치들 (각종 getVideoUrlForFrag·activeVideoUrl·display_id) | B | git diff·코드 원문으로 확정 |

**주의:** D5 썸네일은 전역캐시(`window.__ccut_thumbnail_cache`) 방식 — 단일진실원천 위배, 정리 대기.

---

## 2. 못 믿는 것 (C — PASS 취소 / 재검증 대기)

| 항목 | 왜 C인가 |
|---|---|
| PBE-PLAYBACK 재생영상 수리 | ★안티2 브라우저 안 띄우고 `match=true` 텍스트만. 국장 적발. 효과 불명. **최우선 재검증.** |
| display_id (proposal 경로) 수리 | 코드 diff(B)는 있으나 효과 미검증. |
| IDENTITY-FIX 진짜 데이터 효과 | mock 4케이스로만 검증. 진짜 프로젝트 효과 미확인. |

---

## 3. 여전히 깨진 것 (A — 국장 실화면, 미해결)

| 증상 | 상태 |
|---|---|
| PBE 재생영상 닭(A1) 고정 (A2\|A3 열어도 닭) | 미해결. PBE-PLAYBACK 가짜검증이라 효과 불명. |
| PBE 필름스트립 404 폭발 (P_SF_..._N.jpg 수백개) | 미해결. test_video 기각됐으나 진범 미확정(생성안됨 vs 변형조각 누락). |
| 프레임 이미지 ≠ 재생 이미지 (PBE 안) | 미해결. 위 둘과 연결. |
| apply 좌우 반전 (좌측 밀었는데 우측에 비활성 생성) | 미해결. 미진단. (pbeBoundaryOps 의심) |
| proposal 최초 조각맵 긴 라벨 | 미해결(apply 후엔 짧음). |

---

## 4. 진짜 바닥 (정직한 결론)
**PBE 내부(재생·필름스트립·좌우반전)는 진짜로 검증된 수리가 사실상 0.** mock "PASS"만 받았다. 진짜 프로젝트·국장 실화면으로 확인된 건 §1 목록뿐.

## 5. 다음 (재검증 순서 — 새 시스템으로)
```
1. 부산물 파이프라인 1회 증명 (playwright.config trace/video on → 부산물 생성+timestamp 확인)
2. PBE-PLAYBACK 재검증 (EVIDENCE → PRODUCT: 국장이 video/실화면으로 닭 아님 확인)
3. proposal display_id 재검증
4. PBE 필름스트립 404 미니진단 (backend가 _N.jpg 만드는지 + 변형조각 처리하는지)
5. apply 좌우반전 진단·수리
6. IDENTITY-FIX 진짜 데이터 재검증
```
