# -*- coding: utf-8 -*-
"""[SAVE-SPINE 2-A] story_version · story_version_item — 저장된 버전 원장.

국장 G1 개방 2026-08-04. 확정 설계:
  ① 프로젝트 = 폴더 하나 (채팅 하나 · 전사 원문 하나)
  ② 그 안에 버전들이 파일처럼 쌓인다
  ③ 주인은 저장된 버전
  ④ 다시 편집해도 같은 폴더 안에서 버전이 하나 더 (새 프로젝트 아님)
  ⑤ 저장 안 하면 공식 목록에 안 남는다
  ⑥ 부모/자식은 버전 사이의 관계

왜 참조가 아니라 값 스냅샷인가 (실측 근거):
  `fragment_edit_state` 는 `UNIQUE (program_id, timeline_item_id)` 라 버전 축이 없다.
  같은 조각을 두 번 저장하면 UPDATE 로 덮인다 — 옛 버전의 trim 이 사라진다.
  그래서 버전은 그 시점의 **값을 통째로 복사**한다. 저장 1회 = 조각 수만큼 행.

왜 program_id 에 FK 를 걸지 않는가 (실측 근거):
  `GET /projects` (main.py:6014-6024) 가 `deleted_at < 지금-30일` 인 programs 를
  하드 DELETE + commit 한다. 관제실 흐름도 탭(AdminAnatomyPanel.tsx:213)이 이걸 부른다.
  FK 를 걸면 관제실을 한 번 여는 것으로 저장된 버전이 함께 지워진다.
  → 인덱스만 건다. 고아 행은 남을 수 있고, 그것이 지워지는 것보다 낫다.

왜 전사 선택상태가 item 이 아니라 version 에 붙는가:
  span(전사 낱말 구간, Pollux 586개)과 fragment(조각, 135개)는 단위가 다르다.
  선택은 목록 전체에 대한 하나의 결정이라 item 으로 쪼갤 근거가 없다.
  단 span_id 는 전사 세대가 바뀌면 죽으므로 `rough_cut_input_hash` 를 함께 적는다
  (조각 fid 가 분절 경계 변경으로 죽던 2026-08-01 사고와 같은 종류의 방어).
"""

TABLE = "story_version"
ITEM_TABLE = "story_version_item"

DDL_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    version_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id           TEXT    NOT NULL,   -- 인덱스만. FK 금지 (위 사유)
    name                 TEXT    NOT NULL,   -- 사용자가 붙인 이름
    parent_version_id    INTEGER,            -- 설계 ⑥: 버전 사이의 부모/자식
    schema_version       INTEGER NOT NULL,
    sequence_hash        TEXT    NOT NULL,   -- 저장 시점 원고 지문
    item_count           INTEGER NOT NULL,
    source_ids           TEXT    NOT NULL,   -- JSON 배열
    selected_span_ids    TEXT    NOT NULL,   -- 전사 선택상태 (JSON 배열, 순서 유의미)
    rough_cut_input_hash TEXT,               -- 위 span_id 들이 속한 전사 세대
    actor                TEXT    NOT NULL,
    note                 TEXT,
    created_at           TEXT    NOT NULL
)
"""

ITEM_DDL_SQL = f"""
CREATE TABLE IF NOT EXISTS {ITEM_TABLE} (
    version_id       INTEGER NOT NULL,
    ordinal          INTEGER NOT NULL,   -- 순서. 배열 인덱스를 값으로 박는다
    fid              TEXT    NOT NULL,
    source_id        TEXT    NOT NULL,
    anchor_start_ms  INTEGER NOT NULL,   -- 좌표. fid 가 죽어도 구간은 남는다
    anchor_end_ms    INTEGER NOT NULL,
    trim_start_ms    INTEGER NOT NULL,
    trim_end_ms      INTEGER NOT NULL,
    hidden           INTEGER NOT NULL,   -- 숨김/표시 (0/1)
    display_id       TEXT,               -- 그 시점 표시 문자열을 박아 저장
    edit_values      TEXT    NOT NULL,   -- 값 스냅샷 JSON (excluded_ranges 등)
    PRIMARY KEY (version_id, ordinal)
)
"""

INDEX_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_story_version_program ON {TABLE}(program_id)",
    f"CREATE INDEX IF NOT EXISTS idx_story_version_parent ON {TABLE}(parent_version_id)",
    f"CREATE INDEX IF NOT EXISTS idx_story_version_item_version ON {ITEM_TABLE}(version_id)",
]

# rollback: 아래 두 줄이 역DDL 전부. 기존 테이블 무접촉이라 부작용 없음.
DROP_SQL = [
    f"DROP TABLE IF EXISTS {ITEM_TABLE}",
    f"DROP TABLE IF EXISTS {TABLE}",
]

COLUMNS = [
    "version_id", "program_id", "name", "parent_version_id", "schema_version",
    "sequence_hash", "item_count", "source_ids", "selected_span_ids",
    "rough_cut_input_hash", "actor", "note", "created_at",
]

ITEM_COLUMNS = [
    "version_id", "ordinal", "fid", "source_id",
    "anchor_start_ms", "anchor_end_ms", "trim_start_ms", "trim_end_ms",
    "hidden", "display_id", "edit_values",
]

SCHEMA_VERSION = 1


def _ddl_columns(ddl):
    body = ddl[ddl.index("(") + 1: ddl.rindex(")")]
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("--") or line.startswith("PRIMARY KEY"):
            continue
        out.append(line.split()[0].strip(","))
    return out


def self_check():
    """DDL 의 컬럼 목록과 선언 목록이 일치하는지 (create_table.py 가 실행 전 확인)."""
    a, b = _ddl_columns(DDL_SQL), _ddl_columns(ITEM_DDL_SQL)
    ok = (a == COLUMNS) and (b == ITEM_COLUMNS)
    return ok, {"version": a, "version_expected": COLUMNS,
                "item": b, "item_expected": ITEM_COLUMNS}
