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
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# DB 세션을 가져오는 유틸리티
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
