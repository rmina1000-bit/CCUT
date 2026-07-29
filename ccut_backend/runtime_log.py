"""[LAB-42] 단일 로그 라인 — 어떤 기동 경로로 떠도 같은 파일에 남는다.

왜 코드인가:
  구조상 로그가 런처마다 갈렸다 —
    run_backend.bat            파일 로그 0건 (콘솔만, 국장 평소 경로)
    run_backend.ps1            파일 로그 0건
    run_backend_supervised.ps1 backend_<ts>.out/.err.log
  그래서 "어느 경로로 띄웠나"가 사고 조사 가능 여부를 갈랐다. 베타 테스터가
  bat으로 띄우면 에러는 창을 닫는 순간 사라졌다.
  이제 로그 장착은 런처가 아니라 백엔드 자신이 한다.

동작:
  - logs/backend.log 한 곳으로 stdout/stderr(=print 212곳) + logging 을 모은다.
  - 콘솔 출력은 그대로 유지(tee) — 기존 관찰 방식 무변.
  - 회전: 기동 시 크기 초과면 backend_<ts>.log 로 넘기고, 14일 지난 회전본 정리.
  - 실패해도 절대 죽지 않는다 — 로그 장착 실패가 백엔드 기동을 막으면 본말전도.
"""
import os
import re
import sys
import time
import datetime

# uvicorn 등이 콘솔 색상용으로 넣는 ANSI escape — 파일에는 남기지 않는다.
# (테스터가 메모장으로 열었을 때 [32mINFO[0m 같은 잡음이 보이면 안 된다)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BACKEND_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "backend.log")
MAX_BYTES = 20 * 1024 * 1024   # 20MB 넘으면 기동 시 회전
KEEP_DAYS = 14

_installed = False


class _Tee:
    """콘솔과 파일에 동시에 쓰는 스트림. 파일 쓰기 실패는 콘솔을 막지 않는다."""

    def __init__(self, console, fp):
        self._console = console
        self._fp = fp

    def write(self, data):
        try:
            if self._console is not None:
                self._console.write(data)
        except Exception:
            pass
        try:
            self._fp.write(_ANSI_RE.sub("", data) if data else data)
            self._fp.flush()
        except Exception:
            pass
        return len(data) if data else 0

    def flush(self):
        for s in (self._console, self._fp):
            try:
                if s is not None:
                    s.flush()
            except Exception:
                pass

    def isatty(self):
        try:
            return self._console is not None and self._console.isatty()
        except Exception:
            return False

    def fileno(self):
        # uvicorn/일부 라이브러리가 fileno를 묻는다 — 콘솔 것을 그대로 넘긴다.
        if self._console is None:
            raise OSError("no console stream")
        return self._console.fileno()

    @property
    def encoding(self):
        try:
            return self._console.encoding
        except Exception:
            return "utf-8"


def _rotate_and_prune():
    """기동 시점 회전 + 오래된 회전본 정리."""
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_BYTES:
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            os.replace(LOG_PATH, os.path.join(LOG_DIR, f"backend_{stamp}.log"))
    except Exception:
        pass
    try:
        cutoff = time.time() - KEEP_DAYS * 86400
        for name in os.listdir(LOG_DIR):
            if not (name.startswith("backend_") and name.endswith(".log")):
                continue
            p = os.path.join(LOG_DIR, name)
            try:
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
            except OSError:
                pass
    except Exception:
        pass


def install() -> str:
    """stdout/stderr/logging 을 logs/backend.log 로 일원화. 로그 경로 반환(실패 시 '')."""
    global _installed
    if _installed:
        return LOG_PATH
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _rotate_and_prune()
        fp = open(LOG_PATH, "a", encoding="utf-8", errors="replace", buffering=1)
        sys.stdout = _Tee(sys.stdout, fp)
        sys.stderr = _Tee(sys.stderr, fp)

        import logging
        root = logging.getLogger()
        if not any(getattr(h, "_ccut_runtime_log", False) for h in root.handlers):
            h = logging.StreamHandler(sys.stdout)   # tee 를 통과 → 같은 파일
            h.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s"))
            h._ccut_runtime_log = True
            root.addHandler(h)
            root.setLevel(logging.INFO)

        _installed = True
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        print(f"[RUNTIME-LOG] 장착 완료 {stamp} pid={os.getpid()} -> {LOG_PATH}")
        return LOG_PATH
    except Exception as e:
        try:
            print(f"[RUNTIME-LOG][WARN] 장착 실패 — 콘솔만 사용: {e}")
        except Exception:
            pass
        return ""
