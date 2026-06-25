"""
[A-4] pipeline_watchdog.py
파이프라인 자가진단 — sources / evidence / semantic / proposals / subtitles / quick_scan 연결 상태 점검.
run_watchdog() 단독 실행 가능. /pipeline/status API 연결 대상.
"""

import os
import sqlite3
from pathlib import Path


_DB_PATH = Path(__file__).parent.parent / "ccut_app.db"


def _get_conn():
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def run_watchdog(silent: bool = False) -> dict:
    """
    파이프라인 전체 상태 진단.
    silent=True: print 생략, dict만 반환 (/pipeline/status API용).
    """
    def _log(msg):
        if not silent:
            print(msg)

    result = {
        "ok": True,
        "warnings": [],
        "counts": {},
        "gaps": {},
    }

    try:
        conn = _get_conn()

        # 1. 기본 행수
        tables = [
            "sources", "evidence_board", "semantic_fragments",
            "proposals", "subtitles", "quick_scan",
        ]
        counts = {}
        for t in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                counts[t] = row[0] if row else 0
            except Exception as e:
                counts[t] = f"ERROR:{e}"
        result["counts"] = counts
        _log(f"[WATCHDOG] 행수: {counts}")

        # 2. sources별 파이프라인 완료 여부
        sources = conn.execute("SELECT source_id FROM sources").fetchall()
        source_ids = [r["source_id"] for r in sources]

        def _get_set(table, col="source_id"):
            rows = conn.execute(f"SELECT {col} FROM {table}").fetchall()
            return {r[0] for r in rows}

        ev_set   = _get_set("evidence_board")
        sem_set  = _get_set("semantic_fragments")
        prop_set = _get_set("proposals")
        sub_set  = _get_set("subtitles")
        qs_set   = _get_set("quick_scan")

        gaps = {
            "no_evidence":          [],
            "no_semantic":          [],
            "no_proposals":         [],
            "no_subtitles":         [],
            "no_quick_scan":        [],
        }

        for sid in source_ids:
            if sid not in ev_set:   gaps["no_evidence"].append(sid)
            if sid not in sem_set:  gaps["no_semantic"].append(sid)
            if sid not in prop_set: gaps["no_proposals"].append(sid)
            if sid not in sub_set:  gaps["no_subtitles"].append(sid)
            if sid not in qs_set:   gaps["no_quick_scan"].append(sid)

        result["gaps"] = {k: len(v) for k, v in gaps.items()}

        # 3. 경고 생성
        total = len(source_ids)
        if gaps["no_evidence"]:
            msg = f"[WATCHDOG][WARN] evidence 없는 소스 {len(gaps['no_evidence'])}/{total}"
            result["warnings"].append(msg)
            _log(msg)
        if gaps["no_semantic"]:
            msg = f"[WATCHDOG][WARN] semantic_fragments 없는 소스 {len(gaps['no_semantic'])}/{total}"
            result["warnings"].append(msg)
            _log(msg)
        if gaps["no_proposals"]:
            msg = f"[WATCHDOG][WARN] proposals 없는 소스 {len(gaps['no_proposals'])}/{total}"
            result["warnings"].append(msg)
            _log(msg)
        if gaps["no_subtitles"]:
            msg = f"[WATCHDOG][WARN] subtitles 없는 소스 {len(gaps['no_subtitles'])}/{total}"
            result["warnings"].append(msg)
            _log(msg)
        if gaps["no_quick_scan"]:
            msg = f"[WATCHDOG][WARN] quick_scan 없는 소스 {len(gaps['no_quick_scan'])}/{total}"
            result["warnings"].append(msg)
            _log(msg)

        if not result["warnings"]:
            _log("[WATCHDOG] 전체 파이프라인 정상")
        else:
            result["ok"] = False

        conn.close()

    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
        _log(f"[WATCHDOG] 진단 실패: {e}")

    return result


if __name__ == "__main__":
    run_watchdog()
