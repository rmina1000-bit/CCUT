# -*- coding: utf-8 -*-
"""[V2-α] Receipt — request_id 단위 전 단계 영수증.

헌장 §영수증: 모든 실행은 원문→계약→채널근거→후보까지 한 장으로 남긴다.
저장 위치: stdout + D:\\CCUT_V2_EVIDENCE\\V2_ALPHA_01\\ 만 (repo 내 JSON 생성 금지).
국장 판정 필드는 빈칸으로 동봉 — 채점은 사람 몫.
"""
import datetime
import json
import os

OUT_DIR = r"D:\CCUT_V2_EVIDENCE\V2_ALPHA_01"


def build_receipt(work_order, retrieval, timing_ms=None):
    return {
        "request_id": work_order.request_id,
        "created_at": datetime.datetime.now().isoformat(),
        "work_order": work_order.to_dict(),
        "retrieval": {
            "query_used": retrieval["query_used"],
            "channels_raw": retrieval["channels_raw"],
            "candidates": retrieval["candidates"],
        },
        "timing_ms": timing_ms,
        "director_verdict": {          # 국장 판정 — 빈칸
            "grade": "",
            "reason": "",
            "director_note": "",
        },
    }


def save_receipt(receipt, label):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"receipt_{label}_{receipt['request_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    return path
