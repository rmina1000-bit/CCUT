# -*- coding: utf-8 -*-
"""[FIX-CORRECT 2026-08-11] 24과제가 안 덮는 자리를 말로 돌린다.

  · 정정한 뒤 "되돌려줘" 가 여전히 되는가 (restore_fragment 회귀)
  · 마른 경로 — 되돌릴 직전 실행이 ★없는데★ 정정하면?
  · restore_fragment 단독 (TASKS 에 한 칸도 없다)
무대·원복은 night2_harness 를 그대로 쓴다(두 벌 금지).
"""
import io
import json
import sys
import time

BACKEND = "D:/CCUT1.0.4/ccut_backend"
sys.path.insert(0, BACKEND)
sys.path.insert(0, BACKEND + "/scripts")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import night2_harness as H          # noqa: E402

SCEN = [
    ("S1 정정 뒤 되돌리기",
     ["3번째 조각 빼줘", "아 잘못 말했어. 4번째였어", "방금 거 되돌려줘"]),
    ("S2 마른 경로(첫 턴 정정)",
     ["아니야, 두번째조각은 a60이야"]),
    ("S3 restore_fragment 단독",
     ["3번째 조각 빼줘", "방금 거 되돌려줘"]),
    ("S4 정정 뒤 또 정정",
     ["마지막 조각 빼줘", "아니 그거 말고 첫번째", "아니 잘못 말했어 두번째였어"]),
]


def main():
    base = H.state(H.STAGE)
    labels = H.stage_labels(base)
    inv = {v: k for k, v in labels.items()}
    nm = lambda fs: [inv.get(f, f[3:9]) for f in fs]
    H.jsonl(f"{H.OUTDIR}/fixcorrect_scenarios_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    print(f"[무대] live {nm(base['live'])} fp={base['fp']}")
    for name, turns in SCEN:
        r = H.restore(H.STAGE, base, verbose=False)
        print(f"\n=== {name} · 원복 {'OK' if r['ok'] else '★불일치 ' + r['why']}")
        hist = []
        for i, u in enumerate(turns, 1):
            rec, _, _ = H.run_turn(H.STAGE, u, hist, labels,
                                   {"task": name, "turn": i})
            hist.append({"sender": "user", "text": u})
            hist.append({"sender": "ai", "text": rec["reply"]})
            print(f"  T{i} 사용자: {u!r}")
            print(f"     kind={rec['kind']} cap={rec['cap'] or '-'} "
                  f"args={json.dumps(rec['args'], ensure_ascii=False)}")
            print(f"     원고 {nm(rec['live_before'])} → {nm(rec['live_after'])}")
            print(f"     결: {rec['reply']}")
    H.restore(H.STAGE, base, verbose=False)
    print("\n[끝] 무대 원복 완료")


if __name__ == "__main__":
    sys.exit(main() or 0)
