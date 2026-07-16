"""[STORAGE-1 ST-1] 등급 사전 — 경로 패턴 -> Level 매핑을 이 파일 1곳에만 둔다.

원칙: deny-by-default. GRADE_MAP에 없는 디렉토리명은 UNKNOWN 등급이며,
janitor는 UNKNOWN을 삭제후보 자격이 아예 없는 것으로 취급한다(등급표 밖 = 삭제불가).

보호경로 절대목록(PROTECTED_DIR_NAMES / PROTECTED_SUFFIXES / PROTECTED_ABS_DIRS)은
등급 계산보다 먼저 적용되는 하드 거부 — Level이 몇이든 무관하게 후보에서 제외된다.
"""
import os
from pathlib import Path

# ── 실경로 ──────────────────────────────────────────────────────────
STORAGE_MANAGER_DIR = Path(__file__).resolve().parent
CCUT_BACKEND_DIR = STORAGE_MANAGER_DIR.parent
PROJECT_ROOT = CCUT_BACKEND_DIR.parent

# 두 개의 실제 storage 트리(ST-0 계측에서 확정). 순서 유지.
STORAGE_ROOTS = [
    PROJECT_ROOT / "storage",
    CCUT_BACKEND_DIR / "storage",
]

DB_PATH = CCUT_BACKEND_DIR / "ccut_app.db"

# ── 등급 ────────────────────────────────────────────────────────────
class Level:
    LEVEL1 = 1   # 대본·EditState·Timeline·Receipt·Export결과·설정·학습데이터 + 조각경계/anchor좌표/semantic메타
    LEVEL2 = 2   # 임베딩·키프레임·대표이미지·검색인덱스·StoryCache
    LEVEL3 = 3   # Proxy·Preview·Thumbnail·VLCache·Panorama·OCR·Temp·과거세대잔존물
    UNKNOWN = None  # 등급 사전 밖 — deny-by-default(삭제 후보 자격 없음)


LEVEL_LABELS = {
    Level.LEVEL1: "Level1(보호)",
    Level.LEVEL2: "Level2(재생성비용有)",
    Level.LEVEL3: "Level3(재생성캐시)",
    Level.UNKNOWN: "UNKNOWN(등급표밖-거부)",
}

# 디렉토리명(storage 루트 바로 아래 1단계) -> Level.
# Level3만 janitor 삭제후보 대상이 될 수 있음(추가로 개별 파일이 "현행 대응분"인지도 확인해야 함).
GRADE_MAP = {
    # --- Level 3: 재생성 가능 캐시 (원본+메타데이터로 다시 만들 수 있음) ---
    "thumbnails": Level.LEVEL3,
    "proxies": Level.LEVEL3,
    "proposal_previews": Level.LEVEL3,
    "preview_clips": Level.LEVEL3,
    "search_keyframes": Level.LEVEL3,   # VLCache(조각검색 키프레임)
    "panorama": Level.LEVEL3,
    "cache": Level.LEVEL3,
    "temp_clips": Level.LEVEL3,
    "raw_frames": Level.LEVEL3,
    "generative": Level.LEVEL3,
    "voice_samples": Level.LEVEL3,
    "dubbing": Level.LEVEL3,

    # --- Level 2: 임베딩/인덱스/스토리 캐시 (재생성 비용 있음 — 신중 취급) ---
    "qdrant_db": Level.LEVEL2,
    "fragment_index": Level.LEVEL2,

    # --- Level 1: 절대 보호급 콘텐츠. 디스크상 실체가 있는 것만 여기 표기.
    #     (대본/EditState/Timeline/Receipt/설정/학습데이터/조각경계·anchor좌표/semantic메타는
    #      전부 DB 행이라 디스크 디렉토리가 아님 — PROTECTED_ABS_DIRS의 "DB 일체" 룰로 보호됨)
    "uploads": Level.LEVEL1,
    "exports": Level.LEVEL1,
    "trash": Level.LEVEL1,     # 소프트삭제 휴지통. 프로젝트 30일 보관정책 소관 — janitor 대상 아님
    "faces": Level.LEVEL1,
    "qa_isolated_storage": Level.LEVEL1,  # 정체 불명 — deny 쪽으로 안전하게
    "failures": Level.LEVEL1,
    "fragments": Level.LEVEL1,  # storage/fragments (원본류 자리, 현재 빈 디렉토리라도 등급은 보호)
}


def classify_dir(dirname: str):
    """1단계 디렉토리명 -> Level. 사전에 없으면 UNKNOWN(=deny-by-default)."""
    return GRADE_MAP.get(dirname, Level.UNKNOWN)


# ── ST-3 격리(quarantine) 상수 ──────────────────────────────────────
QUARANTINE_DIR_NAME = "_janitor_trash"   # STORAGE_ROOTS[0] 바로 아래. 물리 영구삭제 아님, 이동만.
QUARANTINE_RETENTION_DAYS = 7            # 격리 보존기간(이 기간 후에야 영구비우기 검토 대상)

# ── 보호경로 절대목록 (등급과 무관하게 하드 거부) ──────────────────────
# 디렉토리명 자체가 이거면 무조건 보호(원본 업로드 + 격리소 자체 재귀 스캔 방지).
PROTECTED_DIR_NAMES = {"uploads", QUARANTINE_DIR_NAME}

# 파일명 접미사/패턴이 이거면 무조건 보호(DB 일체).
PROTECTED_FILE_SUFFIXES = (".db", ".db-wal", ".db-shm")
PROTECTED_FILE_SUBSTRINGS = (".bak",)  # *.bak* 전부(경로 어디에 있든)

# 절대 경로 자체가 보호 디렉토리인 것들.
PROTECTED_ABS_DIRS = [
    CCUT_BACKEND_DIR / "db_snapshots",
    CCUT_BACKEND_DIR / "backups",
    Path("D:/CCUT_V2_EVIDENCE"),
]


def is_protected(path: Path) -> bool:
    """절대 보호 경로 여부. 등급 계산보다 먼저 호출되어야 한다.

    - worktree(PROJECT_ROOT) 밖의 모든 경로는 무조건 보호(거부).
    - uploads 디렉토리 하위는 무조건 보호.
    - *.db / *.db-wal / *.db-shm / *.bak* 는 무조건 보호.
    - db_snapshots/backups/D:\\CCUT_V2_EVIDENCE\\ 하위는 무조건 보호.
    """
    path = Path(path).resolve()

    # worktree 밖 전부 거부
    try:
        path.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return True

    parts = set(path.parts)
    if PROTECTED_DIR_NAMES & parts:
        return True

    name = path.name
    if name.endswith(PROTECTED_FILE_SUFFIXES):
        return True
    if any(sub in name for sub in PROTECTED_FILE_SUBSTRINGS):
        return True

    resolved = path.resolve()
    for prot in PROTECTED_ABS_DIRS:
        try:
            resolved.relative_to(prot.resolve())
            return True
        except (ValueError, OSError):
            continue

    return False


# ── 임계값 상수 (숨기지 않고 여기 1곳에 명시) ──────────────────────────
WATERMARK_SOFT = 70       # % — 이 이상이면 Level3 후보 산출 시작 권고
WATERMARK_HARD = 85       # % — 이 이상이면 적극 정리 권고
WATERMARK_CRITICAL = 95   # % — 이 이상이면 긴급(ST-3 승인 필요는 동일)

ARCHIVE_IDLE_DAYS = 90    # 이 기간 이상 미접근 시 아카이브/정리 후보 가중치

WORKSPACE_CAP_GB = float(os.getenv("CCUT_WORKSPACE_CAP_GB", "100"))  # 설정 가능(env override)
