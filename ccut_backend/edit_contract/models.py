# -*- coding: utf-8 -*-
"""[EDIT-CONTRACT-B0] fragment_edit_state — 현재 상태의 유일 권위 (신규 테이블 1개, 국장 확정 예외).

스키마 근거: EDIT-CONTRACT-B0 v0.4 §6.
  (실행자 주기: v0.4 전문 미보유 — v0.2 §2 전 필드 + 재개지시 명시 v0.4 추가분
   carried_from_item_id·occurrence·INHERIT 반영. v0.4 §6 전문 대조 = STOP① V-gate 확인 항목)

기존 테이블 무변. 생성·시험은 격리 테스트 DB에만 (패치 2 — Cutover 전 운영 DB schema 변경 0).
"""
import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()  # 자체 Base — 제품 db_models.py 무접촉 (IMPL-2에서 배선 협의)


class FragmentEditStateTable(Base):
    __tablename__ = "fragment_edit_state"

    edit_state_id = Column(Text, primary_key=True)          # 안정 ID — 좌표와 독립, 발급 후 불변
    schema_version = Column(Integer, nullable=False)
    program_id = Column(Text, nullable=False)               # P0 — 공란 차단
    timeline_item_id = Column(Text, nullable=False)         # 사용본 단위 (v0.4 §3)
    source_id = Column(Text, nullable=False)
    anchor_start_ms = Column(Integer, nullable=False)       # 최초 원본 좌표 — 불변
    anchor_end_ms = Column(Integer, nullable=False)         # (재조각화 시 ±10ms 매칭, 덮어쓰지 않음)
    parent_fragment_id = Column(Text, nullable=True)        # 참고 필드 (권위 아님)
    carried_from_item_id = Column(Text, nullable=True)      # v0.4: 재제안 승계 추적
    occurrence = Column(Integer, nullable=False, default=0) # v0.4: 동일 증거의 사용본 순번
    trim_start_ms = Column(Integer, nullable=False)         # 생존 창 (기본 = anchor)
    trim_end_ms = Column(Integer, nullable=False)
    excluded_ranges_json = Column(Text, nullable=False, default="[]")  # canonical 내부 구간만
    removed = Column(Boolean, nullable=False, default=False)
    revision = Column(Integer, nullable=False, default=1)   # 낙관적 잠금
    last_origin = Column(Text, nullable=True)               # PBE|TEXT_EDITOR|NATURAL_LANGUAGE|MIGRATION|SYSTEM|INHERIT
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now)

    __table_args__ = (UniqueConstraint("program_id", "timeline_item_id", name="uq_fes_program_item"),)


# 생성/제거 스크립트용 DDL 원문 (클래스와 단일 원천 유지 — self_check로 대조)
DDL_SQL = """
CREATE TABLE IF NOT EXISTS fragment_edit_state (
    edit_state_id        TEXT PRIMARY KEY,
    schema_version       INTEGER NOT NULL,
    program_id           TEXT NOT NULL,
    timeline_item_id     TEXT NOT NULL,
    source_id            TEXT NOT NULL,
    anchor_start_ms      INTEGER NOT NULL,
    anchor_end_ms        INTEGER NOT NULL,
    parent_fragment_id   TEXT,
    carried_from_item_id TEXT,
    occurrence           INTEGER NOT NULL DEFAULT 0,
    trim_start_ms        INTEGER NOT NULL,
    trim_end_ms          INTEGER NOT NULL,
    excluded_ranges_json TEXT NOT NULL DEFAULT '[]',
    removed              BOOLEAN NOT NULL DEFAULT 0,
    revision             INTEGER NOT NULL DEFAULT 1,
    last_origin          TEXT,
    created_at           DATETIME,
    updated_at           DATETIME,
    UNIQUE (program_id, timeline_item_id)
)
""".strip()

DROP_SQL = "DROP TABLE IF EXISTS fragment_edit_state"


def self_check():
    """DDL 컬럼명 = SQLAlchemy 클래스 컬럼명 정확 일치 검사 (드리프트 차단)."""
    import re

    ddl_cols = [c for c in re.findall(r"^\s{4}(\w+)\s", DDL_SQL, re.M) if c != "UNIQUE"]
    cls_cols = [c.name for c in FragmentEditStateTable.__table__.columns]
    return ddl_cols == cls_cols, {"ddl": ddl_cols, "class": cls_cols}
