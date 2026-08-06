# -*- coding: utf-8 -*-
"""[EDIT-SAVE-1] edit_version · edit_version_item — 편집 저장 원장 (SAVE-SPINE).

국장 G1 개방 토큰: G1-2026-08-06-EDIT-SAVE-1
story_version 선례(2026-08-04)를 그대로 따른다. 값 스냅샷 · program_id 인덱스 전용 ·
programs FK 금지 — 사유는 story_version/models.py 와 동일(관제실 하드삭제 회피, main.py:6014).

STEP 0 실측 정합 (2026-08-05):
  · 키는 project_id 가 아니라 program_id (운영 원장 관례).
  · 순서 컬럼은 fragment_order 가 아니라 ordinal (형제표 story_version_item 과 통일).
  · proposal_id 는 형제표에 없어 여기 nullable 로 신설 — A/B 미선택이면 null.
  · edit_values(형제표) 와 의미가 겹치는 칸은 새로 만들지 않는다 (값 스냅샷은 edit_values 하나).
  · sound_role 은 SOUND-1 값을 담을 별도 칸(nullable) — edit_values 와 의미 겹치지 않음.
"""

TABLE = "edit_version"
ITEM_TABLE = "edit_version_item"

DDL_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    version_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id         TEXT    NOT NULL,   -- 인덱스만. programs FK 금지
    name               TEXT    NOT NULL,
    parent_version_id  INTEGER,            -- 자기참조 (nullable)
    story_version_id   INTEGER,            -- 어느 승인 스토리에서 떴는지 (nullable)
    proposal_id        TEXT,               -- A/B 선택 결과. 미선택이면 null
    schema_version     INTEGER NOT NULL,
    created_by         TEXT    NOT NULL,   -- user / ab_a / ab_b
    created_at         TEXT    NOT NULL
)
"""

ITEM_DDL_SQL = f"""
CREATE TABLE IF NOT EXISTS {ITEM_TABLE} (
    version_id       INTEGER NOT NULL,
    ordinal          INTEGER NOT NULL,   -- 순서 0..N-1
    fid              TEXT    NOT NULL,
    source_id        TEXT    NOT NULL,
    anchor_start_ms  INTEGER NOT NULL,   -- 좌표. fid 가 죽어도 구간은 남는다
    anchor_end_ms    INTEGER NOT NULL,
    trim_start_ms    INTEGER,            -- nullable
    trim_end_ms      INTEGER,            -- nullable
    hidden           INTEGER NOT NULL DEFAULT 0,   -- 숨김/표시 (0/1)
    sound_role       TEXT,               -- SOUND-1 값 칸 (nullable)
    display_id       TEXT,               -- 그 시점 표시 문자열 스냅샷
    edit_values      TEXT    NOT NULL DEFAULT '{{}}',  -- 값 스냅샷 JSON
    PRIMARY KEY (version_id, ordinal)
)
"""

INDEX_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_edit_version_program ON {TABLE}(program_id)",
    f"CREATE INDEX IF NOT EXISTS idx_edit_version_parent ON {TABLE}(parent_version_id)",
    f"CREATE INDEX IF NOT EXISTS idx_edit_version_item_version ON {ITEM_TABLE}(version_id)",
]

# rollback: 아래 두 줄이 역DDL 전부. 기존 테이블 무접촉이라 부작용 없음.
DROP_SQL = [
    f"DROP TABLE IF EXISTS {ITEM_TABLE}",
    f"DROP TABLE IF EXISTS {TABLE}",
]

COLUMNS = [
    "version_id", "program_id", "name", "parent_version_id", "story_version_id",
    "proposal_id", "schema_version", "created_by", "created_at",
]

ITEM_COLUMNS = [
    "version_id", "ordinal", "fid", "source_id",
    "anchor_start_ms", "anchor_end_ms", "trim_start_ms", "trim_end_ms",
    "hidden", "sound_role", "display_id", "edit_values",
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
    """DDL 컬럼 목록 == 선언 목록 (create_table.py 가 실행 전 확인)."""
    a, b = _ddl_columns(DDL_SQL), _ddl_columns(ITEM_DDL_SQL)
    ok = (a == COLUMNS) and (b == ITEM_COLUMNS)
    return ok, {"version": a, "version_expected": COLUMNS,
                "item": b, "item_expected": ITEM_COLUMNS}
