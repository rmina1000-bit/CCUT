"""[FRAGMENT-SEARCH 단계1] fragment_index 테이블 + FTS5 가상 테이블 생성.

- fragment_index: SQLAlchemy 모델로 생성 (create_all)
- fragment_fts: FTS5 가상 테이블 (raw SQL, ORM 불가)
- 트리거: fragment_index <-> fragment_fts 동기화

멱등(idempotent): 여러 번 실행해도 안전. 기존 데이터 보존.
read/write 분리: 이 스크립트는 스키마만 생성, 데이터는 인덱서가 채움.
"""
import os
import sys
import sqlite3

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ccut_backend"))
sys.path.insert(0, BACKEND_DIR)
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")


def create_orm_table():
    """SQLAlchemy 모델로 fragment_index 테이블 생성."""
    from database import engine, Base
    import archive.db_models  # noqa: F401  모든 테이블 등록
    from archive.db_models import FragmentIndexTable
    FragmentIndexTable.__table__.create(bind=engine, checkfirst=True)
    print("[OK] fragment_index 테이블 생성 (또는 이미 존재)")


def create_fts_table():
    """FTS5 가상 테이블 + 동기화 트리거 (raw SQL)."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # content-table 연동 FTS5: fragment_index를 외부 콘텐츠로 참조
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fragment_fts USING fts5(
            fragment_id UNINDEXED,
            search_text,
            visual_desc,
            transcript,
            role UNINDEXED,
            content='fragment_index',
            content_rowid='rowid'
        )
    """)

    # 트리거: fragment_index 변경 시 FTS 동기화
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS fragment_index_ai AFTER INSERT ON fragment_index BEGIN
            INSERT INTO fragment_fts(rowid, fragment_id, search_text, visual_desc, transcript, role)
            VALUES (new.rowid, new.fragment_id, new.search_text, new.visual_desc, new.transcript, new.role);
        END
    """)
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS fragment_index_ad AFTER DELETE ON fragment_index BEGIN
            INSERT INTO fragment_fts(fragment_fts, rowid, fragment_id, search_text, visual_desc, transcript, role)
            VALUES ('delete', old.rowid, old.fragment_id, old.search_text, old.visual_desc, old.transcript, old.role);
        END
    """)
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS fragment_index_au AFTER UPDATE ON fragment_index BEGIN
            INSERT INTO fragment_fts(fragment_fts, rowid, fragment_id, search_text, visual_desc, transcript, role)
            VALUES ('delete', old.rowid, old.fragment_id, old.search_text, old.visual_desc, old.transcript, old.role);
            INSERT INTO fragment_fts(rowid, fragment_id, search_text, visual_desc, transcript, role)
            VALUES (new.rowid, new.fragment_id, new.search_text, new.visual_desc, new.transcript, new.role);
        END
    """)
    con.commit()
    print("[OK] fragment_fts FTS5 가상 테이블 + 동기화 트리거 생성")
    con.close()


def verify():
    """생성 결과 검증 (read-only)."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT name, type FROM sqlite_master WHERE name LIKE 'fragment_index%' OR name LIKE 'fragment_fts%' ORDER BY name")
    rows = cur.fetchall()
    print("\n=== 생성된 객체 ===")
    for name, typ in rows:
        print(f"  {typ:8s} {name}")
    cur.execute("PRAGMA table_info(fragment_index)")
    cols = [r[1] for r in cur.fetchall()]
    print(f"\nfragment_index 컬럼 ({len(cols)}): {cols}")
    cur.execute("SELECT COUNT(*) FROM fragment_index")
    print(f"fragment_index 행 수: {cur.fetchone()[0]}")
    con.close()


if __name__ == "__main__":
    print(f"=== DB: {DB_PATH} ===")
    create_orm_table()
    create_fts_table()
    verify()
    print("\n[DONE] 단계1 스키마 생성 완료")
