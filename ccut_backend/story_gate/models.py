# -*- coding: utf-8 -*-
"""[STORY-GATE P2] story_approval — 승인 원장 (append-only).

왜 새 테이블인가 (P2 정찰 실측):
  vault_events는 조각 구간(anchor_hash, start_ds, end_ds)에 매달린 원장이고
  record_events()는 event_kind 화이트리스트 + source_id 필수를 강제한다.
  스토리 승인은 program 단위라 anchor가 없다 → 얹을 자리가 없다.
  (계약 V1 §5의 "vault_events 재사용"은 실측으로 기각. 대신 이 표가 승인 원장이다.)

원칙:
- append-only. 승인을 지우지 않는다. 원고가 바뀌면 새 행을 쌓고 이전 행에 superseded_by를 채운다.
- 무엇을 승인했는지가 남아야 한다 → sequence_hash + mode + fids 원문을 함께 적는다.
"""

TABLE = "story_approval"

DDL_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    approval_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id     TEXT    NOT NULL,
    sequence_hash  TEXT    NOT NULL,   -- I-3 대조 기준: sha256(mode|fid|fid|...)[:16]
    mode           TEXT,               -- 승인 시점의 committed/selected proposal (A/B)
    fragment_ids   TEXT    NOT NULL,   -- 승인한 원고의 조각 순서열 (JSON 배열 원문)
    item_count     INTEGER NOT NULL,
    running_ms     INTEGER,
    actor          TEXT    NOT NULL,   -- I-5: 항상 'user'. AI/자동 경로는 승인 불가.
    approved_at    TEXT    NOT NULL,
    superseded_by  INTEGER,            -- 다음 승인 approval_id (NULL = 현재 유효)
    note           TEXT
)
"""

INDEX_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_story_approval_program ON {TABLE}(program_id)",
    # 프로그램당 '유효한 승인'은 최대 1건 — supersede 없이 중복 승인이 쌓이는 것을 DB가 막는다.
    f"CREATE UNIQUE INDEX IF NOT EXISTS uq_story_approval_live "
    f"ON {TABLE}(program_id) WHERE superseded_by IS NULL",
]

COLUMNS = [
    "approval_id", "program_id", "sequence_hash", "mode", "fragment_ids",
    "item_count", "running_ms", "actor", "approved_at", "superseded_by", "note",
]


def self_check():
    """DDL의 컬럼 목록과 COLUMNS가 일치하는지 (create_table.py가 실행 전 확인)."""
    body = DDL_SQL[DDL_SQL.index("(") + 1: DDL_SQL.rindex(")")]
    ddl_cols = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        ddl_cols.append(line.split()[0].strip(","))
    return ddl_cols == COLUMNS, {"ddl": ddl_cols, "expected": COLUMNS}
