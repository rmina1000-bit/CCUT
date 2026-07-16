"""[STORAGE-1 ST-2/ST-3] Janitor — watermark 계산 + 삭제(격리)후보 산출(목록/용량/사유).

물리 영구삭제는 이 모듈에 없다(delete_candidates는 ST-3 국장 승인 이후에도 "영구비우기" 전용으로
별도 구현될 것이며, 지금은 NotImplementedError 스텁). 격리(storage/_janitor_trash로 이동)는
quarantine.py가 담당하고, 이번 세션에서는 dry_run=True(기본값)로만 호출된다 — 실제 이동 없음.

이중 안전망 근거: 오격리(잘못 옮겨짐)되더라도 semantic 조각 썸네일은
main.py:1642-1729 inject_semantic_thumbnails()의 3단 폴백으로 앱이 자가복구한다
(1. SF 전용 썸네일 존재 확인 -> 2. 없으면 소스 원본에서 즉석 재추출 -> 3. 그래도 실패하면
부모 VF 썸네일로 대체). 격리와 이 자가복구 로직이 이중 안전망을 이룬다.
"""
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import grades
from .job_conductor import default_conductor, Stage

_SRC_RE = re.compile(r"(SRC_[0-9A-Fa-f]+)")
_PROJ_RE = re.compile(r"(proj_[0-9a-fA-F]+)")


# ── DB 조회 (read-only) ────────────────────────────────────────────
def _ro_connect(db_path: Path):
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _current_fragment_ids(db_path: Path) -> set:
    ids = set()
    con = _ro_connect(db_path)
    try:
        for row in con.execute("SELECT fragment_id FROM fragments"):
            ids.add(row[0])
        for row in con.execute("SELECT fragment_id FROM semantic_fragments"):
            ids.add(row[0])
    finally:
        con.close()
    return ids


def _current_source_ids(db_path: Path) -> set:
    con = _ro_connect(db_path)
    try:
        return {row[0] for row in con.execute("SELECT source_id FROM sources")}
    finally:
        con.close()


def _current_program_ids(db_path: Path) -> set:
    con = _ro_connect(db_path)
    try:
        return {row[0] for row in con.execute("SELECT program_id FROM programs")}
    finally:
        con.close()


# ── 파일명 -> id 추출 (휴리스틱, 실패 시 None = 판정 보류) ────────────
def _extract_thumb_fragment_id(name: str):
    """thumbnails/search_keyframes 공통. panorama(P_ 접두)와 SF/VF 조각 썸네일 구분.

    DEBT: P_{fid}_d{n}_{i}.jpg(밀도 변형 파노라마)는 마지막 "_숫자"만 잘라내므로
    fid에 "_d{n}"이 남아 실제 fragment_id와 불일치 -> 현행 조각이어도 orphan으로
    오탐할 수 있음. dry-run 후보 산출용이라 즉시 위험은 없으나(삭제는 ST-3 이후),
    ST-3 전에 밀도 접미사 정규식을 분리해야 함.
    """
    stem = name[:-4] if name.lower().endswith(".jpg") else name
    if stem.startswith("P_"):
        m = re.match(r"^P_(.+)_\d+$", stem)
        return m.group(1) if m else None
    return stem


def _extract_source_id(name: str):
    m = _SRC_RE.search(name)
    return m.group(1) if m else None


def _extract_program_id(name: str):
    m = _PROJ_RE.search(name)
    return m.group(1) if m else None


@dataclass
class Candidate:
    path: str
    level: int
    reason: str
    size_bytes: int
    mtime: float


@dataclass
class DryRunResult:
    candidates: list = field(default_factory=list)
    total_candidate_files: int = 0
    total_candidate_bytes: int = 0
    scanned_files: int = 0
    scanned_bytes: int = 0
    excluded_protected: int = 0
    excluded_non_level3: int = 0
    by_level_scanned: dict = field(default_factory=dict)


def _iter_level3_files(storage_root: Path):
    """storage_root 바로 아래 1단계 디렉토리를 등급 분류해 Level3인 것만 재귀 순회.

    _janitor_trash(격리소 자체)는 GRADE_MAP에 없어 UNKNOWN으로 자연 배제되지만,
    재계측 이중카운트 방지를 위해 여기서도 명시적으로 건너뛴다(방어 이중화).
    """
    if not storage_root.exists():
        return
    for entry in storage_root.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == grades.QUARANTINE_DIR_NAME:
            continue
        level = grades.classify_dir(entry.name)
        for f in entry.rglob("*"):
            if f.is_file():
                yield entry.name, level, f


def compute_dry_run(now: float = None, idle_days: int = None) -> DryRunResult:
    """read-only. Level3 파일만 후보 자격 검토, 그 안에서도 '현행 대응분'은 제외한다.

    사유(reason) 종류:
      - "orphan_fragment": thumbnails/search_keyframes 중 현재 fragments/semantic_fragments에
        없는 fragment_id로 추정되는 파일
      - "orphan_source_proxy": proxies 중 현재 sources에 없는 source_id
      - "orphan_program_preview": proposal_previews 중 현재 programs에 없는 program_id
      - "stale_idle": id 추출 규칙이 없는 Level3 디렉토리(cache/temp_clips 등)에서
        ARCHIVE_IDLE_DAYS 이상 미접근
    """
    now = now if now is not None else time.time()
    idle_days = idle_days if idle_days is not None else grades.ARCHIVE_IDLE_DAYS
    idle_cutoff = now - (idle_days * 86400)

    result = DryRunResult()

    frag_ids = _current_fragment_ids(grades.DB_PATH)
    src_ids = _current_source_ids(grades.DB_PATH)
    prog_ids = _current_program_ids(grades.DB_PATH)

    for storage_root in grades.STORAGE_ROOTS:
        for dirname, level, f in _iter_level3_files(storage_root):
            result.by_level_scanned[level] = result.by_level_scanned.get(level, 0) + 1

            try:
                st = f.stat()
            except OSError:
                continue
            result.scanned_files += 1
            result.scanned_bytes += st.st_size

            # 보호경로 하드 거부 — 등급과 무관하게 최우선
            if grades.is_protected(f):
                result.excluded_protected += 1
                continue

            if level != grades.Level.LEVEL3:
                result.excluded_non_level3 += 1
                continue

            reason = None
            if dirname in ("thumbnails", "search_keyframes"):
                fid = _extract_thumb_fragment_id(f.name)
                if fid is not None and fid not in frag_ids:
                    reason = "orphan_fragment"
            elif dirname == "proxies":
                sid = _extract_source_id(f.name)
                if sid is not None and sid not in src_ids:
                    reason = "orphan_source_proxy"
            elif dirname == "proposal_previews":
                pid = _extract_program_id(f.name)
                if pid is not None and pid not in prog_ids:
                    reason = "orphan_program_preview"
            else:
                # id 추출 규칙이 없는 Level3 디렉토리 — 순수 idle 기준만 적용
                if st.st_mtime < idle_cutoff:
                    reason = "stale_idle"

            if reason is not None:
                result.candidates.append(Candidate(
                    path=str(f), level=level, reason=reason,
                    size_bytes=st.st_size, mtime=st.st_mtime,
                ))

    result.total_candidate_files = len(result.candidates)
    result.total_candidate_bytes = sum(c.size_bytes for c in result.candidates)
    return result


def watermark_status(cap_gb: float = None) -> dict:
    """read-only. 두 storage 루트 합계 용량 대비 WORKSPACE_CAP_GB 워터마크 판정."""
    cap_gb = cap_gb if cap_gb is not None else grades.WORKSPACE_CAP_GB
    total_bytes = 0
    for root in grades.STORAGE_ROOTS:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.is_file():
                try:
                    total_bytes += f.stat().st_size
                except OSError:
                    pass
    used_gb = total_bytes / (1024 ** 3)
    pct = round((used_gb / cap_gb) * 100, 1) if cap_gb > 0 else 0.0

    if pct >= grades.WATERMARK_CRITICAL:
        tier = "CRITICAL"
    elif pct >= grades.WATERMARK_HARD:
        tier = "HARD"
    elif pct >= grades.WATERMARK_SOFT:
        tier = "SOFT"
    else:
        tier = "OK"

    return {
        "used_gb": round(used_gb, 2),
        "cap_gb": cap_gb,
        "pct": pct,
        "tier": tier,
        "thresholds": {
            "soft": grades.WATERMARK_SOFT,
            "hard": grades.WATERMARK_HARD,
            "critical": grades.WATERMARK_CRITICAL,
        },
    }


def run_dry_run_job() -> dict:
    """Job Conductor에 등록해 dry-run을 수행 — 여전히 read-only."""
    job = default_conductor.enqueue("janitor_dry_run")
    default_conductor.set_stage(job.job_id, Stage.RUNNING)
    try:
        wm = watermark_status()
        dr = compute_dry_run()
        summary = {
            "job_id": job.job_id,
            "watermark": wm,
            "scanned_files": dr.scanned_files,
            "scanned_bytes": dr.scanned_bytes,
            "excluded_protected": dr.excluded_protected,
            "excluded_non_level3": dr.excluded_non_level3,
            "by_level_scanned": dr.by_level_scanned,
            "candidate_files": dr.total_candidate_files,
            "candidate_bytes": dr.total_candidate_bytes,
            "candidates_by_reason": _group_by_reason(dr.candidates),
            # 정직한 이중지표: 같은 드라이브 격리(trash 이동)는 디스크를 비우지 않는다.
            # "정리됨"(격리 이동 대상)과 "회수됨"(영구비우기 후 실제 확보 공간)을 절대 섞지 않는다.
            "tidied_bytes_if_quarantined": dr.total_candidate_bytes,  # 정리됨(격리 시)
            "reclaimed_bytes": 0,  # 회수됨 — 격리 단계에서는 항상 0(같은 드라이브 이동이라 디스크 안 비움)
        }
        default_conductor.set_result(job.job_id, summary)
        default_conductor.set_stage(job.job_id, Stage.DONE)
        return summary
    except Exception as e:
        default_conductor.set_error(job.job_id, str(e))
        raise


def _group_by_reason(candidates):
    out = {}
    for c in candidates:
        g = out.setdefault(c.reason, {"files": 0, "bytes": 0})
        g["files"] += 1
        g["bytes"] += c.size_bytes
    return out


def delete_candidates(*args, **kwargs):
    """[ST-3 게이트] 실삭제는 국장 승인 이후에만 구현된다. 지금은 미구현."""
    raise NotImplementedError(
        "delete_candidates()는 ST-3 국장 승인 게이트 이후 구현 대상입니다. "
        "지금은 dry-run(compute_dry_run/run_dry_run_job)만 지원합니다."
    )
