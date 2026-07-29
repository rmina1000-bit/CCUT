"""[LAB-42 폐쇄] 이 경로는 폐쇄됨 — 로그는 runtime_log(logs/backend.log)를 쓴다.

폐쇄 근거(2026-07-30 전수 실측):
  - LOG_PATH가 존재하지 않는 드라이브(d:/CCUT_1.0.3)를 가리켜 모든 파일 쓰기가
    `except: pass`로 삼켜지고 있었다 — 조용한 실패.
  - 호출처 전수: import 1건(engine/signal_processor.py:6)뿐, blackbox.log(...)
    실제 호출 0건. 아무것도 기록하지 않은 채 살아 있는 척만 했다.
기능(파일 쓰기·psutil 수집)은 죽이고 import 하위호환만 남긴다 — 조용한 부활 금지.
"""
import json
import datetime

CLOSED_NOTICE = ("engine.blackbox 는 폐쇄되었습니다. "
                 "로그는 runtime_log(ccut_backend/logs/backend.log)를 사용하세요.")


class BlackBoxRecorder:
    """폐쇄된 기록기. 파일 쓰기 없음 — print만 남아 runtime_log tee를 타고
    logs/backend.log 로 흘러간다."""

    @staticmethod
    def log(category, msg, data=None):
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        suffix = f" {json.dumps(data, ensure_ascii=False)}" if data else ""
        print(f"[{category}][BLACKBOX-CLOSED {stamp}] {msg}{suffix}")

    @staticmethod
    def record_system_stats():
        print(f"[SYSTEM][BLACKBOX-CLOSED] {CLOSED_NOTICE}")


blackbox = BlackBoxRecorder()
