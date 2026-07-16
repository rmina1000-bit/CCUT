# STORY GATE CONTRACT V1 — 스토리 승인 관문

발행: 2026-07-14 · 국장 판정 반영 · 상태: P0(계약 동결). 코드 0줄.
상위 문서: `docs/CCUT_MASTER_CONCEPT_1.0.md` (중심화면 ①원고 ②이야기 ③결과)

---

## 0. 한 줄

**사용자 승인 없이는 편집(렌더)이 일어나지 않는다.** 기계는 이야기를 제안할 뿐이고,
편집으로 넘어가는 문은 사람이 연다.

---

## 1. 왜 이 계약이 필요한가 (실측)

현재 파이프라인은 조각 선별·배치가 끝나는 그 자리에서 곧바로 영상을 렌더한다.

| 사실 | 위치 |
|---|---|
| 제안 생성 API가 같은 호출 안에서 미리보기를 렌더 | `ccut_backend/main.py:2328` `inject_proposal_previews(proposals)` |
| 분석 완료 → 곧바로 제안 생성으로 진입 | `ccut_frontend/src/pages/Index.tsx:563` "의미 조각 수집 및 제안 생성 중..." |
| 채팅이 결과부터 통보 | `ccut_frontend/src/hooks/useProposalState.ts:953` "다 골랐습니다 — A안 …초 · B안 …초. 아래 무대에서 재생해 보시고" |
| 사용자가 처음 보는 화면 = 렌더된 편집본 + [A안 확정] | `ccut_frontend/src/components/CenterPanel.tsx:1798` |

그 결과 **이야기를 협의할 자리가 구조적으로 없다.** 사용자는 이미 편집된 결과를 놓고
"A냐 B냐"만 고를 수 있다.

반대로, 이야기를 보여줄 재료는 이미 다 있다:

| 사실 | 위치 |
|---|---|
| 원고 = 제안 sequence를 텍스트로 읽은 것. **렌더 불필요** | `ccut_backend/ledger_r0.py:5` "스토리 원고 = committedProposalId 우선(없으면 selected) 제안의 sequence 순서" |
| 원고 read API 동작 확인 | `GET /ledger/{program_id}` → 200 (Marigold 실측) |
| 문장 클릭 → 원본 구간 재생 동작 확인 | `ccut_frontend/src/pages/LedgerPage.tsx` `loadItem`/`rafTick` (커밋 344e1649) |

즉 **새로 만들 것은 원고 생성기가 아니라, 렌더를 승인 뒤로 미루는 관문이다.**

---

## 2. 상태기계 (Program Lifecycle)

```
ingested ──▶ scanned ──▶ story_draft ──▶ story_review ──▶ story_approved ──▶ editing ──▶ exported
                             ▲               │
                             └───── revise ──┘   (렌더 0회, 몇 번이든)
```

| 상태 | 뜻 | 진입 조건 | 이 상태에서 금지되는 것 |
|---|---|---|---|
| `ingested` | 원본 업로드됨 | `POST /upload` 완료 | — |
| `scanned` | 1차 조각분석 완료 | `/generate-fragments` + `/semantic-fragments` 완료 | — |
| `story_draft` | 제안 sequence 생성됨 (**렌더 없음**) | `/proposals/project` with `render_preview=false` | **렌더 호출** |
| `story_review` | 사용자가 원고를 보는 중 | 원고 화면 노출 | **렌더 호출**, 편집 UI 노출 |
| `story_approved` | 사용자가 승인함 | `POST /story/{id}/approve` | — |
| `editing` | 렌더·PBE·A/B 편집 개방 | 승인 영수증 존재 | — |
| `exported` | 최종 산출 | `/render`, `/export` | — |

**전이는 단방향이 아니다.** `story_review → revise → story_draft`는 몇 번이든 왕복한다.
`story_approved` 이후 사용자가 다시 이야기를 고치겠다고 하면 `story_review`로 되돌아갈 수 있고,
그때 기존 승인 영수증은 무효화(supersede)되며 새 승인이 필요하다.

---

## 3. 불변식 (Invariants) — 검증 가능한 형태로만 적는다

| # | 불변식 | 검증 방법 |
|---|---|---|
| I-1 | `story_approved` 영수증이 없는 프로그램은 렌더 산출물이 0개다 | 승인 전 `/render`·`inject_proposal_previews` 호출 → **HTTP 403**, storage 렌더 파일 수 전후 동일 |
| I-2 | 협의(revise) 중 렌더는 0회 | 조건 3회 연속 수정 → 네트워크 render 요청 0, 렌더 산출 파일 증가 0 |
| I-3 | 승인한 원고 == 렌더된 결과의 순서 | 승인 시점 `GET /ledger/{id}/edl` 과 렌더 입력 clip 리스트 diff = 0 |
| I-4 | 게이트 OFF면 현행 동작과 바이트 동일 | `CCUT_STORY_GATE=off` 로 업로드→편집 전 구간 실행, 응답·DB 해시 전후 동일 |
| I-5 | 승인은 사람만 한다 | 승인 영수증의 actor는 항상 user. AI·자동 경로에서 approve 호출 불가 |

I-1과 I-5가 이 계약의 심장이다. 나머지가 흔들려도 이 둘이 서면 계약은 산다.

---

## 4. 게이트

`CCUT_STORY_GATE` (환경변수, **기본 OFF**)

- OFF: 지금 흐름 그대로. 새 코드는 전부 우회. (I-4)
- ON: 본 계약의 흐름.

`EDIT_CONTRACT_V2`와 동일한 방식이며, `/settings/gates`에 노출한다.
(게이트 목록: `ccut_backend/main.py:4232`)

---

## 5. 승인 영수증 (Receipt)

> **v1.1 수정 (2026-07-15, P2 정찰 실측 반영).** 초안은 `vault_events` 재사용을 지시했으나
> 실측 결과 **부적합으로 기각**한다. `vault_events`는 조각 구간에 매달린 원장이고
> (`anchor_hash`, `start_ds`, `end_ds` + `record_events()`의 `event_kind` 화이트리스트 +
> `source_id` 필수), 스토리 승인은 **program 단위**라 anchor가 없다. 얹을 자리가 없다.

**전용 원장 테이블 `story_approval`** 을 쓴다 (append-only).

```
story_approval
  approval_id    INTEGER PK
  program_id     TEXT NOT NULL
  sequence_hash  TEXT NOT NULL   -- sha256(mode|fid|fid|...)[:16]  ← I-3 대조 기준
  mode           TEXT            -- 승인 시점의 committed/selected proposal (A/B)
  fragment_ids   TEXT NOT NULL   -- 승인한 조각 순서열 원문(JSON)
  item_count     INTEGER NOT NULL
  running_ms     INTEGER
  actor          TEXT NOT NULL   -- I-5: 항상 'user'
  approved_at    TEXT NOT NULL
  superseded_by  INTEGER         -- 다음 승인 id (NULL = 현재 유효)
  note           TEXT

  UNIQUE INDEX uq_story_approval_live (program_id) WHERE superseded_by IS NULL
```

- `sequence_hash` = 승인 시점 원고(`mode` + fragment_id 순서열)의 해시. **순서가 바뀌면 해시가 바뀐다** — 배치도 승인 대상이기 때문.
- 승인 후 원고가 바뀌면 상태가 자동으로 `story_review`로 돌아가고(승인이 `stale`), 렌더가 다시 막힌다. 재승인 시 이전 행에 `superseded_by`를 채운다.
- 영수증은 **지우지 않는다.** 무엇을 승인했었는지가 남아야 한다.
- **운영 DB 스키마 불가침**: `create_table.py`가 운영 DB 경로를 하드 거부(exit 2)한다. 테이블이 없으면 읽기는 "승인 없음"으로 답하고 쓰기는 503. edit_contract과 같은 Cutover 규율.

**원고의 진실원** (실측): `programs.ui_state` → `proposalsKeyFragments[mode]`,
`mode = committedProposalId or selectedProposalId` (`ledger_r0.py:113-114`와 동일 규칙).
승인은 "그 배열을 그 순서로 승인했다"는 기록이다.

---

## 6. 원고 단수 원칙 (국장 판정)

**협의 화면에는 원고를 하나만 띄운다.**

- A안/B안 두 벌을 만들어 고르게 하지 않는다. 추천안 하나를 원고로 보여주고, 마음에 안 들면 **대화로 고친다**.
- 근거: "A냐 B냐"는 기계적 선택이지 협의가 아니다. 한 편의 이야기를 함께 다듬는 편집실에 가깝게 간다.
- 부수효과: 승인 전 이중 렌더가 사라져 협의가 빨라진다.
- 내부적으로 엔진이 A/B를 만드는 것은 무방하나, **화면에는 하나만** 나간다. (B를 기본 추천으로 쓰는 현행 `setSelectedProposalId(B ?? A)` 유지)

---

## 7. 승인 전 재생 원칙 (국장 판정)

**승인 전에는 완성본을 만들지 않는다.**

- 허용: 원고 문장 클릭 → **원본 영상의 해당 구간만** 재생. (오늘 커밋 344e1649로 구간 경계 정확도 확보)
- 금지: 이어붙인 가안 영상, 저해상도 프리뷰, 워터마크본 — 형태 불문 **렌더 산출물 일체**.
- 이유: 가안이라도 렌더가 돌면 "편집으로 직행"이 부분적으로 되살아나고, 매 수정마다 비용이 든다.

---

## 8. API 계약 (P1·P2에서 구현)

| 단계 | 엔드포인트 | 계약 |
|---|---|---|
| P1 | `POST /proposals/project` | `render_preview: bool = True` 추가. **False면 `inject_proposal_previews` 건너뜀**(main.py:2328). 기본 True → 현행 무변 |
| P2 | `GET /ledger/{program_id}` | 응답에 `story_state` 필드 추가 (신규 라우트 만들지 않음) |
| P2 | `POST /story/{program_id}/approve` | 영수증 기록 + `story_approved`. body에 사용자가 본 `sequence_hash` 동봉 → 불일치면 **409**(그새 원고가 바뀜) |
| P2 | `POST /story/{program_id}/revise` | 자연어 조건 → 선별·배치만 재실행(`render_preview=false`) → 원고 갱신. **렌더 0** |
| P2 | `POST /render/*`, `/export-input/*` | 게이트 ON일 때 승인 영수증 없으면 **403** (I-1) |

409/403은 edit_contract이 쓰는 규약과 동일하게 맞춘다. (낙관적 잠금 = `revision`, 게이트 차단 = 403)

---

## 9. 화면 계약 (P3·P5에서 구현)

**협의 중 (`story_draft`/`story_review`)**
- 중심화면 = **원고**. 미리보기 영상 카드 없음. Export 버튼 없음. [A안 확정] 없음.
- 채팅 첫 마디 = 결과 통보가 아니라 제안. (현행 "다 골랐습니다 …" → "이런 이야기로 엮었습니다. 보시고 말씀 주세요.")
- 문장 클릭 = 원본 구간 재생 (§7)

**승인 후 (`editing`)**
- 그때 비로소 렌더가 돌고, 편집 화면(A/B·PBE·Export)이 등장한다.

---

## 10. 단계별 검증 게이트 (P0 이후)

| 단계 | 내용 | 통과 기준 |
|---|---|---|
| P0 | 본 문서 | 국장 판정 |
| P1 | 렌더 분리 (`render_preview`) | true/false sequence 바이트 동일 · false일 때 렌더 산출 0 · 소요시간 raw |
| P2 | story API 3종 + 403/409 | 승인 없이 render → 403 · 승인 후 EDL diff 0 (I-3) · 영수증 raw |
| P3 | 이야기 화면 | ★SEE: 신규 업로드 → 분석 끝 → **영상이 아니라 원고**가 뜬다 · 편집 UI 없음 |
| P4 | 협의 루프 | ★SEE: 조건 3회 수정 → 원고 3회 갱신 · render 요청 0 (I-2) |
| P5 | 승인 → 편집 개방 | ★SEE: 승인 후에만 편집 등장 · 렌더 결과 순서 == 승인 원고 |
| P6 | 2차 집중분석 병행 | 원고 읽는 동안 VL/파노라마 백그라운드 · 끝나면 "장면 설명 정밀해짐" 배지 |

각 단계는 게이트 OFF 상태에서 기존 동작 무변(I-4)을 먼저 증명한 뒤 ON 검증으로 넘어간다.

---

## 11. 범위 밖 (이번 계약이 다루지 않는 것)

- **Marigold 좌표 오염** (`coord_source=ui_state_snapshot` 조각의 경계값) — 데이터 문제. 별건.
- 원고 텍스트 품질(ASR 환각, `[두 번째 요리]` 반복) — TEXT-CORE 트랙 소관.
- 재생 매끄러움/오디오 글리치 — SCRIPT-2h 이후 별도 과제.
- 2차 집중분석의 알고리즘 자체 — P6는 "언제 돌리나"만 다루고 "무엇을 계산하나"는 안 건드린다.

---

## 12. DEBT

- 원고 화면 근사 재생: 90ms 미만 활성 span 재생 누락 가능 (렌더는 정확)

- 상태(`story_state`) 영속 위치: 초안은 `programs` 테이블 컬럼 1개. 확정은 P2 착수 시 국장 판정.
- 다중 소스 프로그램에서 원고 1개 원칙이 어떻게 보이는지(영상 14개짜리 Hadar 등)는 P3 화면검증에서 실측 후 판단.
