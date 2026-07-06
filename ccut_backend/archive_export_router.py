"""[아카이브 바구니 내보내기 MVP 2026-07-06] 바구니 조각 → 표준 MP4 클립 export.

원칙:
- 클라이언트 start/end를 그대로 믿지 않는다. fragment_id로 DB에서 source_id/start/end 재조회.
- 원본 파일 없으면 그 조각만 실패 목록, 나머지는 계속 진행.
- H.264/AAC MP4. DB/임베딩/내부 점수는 내보내지 않는다(manifest 최소).
- proposal_engine/project_sources와 무관 — 순수 파일 export.
"""
import os
import re
import subprocess
import sqlite3
import datetime
import threading
import time
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent
_DB_PATH = str(_BACKEND_DIR / "ccut_app.db")
_EXPORT_ROOT = _PROJECT_ROOT / "storage" / "exports" / "archive_basket"
_XML_TIMEBASE = 30


def _connect():
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


class BasketItem(BaseModel):
    fragment_id: str


class BasketExportRequest(BaseModel):
    items: list[BasketItem] = []


class OpenFolderRequest(BaseModel):
    export_dir: str


def _resolve_fragment(con, fragment_id: str):
    """fragment_id → (source_id, title, file_path, start, end). 없으면 None. 재검증 진실원."""
    row = con.execute(
        "SELECT source_id, display_name, start, end FROM fragment_vault WHERE fragment_id=?",
        (fragment_id,)).fetchone()
    if row:
        source_id, display_name = row["source_id"], row["display_name"]
        start, end = row["start"], row["end"]
    else:
        row2 = con.execute(
            "SELECT source_id, start, end FROM semantic_fragments WHERE fragment_id=?",
            (fragment_id,)).fetchone()
        if not row2:
            return None
        source_id, display_name = row2["source_id"], None
        start, end = row2["start"], row2["end"]

    src = con.execute("SELECT title, file_path FROM sources WHERE source_id=?",
                      (source_id,)).fetchone()
    title = (src["title"] if src else None) or source_id
    file_path = src["file_path"] if src else None
    return {"source_id": source_id, "title": title, "file_path": file_path,
            "start": start, "end": end,
            "display_name": display_name}


def _safe_name(s: str) -> str:
    base = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", str(s or ""))       # 확장자 제거
    base = re.sub(r"[^0-9A-Za-z가-힣]+", "_", base).strip("_")
    return base or "clip"


def _ffmpeg_clip(src_path: str, start: float, end: float, out_path: str) -> bool:
    cmd = [
        "ffmpeg", "-ss", str(max(0.0, float(start or 0))),
        "-to", str(float(end or 0)), "-i", src_path,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-movflags", "+faststart", "-y", out_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception as e:
        print(f"[ARCHIVE-EXPORT] ffmpeg 실패 {out_path}: {e}")
        return False


def _frames(sec: float) -> int:
    return max(1, int(round(float(sec or 0) * _XML_TIMEBASE)))


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _write_premiere_xml(export_dir: Path, exported_items: list[dict]) -> str | None:
    if not exported_items:
        return None

    total_frames = sum(_frames(item["duration_sec"]) for item in exported_items)
    timeline_pos = 0
    clip_xml = []

    for idx, item in enumerate(exported_items, start=1):
        duration_frames = _frames(item["duration_sec"])
        start_frame = timeline_pos
        end_frame = timeline_pos + duration_frames
        timeline_pos = end_frame

        clip_file = escape(item["clip_file"])
        clip_path = escape(_file_url(export_dir / item["clip_file"]))
        clip_name = escape(Path(item["clip_file"]).stem)
        file_id = f"file-{idx}"

        clip_xml.append(f"""            <clipitem id=\"clipitem-{idx}\">
              <name>{clip_name}</name>
              <duration>{duration_frames}</duration>
              <rate><timebase>{_XML_TIMEBASE}</timebase><ntsc>FALSE</ntsc></rate>
              <start>{start_frame}</start>
              <end>{end_frame}</end>
              <in>0</in>
              <out>{duration_frames}</out>
              <file id=\"{file_id}\">
                <name>{clip_file}</name>
                <pathurl>{clip_path}</pathurl>
                <rate><timebase>{_XML_TIMEBASE}</timebase><ntsc>FALSE</ntsc></rate>
                <duration>{duration_frames}</duration>
              </file>
            </clipitem>""")

    xml_text = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE xmeml>
<xmeml version=\"5\">
  <sequence id=\"sequence-1\">
    <name>CCUT Basket Timeline</name>
    <duration>{total_frames}</duration>
    <rate><timebase>{_XML_TIMEBASE}</timebase><ntsc>FALSE</ntsc></rate>
    <media>
      <video>
        <format>
          <samplecharacteristics>
            <rate><timebase>{_XML_TIMEBASE}</timebase><ntsc>FALSE</ntsc></rate>
            <width>1920</width>
            <height>1080</height>
            <anamorphic>FALSE</anamorphic>
            <pixelaspectratio>square</pixelaspectratio>
            <fielddominance>none</fielddominance>
          </samplecharacteristics>
        </format>
        <track>
{chr(10).join(clip_xml)}
        </track>
      </video>
    </media>
  </sequence>
</xmeml>
"""
    xml_path = export_dir / "CCUT_Premiere.xml"
    xml_path.write_text(xml_text, encoding="utf-8")
    return str(xml_path)


def _open_explorer_foreground(target: Path):
    """내보낸 폴더를 탐색기로 열고 브라우저 앞으로 끌어올린다.

    os.startfile(ShellExecute)는 경로/창재사용은 정확하지만, 백그라운드(uvicorn)
    프로세스는 Windows 포그라운드 락 때문에 창이 브라우저 뒤로 열린다.
    (AllowSetForegroundWindow는 포그라운드를 이미 가진 프로세스에서만 유효 → 무의미.)
    그래서 창을 실제로 앞으로 올리려면:
      1) 대상 폴더의 탐색기 창(CabinetWClass, 제목=폴더명)을 찾고,
      2) 합성 ALT 키 탭으로 포그라운드 락을 리셋한 뒤,
      3) SetForegroundWindow/BringWindowToTop, 그래도 안 되면 최소화→복원으로 강제.
    HTTP 응답을 막지 않도록 별도 스레드에서 수행한다.
    """
    threading.Thread(target=_open_and_focus, args=(target,), daemon=True).start()


def _open_and_focus(target: Path):
    folder = os.path.normpath(str(target.resolve()))
    basename = os.path.basename(folder)

    # 폴더 열기(또는 같은 폴더 창 재사용). 실패 시 explorer /select 폴백.
    try:
        os.startfile(folder)  # type: ignore[attr-defined]  # Windows 전용
    except Exception as e:
        print(f"[ARCHIVE-EXPORT] os.startfile 실패 {folder}: {e}")
        try:
            first = next((p for p in sorted(Path(folder).glob("*.mp4"))), None)
            subprocess.Popen(["explorer", f"/select,{first}"] if first else ["explorer", folder])
        except Exception as e2:
            print(f"[ARCHIVE-EXPORT] explorer 폴백 실패: {e2}")
        return

    # 열린 탐색기 창을 포그라운드로 (best-effort)
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        for fn, args in (
            ("IsWindowVisible", [wintypes.HWND]),
            ("GetClassNameW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
            ("GetWindowTextLengthW", [wintypes.HWND]),
            ("GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
            ("SetForegroundWindow", [wintypes.HWND]),
            ("BringWindowToTop", [wintypes.HWND]),
            ("SetActiveWindow", [wintypes.HWND]),
            ("ShowWindow", [wintypes.HWND, ctypes.c_int]),
        ):
            getattr(u, fn).argtypes = args
        u.GetForegroundWindow.restype = wintypes.HWND

        def find_hwnd():
            box = {"h": None}

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def cb(hwnd, _):
                if not u.IsWindowVisible(hwnd):
                    return True
                cls = ctypes.create_unicode_buffer(64)
                u.GetClassNameW(hwnd, cls, 64)
                if cls.value in ("CabinetWClass", "ExploreWClass"):
                    ln = u.GetWindowTextLengthW(hwnd)
                    buf = ctypes.create_unicode_buffer(ln + 1)
                    u.GetWindowTextW(hwnd, buf, ln + 1)
                    if basename.lower() in buf.value.lower():
                        box["h"] = hwnd
                        return False
                return True

            u.EnumWindows(cb, 0)
            return box["h"]

        hwnd = None
        for _ in range(30):  # 셸이 창을 만들 때까지 최대 ~3초
            hwnd = find_hwnd()
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            return

        VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
        SW_RESTORE, SW_MINIMIZE = 9, 6
        # 합성 ALT 탭 → 포그라운드 락 해제 후 앞으로
        u.keybd_event(VK_MENU, 0, 0, 0)
        u.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        u.ShowWindow(hwnd, SW_RESTORE)
        u.SetForegroundWindow(hwnd)
        u.BringWindowToTop(hwnd)
        u.SetActiveWindow(hwnd)
        # 그래도 못 올라오면 최소화→복원으로 강제 활성화
        if u.GetForegroundWindow() != hwnd:
            u.ShowWindow(hwnd, SW_MINIMIZE)
            u.ShowWindow(hwnd, SW_RESTORE)
            u.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"[ARCHIVE-EXPORT] 포그라운드 끌어올리기 실패: {e}")


@router.post("/archive/basket/export")
async def archive_basket_export(body: BasketExportRequest):
    items = body.items or []
    if not items:
        return {"status": "ERROR", "message": "바구니가 비어 있습니다."}

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = _EXPORT_ROOT / ts
    export_dir.mkdir(parents=True, exist_ok=True)

    con = _connect()
    exported_items = []
    failed = []
    total_dur = 0.0
    idx = 0

    for it in items:
        fid = (it.fragment_id or "").strip()
        info = _resolve_fragment(con, fid)
        if not info:
            failed.append({"fragment_id": fid, "reason": "DB에서 조각을 찾지 못함"})
            continue
        if not info["file_path"] or not os.path.exists(info["file_path"]):
            failed.append({"fragment_id": fid, "reason": "원본 파일 없음", "source_title": info["title"]})
            continue

        idx += 1
        start, end = float(info["start"] or 0), float(info["end"] or 0)
        clip_name = f"{idx:03d}_{_safe_name(info['title'])}_{int(start)}_{int(end)}.mp4"
        out_path = export_dir / clip_name
        if not _ffmpeg_clip(info["file_path"], start, end, str(out_path)):
            idx -= 1
            failed.append({"fragment_id": fid, "reason": "클립 생성 실패", "source_title": info["title"]})
            continue

        duration_sec = max(0.0, end - start)
        total_dur += duration_sec
        exported_items.append({
            "fragment_id": fid,
            "source_id": info["source_id"],
            "source_title": _safe_name(info["title"]),
            "start_sec": round(start, 2),
            "end_sec": round(end, 2),
            "duration_sec": round(duration_sec, 3),
            "clip_file": clip_name,
        })

    con.close()
    xml_path = _write_premiere_xml(export_dir, exported_items)

    return {
        "status": "OK",
        "export_dir": str(export_dir),
        "premiere_xml": xml_path,
        "ok_count": len(exported_items),
        "requested": len(items),
        "duration_sec": round(total_dur, 1),
        "failed": failed,
        "clips": exported_items,
    }


@router.post("/archive/basket/export/open-folder")
async def open_export_folder(body: OpenFolderRequest):
    """내보낸 폴더를 탐색기로 연다. 경로탈출 방지: export 루트 하위만 허용."""
    try:
        target = Path(body.export_dir).resolve()
        root = _EXPORT_ROOT.resolve()
        if target != root and not target.is_relative_to(root):
            return {"status": "ERROR", "message": "허용되지 않은 경로입니다."}
        if not target.exists() or not target.is_dir():
            return {"status": "ERROR", "message": "폴더가 없습니다."}
        _open_explorer_foreground(target)
        return {"status": "OK", "opened": str(target)}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}
