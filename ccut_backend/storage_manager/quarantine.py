"""[STORAGE-1 ST-3] 격리(quarantine) — 물리 영구삭제 아님, storage/_janitor_trash로 "이동"만.

이번 세션 규칙: simulate_quarantine()은 dry_run=True가 기본값이며, 이 세션에서는
dry_run=False로 호출하지 않는다(= 실제 shutil.move가 일어나지 않는다). 실제 이동은
국장이 후보 목록을 확인한 뒤 별도 지시로만 트리거된다.

정직한 이중지표: storage/_janitor_trash도 같은 드라이브(D:) 안이라 이동만으로는
디스크 여유공간이 늘지 않는다. "정리됨(quarantined_bytes)"과 "회수됨(reclaimed_bytes)"을
절대 같은 숫자로 보고하지 않는다 — 회수됨은 영구비우기(미구현, ST-3 게이트 그 다음)가
실행된 뒤에만 0보다 커진다.

이중 안전망: 오격리되어도 semantic 조각 썸네일은 main.py:1642-1729
inject_semantic_thumbnails()의 3단 폴백(존재확인 -> 원본에서 즉석 재추출 -> 부모 VF
썸네일 대체)으로 앱이 자가복구한다.
"""
import json
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from . import grades

QUARANTINE_DIR = grades.STORAGE_ROOTS[0] / grades.QUARANTINE_DIR_NAME
JOURNAL_PATH = QUARANTINE_DIR / "_journal.jsonl"


@dataclass
class JournalEntry:
    """Receipt 계열 저널 1행. 무엇을·왜·언제·어디서→어디로."""
    what: str        # 무엇을 — 원본(이동 전) 파일 경로
    why_reason: str  # 왜 — orphan_fragment / orphan_source_proxy / stale_idle 등
    why_level: int    # 왜 — Level(현재는 Level3만 대상)
    when_ts: float    # 언제 — epoch seconds
    src: str          # 어디서
    dst: str          # 어디로


def _dst_for(candidate_path: Path) -> Path:
    """storage 루트 기준 상대경로 구조를 격리 디렉토리 밑에 그대로 보존."""
    for root in grades.STORAGE_ROOTS:
        try:
            rel = candidate_path.resolve().relative_to(root.resolve())
            return QUARANTINE_DIR / root.name / rel
        except ValueError:
            continue
    return QUARANTINE_DIR / candidate_path.name


def simulate_quarantine(candidates, dry_run: bool = True) -> dict:
    """격리 이동을 시뮬레이션(기본, dry_run=True)하거나 실제 실행(dry_run=False)한다.

    dry_run=True(기본값): 대상·용량·src->dst 매핑만 계산. 파일 이동 없음, 저널 기록 없음
      (plan_sample에 저널 프리뷰만 포함).
    dry_run=False: 실제 shutil.move + 저널 append. 이번 세션에서는 호출하지 않는다.
    """
    plan = []
    total_bytes = 0
    skipped_protected = 0

    for c in candidates:
        src = Path(c.path)
        # 이중 방어: 후보 리스트가 이미 걸러졌어야 하나, 이동 직전에 다시 한번 확인.
        if grades.is_protected(src):
            skipped_protected += 1
            continue
        dst = _dst_for(src)
        plan.append({
            "src": str(src), "dst": str(dst), "bytes": c.size_bytes,
            "reason": c.reason, "level": c.level,
        })
        total_bytes += c.size_bytes

    result = {
        "dry_run": dry_run,
        "quarantine_dir": str(QUARANTINE_DIR),
        "retention_days": grades.QUARANTINE_RETENTION_DAYS,
        "planned_files": len(plan),
        "skipped_protected": skipped_protected,
        # 정직한 이중지표 — 절대 혼동 금지.
        "quarantined_bytes": 0,             # 실제로 옮겨진 양(격리 완료분). dry-run이면 0.
        "quarantined_bytes_planned": total_bytes,  # 옮길 예정인 양(시뮬레이션 값).
        "reclaimed_bytes": 0,               # 회수된 디스크 공간. 같은 드라이브 이동이라 항상 0.
        "executed": False,
        "journal_written": False,
    }

    if dry_run:
        result["plan_sample"] = plan[:20]
        result["plan_sample_note"] = (
            f"전체 {len(plan)}건 중 앞 20건만 미리보기. 저널은 미기록(dry-run)."
        )
        return result

    # ── 아래는 dry_run=False일 때만 실행되는 실제 이동 경로.
    #    이번 세션에서는 이 분기가 호출되지 않는다(국장 최종 지시 이후에만). ──
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    journal_entries = []
    moved_files = 0
    moved_bytes = 0
    for item in plan:
        src = Path(item["src"])
        dst = Path(item["dst"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved_files += 1
        moved_bytes += item["bytes"]
        journal_entries.append(JournalEntry(
            what=item["src"], why_reason=item["reason"], why_level=item["level"],
            when_ts=time.time(), src=item["src"], dst=item["dst"],
        ))

    with open(JOURNAL_PATH, "a", encoding="utf-8") as jf:
        for entry in journal_entries:
            jf.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    result["executed"] = True
    result["journal_written"] = True
    result["moved_files"] = moved_files
    result["quarantined_bytes"] = moved_bytes
    return result
