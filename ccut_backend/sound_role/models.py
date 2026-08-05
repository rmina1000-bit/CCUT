"""Schema for user corrections to derived sound handling labels.

The sensor result is derived and is never persisted here. This table contains
only an explicit user correction for a current timeline item.
"""

TABLE = "fragment_sound_role_override"
SCHEMA_VERSION = 1
ALLOWED_ROLES = ("dialogue", "background", "silence", "unknown")

DDL_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    program_id       TEXT    NOT NULL,
    timeline_item_id TEXT    NOT NULL,
    fragment_id      TEXT    NOT NULL,
    source_id        TEXT    NOT NULL,
    anchor_start_ms  INTEGER NOT NULL,
    anchor_end_ms    INTEGER NOT NULL,
    sound_role       TEXT    NOT NULL CHECK (
        sound_role IN ('dialogue', 'background', 'silence', 'unknown')
    ),
    schema_version   INTEGER NOT NULL,
    revision         INTEGER NOT NULL,
    actor            TEXT    NOT NULL,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    PRIMARY KEY (program_id, timeline_item_id),
    CHECK (anchor_start_ms >= 0),
    CHECK (anchor_end_ms > anchor_start_ms)
)
"""

INDEX_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_sound_role_override_fragment "
    f"ON {TABLE}(program_id, fragment_id)",
]

# Complete rollback. No existing table is part of this list.
DROP_SQL = [f"DROP TABLE IF EXISTS {TABLE}"]

COLUMNS = [
    "program_id", "timeline_item_id", "fragment_id", "source_id",
    "anchor_start_ms", "anchor_end_ms", "sound_role", "schema_version",
    "revision", "actor", "created_at", "updated_at",
]


def self_check():
    body = DDL_SQL[DDL_SQL.index("(") + 1: DDL_SQL.rindex(")")]
    found = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("PRIMARY KEY", "CHECK", "sound_role IN")):
            continue
        name = line.split()[0].strip(",")
        if name in COLUMNS:
            found.append(name)
    return found == COLUMNS, {"found": found, "expected": COLUMNS}
