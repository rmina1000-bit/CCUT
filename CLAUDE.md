# CCUT — 작업 전 필독

**모든 에이전트·작업자는 코드를 만지기 전에 [docs/CCUT_MASTER_CONCEPT_1.0.md](docs/CCUT_MASTER_CONCEPT_1.0.md)를 먼저 읽는다.**
개념↔코드 대응은 [docs/CONCEPT_CODE_MAP.md](docs/CONCEPT_CODE_MAP.md).

한 문장: **CCUT은 AI 편집 도구가 아니라, 사용자가 기획·촬영하면 나머지를 방송국 제작진처럼 수행하는 로컬 AI 제작실이다.**

## 절대 규칙 (요약)

- 사용자의 말과 행동에 제약을 두지 않는다. 제약은 내부 계약(EDIT-CONTRACT-B0)에만 건다.
- 각 층의 진실은 하나: Evidence(사실) / Ledger(원고) / Timeline Item(사용본) / Edit State(승인된 편집) / Render Span(계산 결과 — 저장 금지) / Receipt(변경 기록).
- 원본 영상·운영 DB 스키마는 불가침 (신규 테이블 = 국장 승인 예외뿐).
- 시간 좌표는 ms 정수 단일 권위 — 변환은 `to_ms`/`toMs` 하나만 사용 (`ccut_backend/edit_contract/time_units.py`, `ccut_frontend/src/utils/editContract.ts`).
- 전체는 가볍게, 필요한 곳만 깊게 분석한다. 전 프레임 VL 금지.
- PBE는 예외 감독창이다. 사용자를 프레임 노가다로 보내는 설계는 실패다.
- 숨은 백그라운드 작업 금지. 같은 worktree에 writer 1명 (예약·자동 세션은 지시서 실행 금지 — STOP·보고만).
- 로컬 우선: API 없이 핵심 기능이 완주해야 한다.
- 증거 원칙: 실측 raw 우선, 전 시도 보존, 조용한 변경 금지(Receipt).

## 게이트 (국장만 열 수 있음)

- G1 운영 DB 변경 (스키마 생성·Cutover ON·MIG 실행)
- G2 본선 브랜치 접촉·병합·push
- G3 제품 방향·계약(v0.4) 수정
