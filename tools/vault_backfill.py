# -*- coding: utf-8 -*-
"""[조각 금고] 과거분 일괄 적재 — 수동/스케줄 실행 전용, 서버 부팅과 분리.

기존 backfill_all()을 main.py 부팅 경로에 두면 sources가 늘수록 시작 지연이
선형으로 커진다는 지적(2026-07-05)을 반영해 여기로 뺐다. 신규 적재는
조각화 완료 시점 증분 훅(main.py의 POST /semantic-fragments)이 처리하므로,
이 스크립트는 "vault 도입 이전에 이미 존재하던 원본"을 한 번 채워 넣는 용도다.

실행: python tools/vault_backfill.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccut_backend"))


def main():
    from engine import fragment_vault as fv
    r = fv.backfill_all()
    n_dead = fv.mark_source_alive()
    print(f"[VAULT] 완료: sources={r['sources']} 신규={r['inserted']} 병합={r['merged']} "
          f"원본유실={n_dead}")
    print(fv.stats())
    return 0


if __name__ == "__main__":
    sys.exit(main())
