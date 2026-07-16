"""[STORAGE-1 ST-2] 사용량 조회 — read-only, 값만 반환(표시는 후속 과제).

get_usage_summary()는 두 storage 루트 전체를 스캔해
(1) 총량, (2) source_id/program_id로 귀속 가능한 파일들의 프로젝트별 합계,
(3) 어디에도 못 붙인 파일들의 unassigned 합계를 반환한다.
파일을 쓰거나 지우지 않는다.
"""
import re
import sqlite3
from pathlib import Path

from . import grades

_SRC_RE = re.compile(r"(SRC_[0-9A-Fa-f]+)")
_PROJ_RE = re.compile(r"(proj_[0-9a-fA-F]+)")


def _ro_connect(db_path: Path):
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _source_to_program_map(db_path: Path) -> dict:
    con = _ro_connect(db_path)
    try:
        return {row[0]: row[1] for row in con.execute(
            "SELECT source_id, program_id FROM project_sources"
        )}
    finally:
        con.close()


def _program_names(db_path: Path) -> dict:
    con = _ro_connect(db_path)
    try:
        return {row[0]: row[1] for row in con.execute(
            "SELECT program_id, name FROM programs"
        )}
    finally:
        con.close()


def get_usage_summary() -> dict:
    """returns:
    {
      "total_bytes": int,
      "total_files": int,
      "by_project": {program_id: {"name": str, "bytes": int, "files": int}, ...},
      "unassigned": {"bytes": int, "files": int},
    }

    DEBT: uploads/exports 원본 파일명은 SRC_/proj_ 패턴을 안 담는 경우가 많아
    unassigned 비중이 큼(실측 44.2GB/56.8GB). project_sources만으로는 부족 —
    sources.file_path 직접 매칭으로 보강 필요(후속 과제, 표시 붙일 때 함께).
    """
    src_to_prog = _source_to_program_map(grades.DB_PATH)
    prog_names = _program_names(grades.DB_PATH)

    total_bytes = 0
    total_files = 0
    by_project: dict = {}
    unassigned = {"bytes": 0, "files": 0}

    for root in grades.STORAGE_ROOTS:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            total_bytes += size
            total_files += 1

            program_id = None
            m = _PROJ_RE.search(f.name)
            if m:
                program_id = m.group(1)
            else:
                m2 = _SRC_RE.search(f.name)
                if m2:
                    program_id = src_to_prog.get(m2.group(1))

            if program_id:
                bucket = by_project.setdefault(program_id, {
                    "name": prog_names.get(program_id, "(알수없음)"),
                    "bytes": 0, "files": 0,
                })
                bucket["bytes"] += size
                bucket["files"] += 1
            else:
                unassigned["bytes"] += size
                unassigned["files"] += 1

    return {
        "total_bytes": total_bytes,
        "total_files": total_files,
        "by_project": by_project,
        "unassigned": unassigned,
    }
