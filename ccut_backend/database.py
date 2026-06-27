from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path

# 현재 백엔드 디렉토리를 기준으로 DB 경로 설정 (1.0.3 오염 제거)
BACKEND_DIR = Path(__file__).resolve().parent
SQLALCHEMY_DATABASE_URL = os.getenv("CCUT_DATABASE_URL", f"sqlite:///{BACKEND_DIR}/ccut_app.db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

from sqlalchemy import event as _event

@_event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _conn_record):
    # 연결마다 WAL 보장 — 갑작스런 종료 시 DB 손상 방지 (2026-06-27 malformed 사고 예방)
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")   # WAL에서 안전+성능 균형
    cur.execute("PRAGMA busy_timeout=5000")    # 락 경합 시 5초 대기(즉시 실패 방지)
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# DB 세션을 가져오는 유틸리티
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
