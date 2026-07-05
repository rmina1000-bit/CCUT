# -*- coding: utf-8 -*-
"""[기초층 §6] 아카이브 무결성 스캔 — read-only. DB↔파일 양방향 대조 리포트.

설계 근거: DESIGN_ccut_archive_v2_2026-07-05.md (Plex 정합 스캐너 패턴 P5).
어떤 것도 수정·삭제하지 않는다 — Tier D(잔여물) '목록'을 만들 뿐이며,
삭제는 정리 버튼(사용자 클릭)의 몫이다.

실행: python tools/archive_scan.py
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "ccut_backend", "ccut_app.db")


def _dir_stat(path):
    n, sz = 0, 0
    if os.path.isdir(path):
        for r, _, files in os.walk(path):
            for f in files:
                try:
                    sz += os.path.getsize(os.path.join(r, f))
                    n += 1
                except OSError:
                    pass
    return n, sz


def main():
    con = sqlite3.connect(f"file:{DB.replace(os.sep, '/')}?mode=ro", uri=True)
    print("=" * 60)
    print("CCUT 아카이브 무결성 스캔 (read-only)")
    print("=" * 60)

    # 1. 자산(Tier A) 정합 — 원본 무손실이 최우선 검증
    rows = list(con.execute("SELECT source_id, file_path FROM sources"))
    missing = [(sid, p) for sid, p in rows if not (p and os.path.exists(p))]
    print(f"\n[Tier A] 원본 정합: {len(rows) - len(missing)}/{len(rows)} 실존")
    for sid, p in missing:
        print(f"  !! 유실: {sid} -> {p}")

    # 2. 죽은 참조 (기록 계층)
    checks = [
        ("person_faces→fragment_index 끊김",
         """SELECT COUNT(*) FROM person_faces pf LEFT JOIN fragment_index fi
            ON fi.fragment_id = pf.fragment_id WHERE fi.fragment_id IS NULL"""),
        ("export_results→proposals 죽은 참조",
         """SELECT COUNT(*) FROM export_results er LEFT JOIN proposals p
            ON p.proposal_id = er.proposal_id WHERE p.proposal_id IS NULL"""),
        ("fragment_index 잔재(semantic 없음)",
         """SELECT COUNT(*) FROM fragment_index fi LEFT JOIN semantic_fragments sf
            ON sf.fragment_id = fi.fragment_id WHERE sf.fragment_id IS NULL"""),
        ("proposals 레거시(program_id NULL)",
         "SELECT COUNT(*) FROM proposals WHERE program_id IS NULL"),
    ]
    print("\n[기록] 죽은 참조:")
    for label, q in checks:
        print(f"  {label}: {con.execute(q).fetchone()[0]}")

    # 3. 캐시/잔여물(Tier C/D) — 파일만 있고 DB엔 없는 고아
    live = {r[0] for r in con.execute("SELECT fragment_id FROM semantic_fragments")}
    live |= {r[0] for r in con.execute("SELECT fragment_id FROM fragments")}
    tdir = os.path.join(ROOT, "storage", "thumbnails")
    orphan_thumb, orphan_sz = 0, 0
    if os.path.isdir(tdir):
        for f in os.listdir(tdir):
            if f.startswith(("SF_", "VF")) and f.rsplit(".", 1)[0] not in live:
                orphan_thumb += 1
                try:
                    orphan_sz += os.path.getsize(os.path.join(tdir, f))
                except OSError:
                    pass
    print(f"\n[Tier D] 고아 썸네일: {orphan_thumb:,}개 ({orphan_sz/1024/1024:.0f} MB)")

    exp_urls = {os.path.basename((r[0] or "").split("?")[0]) for r in con.execute(
        "SELECT output_url FROM export_results")}
    edir = os.path.join(ROOT, "ccut_backend", "storage", "exports")
    orphan_exp = [f for f in (os.listdir(edir) if os.path.isdir(edir) else [])
                  if os.path.isfile(os.path.join(edir, f)) and f not in exp_urls]
    print(f"[Tier D] 고아 export 파일: {len(orphan_exp)}개")

    # 4. 용량 분포 (사용자에게 보여줄 수치의 원천)
    print("\n[용량] Tier별 분포:")
    for label, path in [("원본(A)", "storage/uploads"),
                        ("완성본(A)", "ccut_backend/storage/exports"),
                        ("캐시-썸네일(C)", "storage/thumbnails"),
                        ("캐시-프록시(C)", "storage/proxies"),
                        ("캐시-프리뷰(C)", "storage/proposal_previews"),
                        ("이중분(D)", "ccut_backend/storage/uploads")]:
        n, sz = _dir_stat(os.path.join(ROOT, path))
        print(f"  {label:16s} {n:>7,} files  {sz/1024/1024:>10,.0f} MB")

    con.close()
    print("\n(스캔 완료 — 아무것도 수정하지 않았습니다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
