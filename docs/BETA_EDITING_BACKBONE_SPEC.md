# BETA_EDITING_BACKBONE_SPEC v1.0

본선 ccut-1.0.4-step9, HEAD b5cee91 기준. 단, 일부 AUDIT raw는 modified working tree 상태의 파일(특히 archive/manager.py)을 기준으로 확인되었다.
이 문서는 상위 설계 문서다. 편집 저장·읽기·조각맵·정밀편집·재생·Preview가 전부 이 문서를 따른다.
이 문서가 확정되기 전 코드 수정 금지.

## 1. AUDIT로 확정된 사실 (raw 근거)
- 편집 trim은 현재 Index.tsx 런타임 state에만 존재. DB·서버 영속 없음. (A-2)
- /save_edit 실재: Index.tsx:1544 → main.py:2291 save_edit → bams.archive_fragments → save_fragments. (B''~B7)
- save_fragments(manager.py L56)는 FragmentTable(**frag) + db.add → 항상 INSERT(append). UPDATE 아님. (B7)
- 저장처 = fragments 테이블. 화면이 읽는 곳 = semantic_fragments 테이블. 쓰는 곳 ≠ 읽는 곳. (B7 + A-1)
- save_fragments에 MockFrag 메모리 dict 동시 사용(L60-67). (B7)
- archive_fragments(manager.py L87)는 fps30 기본값(L102), start_frame÷fps 환산(L121/133), 저장키 start_time/end_time, excluded 없음, intelligence에 frame 재주입(L96-100). (B5)
- archive_fragments는 편집 전용이 아니라 범용 적재 함수로 보이며(main.py에서 save_edit 외 다수 호출 지점 확인: L805/L2488/L2606 등), 편집 overlay 저장소로 직접 재활용하기에는 위험하다. (B'''' bams 호출 raw)
- semantic_fragments 컬럼 = start/end(Float) + JSON 3개. start_sec/end_sec/excluded/trim_applied 컬럼 없음. (B6)
- Fragment 타입(fragmentData.ts) = start_frame/end_frame 중심, excluded? 있음, sec 필드 없음. (B6)
- 정밀편집(SingleFragmentEditor L93-94)은 start_sec/start/start_time 중 하나 필요. 없으면 L124 return → "시간 정보 없음" 거부. (C2)
- 재생(CenterPanel)은 start_frame÷30 기반. (A-1 그룹4)
- handleAddFromSource(Index.tsx L1170)는 ...f 통째 복사 + fragment_id/uid/display_id/excluded만 덮음. 원본 f에 sec 없으면 복사본도 없음. (C2-2)

확정 결론: 편집 영속 경로는 실질적으로 끊겨 있다(저장-읽기 테이블 불일치). 그리고 재생(frame)과 편집(sec)이 서로 다른 시간 기준을 본다.

## 2. 현재 /save_edit 경로의 한계
- 저장은 실행되나(INSERT) 화면이 읽지 않는 테이블(fragments)에 들어가 → 새로고침 시 편집 소실.
- 프론트는 저장 성공/실패 무관하게 "저장되었습니다" 문구 표시 → 사용자는 영속된 줄 앎(실제 아님). 더미 신호.
- 따라서 이 경로는 "영속되는 척"이며, 편집 영속의 신뢰 기반이 못 된다.

## 3. fragments vs semantic_fragments 테이블 불일치
- 쓰기: save_fragments → FragmentTable(=fragments)
- 읽기: 화면/proposal/정밀편집 → SemanticFragmentTable(=semantic_fragments)
- 두 테이블이 분리돼 편집 결과가 읽기 경로에 도달하지 못함.
- 확정: 기존 경로 교정이 아니라 신규 edit_overlay 계층으로 분리한다(§15).

## 4. 원본 semantic_fragments 불가침 원칙
- semantic_fragments.start/end(원본 분석 결과)는 덮어쓰지 않는다.
- 편집은 원본 수정이 아니라 "사용자 결정"을 별도로 얹는 것.
- 원본 테이블 스키마 변경(컬럼 추가) 금지. JSON 컬럼/별도 계층 활용.

## 5. edit overlay / effective range 계층
- 읽는 쪽(조각맵·정밀편집·재생·Preview)은 전부 한 가지 개념만 본다:
  effective_start_sec : 편집 반영된 시작(초)
  effective_end_sec   : 편집 반영된 끝(초)
  excluded            : 최종에서 빠지는가(true/false)
- 원본만 있고 편집 없으면 effective = 원본 환산값, excluded=false.
- 편집 있으면 그 값이 effective.
- 저장 위치 = 신규 edit_overlay 테이블(§15 확정).

## 6. frame/sec 단일화 원칙 (이번 백본의 심장)
- 단일 진실원천 = 초(sec). 프론트는 초로만 판단·표시·편집.
- frame 변환은 백엔드(ffmpeg -ss 초)에서만. 프론트 ×30/÷30 신규 도입 금지(59.94 소스 실재).
- 조각이 만들어지는 모든 입구에서 sec을 채운다(원본맵 추가 포함). frame만 있고 sec 없는 조각 금지 — 그게 C2.
- 기존 frame 필드는 호환용으로 남기되 판단 기준은 sec.

## 7. C2 재생O/편집X 실패 케이스 (산 증거)
- 같은 조각이 재생(frame)됨 / 편집(sec) 거부됨 = 두 진실원천 분열의 직접 증거.
- 원인: 원본맵 조각이 frame만 보유 → handleAddFromSource가 그대로 복사 → 편집기는 sec 요구.
- 백본은 "조각 생성·복사 시 sec 동반"을 강제해 이 케이스를 구조적으로 없앤다.

## 8. start_sec/end_sec vs start_frame/end_frame 역할 분리
- 판단·저장·편집·조각맵·재생 기준 = sec.
- frame = 표시 보조/백엔드 추출 입력. 단독 진실원천으로 쓰지 않는다.
- 확정: 원본 테이블·공유 테이블에 sec/excluded 물리 컬럼 추가 안 함. effective_start_sec/effective_end_sec/excluded는 신규 edit_overlay 테이블에서 source_id+fragment_id 매핑으로 관리, 프론트 통신 시 overlay JSON으로 결합.

## 9. excluded 저장 정책
- excluded는 조각의 1급 상태. edit_overlay 계층에 함께 저장.
- excluded=true 조각은 재생·Proposal·Export에서 제외, 조각맵엔 회색 표시(§11).
- Fragment 타입에 excluded? 이미 있음 → 프론트는 보유, 저장 계층에만 반영.

## 10. split + excluded 정책 (가운데 구간 제거)
- 멀티 trim 배열(한 조각에 구멍) 금지.
- 한 조각을 셋으로 분할:
  원본 SF_001 10.0~30.0, 가운데 18.0~21.0 제거
  → SF_001#A 10.0~18.0 excluded=false
    SF_001#X 18.0~21.0 excluded=true
    SF_001#B 21.0~30.0 excluded=false
- 분할 식별자 #A/#X/#B 규칙은 STEP C 설계에서 공식화. 전부 sec 기준.

## 11. 조각맵 표시 정책
- 조각맵은 effective_start_sec/effective_end_sec 길이로 표시.
- 현재 옛 길이 표시 원인: resolver(proposalFragmentResolver.ts L153)가 start_frame 우선 → effective sec 우선으로 교체.
- resolver는 공유영역 → 수정 전 별도 read-only로 호출처 확인 후. ×30 재도입 금지.

## 12. 정밀편집 진입 조건 정책
- 정밀편집은 effective sec이 유효하면 진입.
- 모든 조각이 생성 시 sec을 갖도록 보장(§6) → "시간 정보 없음" 거부가 구조적으로 사라짐.
- 진입 조건에서 frame 단독 폴백(÷30) 금지 — sec 없으면 입구를 고친다.

## 13. A/B Proposal 반영 정책
- Proposal 구성 시 excluded=true 제외, 포함 조각은 effective sec로 길이·재생.
- 재생 시 excluded 구간 재사용 금지.
- proposals 테이블 스키마 안 건드림 — 읽는 시점에 overlay 적용.

## 14. Preview Render 반영 정책
- Preview/Export는 effective sec를 백엔드 ffmpeg -ss(초)에 전달.
- exportClipBuilder는 이미 sec 읽고 frame 안 씀 → effective sec와 정합.
- frame 변환은 백엔드만.

## 15. 편집 저장 계층 (확정)
- 현 경로(save_edit→archive_fragments→save_fragments)는 테이블 불일치+MockFrag+fps30+sec누락+frame재주입이 겹침 → 그 위에 편집 overlay 얹기 금지.
- 확정: 신규 edit_overlay 테이블 + 독립 API. 원본 불가침·읽기 일원화에 가장 깔끔. backend 신규 작업이며 STEP C에서 DDL 설계 후 진행.
- edit_overlay 최소 필드(STEP C에서 확정): source_id, fragment_id, effective_start_sec, effective_end_sec, excluded.

## 16. 단계별 구현 순서 (코드 수정은 각 STEP 승인 후)
STEP B  이 Spec 확정 후 docs 저장
STEP C  edit_overlay DDL + #A/#X/#B 식별자 규칙 설계 (코드 0)
STEP D  조각 생성·복사 입구에 sec 보장 (handleAddFromSource 등) — C2 구조 제거, 최소 변경 [E보다 먼저, 확정]
STEP E  읽기 일원화: 조각맵 resolver를 effective sec 우선으로 (공유영역 사전 read-only)
STEP F  edit_overlay 쓰기/읽기 연결 (단일조각 trim부터 영속)
STEP G  split + excluded (가운데 제거) 구현
STEP H  A/B Proposal·Preview에 effective 반영 검증
(후속)  재생 멈칫 안정화 / fps 전수정리 — 별도 트랙
- 한 STEP = 한 배치. 단계 합치기 금지. 각 STEP 앞에 read-only AUDIT.

## 17. PASS 기준
DESIGN PASS    이 Spec/구조가 국장+ChatGPT 본문 검토 통과
CODE PASS      코드가 의도대로 들어감 (git diff)
RUNTIME PASS   API/로컬 실행 raw 확인
BROWSER PASS   브라우저 콘솔/화면 raw 확인
PRODUCT PASS   국장 실화면 체감 확인 (최종)
검증 케이스(최소, INPUT {…} -> OUTPUT {…} 형식):
- 양끝 trim 영속(새로고침 후 유지)
- 원본맵 추가 조각 정밀편집 가능(C2 해소)
- 중간 exclude 후 재생이 10~18+21~30
- 조각맵 길이 = 실제 재생 길이
- 재제안 시 excluded 재사용 안 함
- b5cee91 단일 trim 회귀 없음

## 확정 사항 (2026-06-07, 국장+ChatGPT 검수)
1. 편집 저장처 = 신규 edit_overlay 계층 + 독립 API. (기존 save_edit 경로 재활용 금지)
2. 원본·공유 테이블 물리 컬럼 추가 금지. effective sec/excluded는 edit_overlay 테이블 + overlay JSON 결합으로 관리.
3. 구현 순서 STEP D(입구 sec 보장) 먼저, 그 다음 STEP E(읽기 일원화).
