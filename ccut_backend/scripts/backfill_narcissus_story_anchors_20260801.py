"""[BACKFILL 2026-08-01] Narcissus 원고 5건에 좌표(fidAnchors)를 소급 병기 (국장 승인).

무엇을 고치는가:
  proj_94f8dc2d7699(Narcissus)의 ui_state.story.fids 5건이 현행 semantic_fragments 에
  없어 조각맵이 비고, 저장할 때마다 STORY-WRITE-GUARD 가 거부한다.
  fid 가 죽은 이유는 '남의 원고'가 아니라 **자기 소스(SRC_0094A13D)의 분절 경계가 바뀌어서**다
  (2026-08-01 12:45 재조각화. fid 는 sha1(source_id|start_ds|end_ds)[:6] 결정론이라
   경계가 바뀌면 해시 입력이 달라진다).

왜 좌표만 넣는가:
  bd78b0d4(STORY-ANCHOR)에서 읽기 경로에 '좌표 재매칭'을 깔았다.
  story.fidAnchors 만 있으면 화면이 열릴 때 rematchAnchor 로 현 세대 조각을 찾아 잇는다.
  ★ story.fids 는 건드리지 않는다. 재연결은 **읽을 때** 일어난다 — 스크립트가 fid 를
    새 것으로 갈아치우면 그 판단을 DB 에 굳혀 버리고, 나중에 세대가 또 바뀌면 같은 문제가 반복된다.

좌표는 어디서 오는가 — ★ 현재 DB 가 아니라 **백업 스냅샷**이다:
  금고는 행을 지우지 않지만(vault_id 결번 0), _upsert 는 자연키(anchor_hash,start_ds,end_ds)가
  같고 fid 만 다르면 **그 행의 fragment_id 를 신세대 값으로 UPDATE 한다**(fragment_vault.py:107-109).
  2026-08-01 밤 VAULT-HOOK 검증으로 SRC_0094A13D 를 재분석했을 때 '병합 7' 이 그것이고,
  그 결과 대상 5건 중 EEC860_P001·EEC860_P002 **2건의 옛 fid 가 현재 DB 에서 조회되지 않는다**.
  (좌표 행 자체는 살아 있지만 그 행이 이제 다른 fid 를 달고 있어 fid 로는 못 찾는다.)
  실측: 현재 3/5 · 21:54 백업 5/5 · 17:12 백업 5/5 · 11:58 백업 5/5.
  그래서 좌표는 재분석 이전 스냅샷에서 읽는다. 백업은 읽기 전용으로만 연다.
  ※ 이 사실 자체가 기록 대상이다 — 검증을 위해 돌린 재분석이 증거의 일부를 덮었다.

검증된 근거(실측):
  5건 전부 vault 좌표 보유. tol 3000ms 재매칭 결과 5/5 성공, **전부 후보 1개**.
  드리프트 0 / 260 / 640 / 1930 / 0 ms (최대 1930ms < tol 3000ms).

절벽:
  ① fid 를 새 것으로 바꾸지 않는다. 좌표만 추가한다.
  ② 대상은 program_id 와 fid 5건을 **명시 지정**한다. WHERE 조건절로 훑지 않는다 —
     나중에 비슷한 프로그램이 생기면 함께 물든다.
  ③ 백업 없이 실행하지 않는다(sqlite backup API. cp 는 WAL 때문에 불완전).
  ④ 낡은 vault 데이터 무접촉. 읽기만 한다.
  ⑤ 전후 대조 없이 완료라고 하지 않는다.

사용:
  python scripts/backfill_narcissus_story_anchors_20260801.py            (dry-run)
  python scripts/backfill_narcissus_story_anchors_20260801.py --apply
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

PROGRAM_ID = "proj_94f8dc2d7699"          # Narcissus — 이 하나만
SOURCE_ID = "SRC_0094A13D"
# 옛 세대 좌표의 출처. 밤 재분석(22:41) 이전 스냅샷이라 5건이 모두 원래 fid 로 남아 있다.
VAULT_SNAPSHOT = "ccut_app.db.PRE_STORY_ANCHOR_TEST_20260801_215430.bak"
# 절벽 ② — 5건을 이름으로 못박는다. 기대 좌표(ms)도 함께 적어 vault 값과 대조한다.
TARGETS = {
    "SF_EEC860_SRC_0094A13D_P001": (0, 15000),
    "SF_3E0E21_SRC_0094A13D_P001": (140000, 159000),
    "SF_DA2B88_SRC_0094A13D_P002": (471440, 485000),
    "SF_FCEBD7_SRC_0094A13D_P002": (1448000, 1465090),
    "SF_EEC860_SRC_0094A13D_P002": (15000, 29000),
}
TOL_MS = 3000                              # bd78b0d4 와 같은 값. 임의 조정 금지.


def load_ui(con):
    row = con.execute("SELECT ui_state FROM programs WHERE program_id=?", (PROGRAM_ID,)).fetchone()
    if not row or not row[0]:
        return None, None
    raw = row[0]
    d = json.loads(raw)
    if isinstance(d, str):                 # 이중 인코딩 방어
        d = json.loads(d)
    return raw, d


def vault_coords(_unused=None):
    """옛 세대 좌표를 **백업 스냅샷**에서 읽는다(read-only). 같은 fid 가 여러 행이면
    가장 이른 first_seen 을 쓴다 — 원고가 가리키던 세대가 옛 것이기 때문이다."""
    path = os.path.join(BACKEND_DIR, VAULT_SNAPSHOT)
    if not os.path.exists(path):
        raise SystemExit(f"[STOP] 좌표 스냅샷이 없다: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out = {}
    for fid, s, e, seen in con.execute(
        "SELECT fragment_id, start, end, first_seen FROM fragment_vault "
        "WHERE source_id=? ORDER BY first_seen", (SOURCE_ID,)
    ):
        if fid in TARGETS and fid not in out:
            out[fid] = (int(round(s * 1000)), int(round(e * 1000)), seen)
    con.close()
    return out


def current_fragments(con):
    return [(fid, int(round(s * 1000)), int(round(e * 1000)))
            for fid, s, e in con.execute(
                "SELECT fragment_id, start, end FROM semantic_fragments "
                "WHERE source_id=? ORDER BY start", (SOURCE_ID,))]


def backup(db_path):
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = f"{db_path}.PRE_NARCISSUS_ANCHOR_{stamp}.bak"
    src = sqlite3.connect(db_path)
    out = sqlite3.connect(dst)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    chk = sqlite3.connect(dst)
    ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
    n = chk.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    chk.close()
    return dst, ok, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")

    raw_before, ui = load_ui(con)
    if ui is None:
        print("[STOP] ui_state 를 읽지 못했다."); return 1
    story = ui.get("story") or {}
    fids = story.get("fids") or []
    print("=== 전 상태")
    print(f"  program_id      {PROGRAM_ID}")
    print(f"  story.fids      {len(fids)}건  {fids}")
    print(f"  fidAnchors      {'있음 ' + str(len(story.get('fidAnchors') or {})) + '건' if story.get('fidAnchors') else '없음'}")
    print(f"  ui_state 길이    {len(raw_before)}")

    if set(fids) != set(TARGETS):
        print(f"[STOP] 저장된 fids 가 명시 대상 5건과 다르다. 중단한다.\n  DB={sorted(fids)}\n  대상={sorted(TARGETS)}")
        return 1
    if story.get("fidAnchors"):
        print("[STOP] 이미 fidAnchors 가 있다. 덮어쓰지 않는다."); return 1

    vc = vault_coords()
    missing = [f for f in TARGETS if f not in vc]
    if missing:
        print(f"[STOP] vault 좌표가 없는 fid: {missing}"); return 1

    cur = current_fragments(con)
    print(f"\n=== 좌표 대조 (백업 vault vs 기대값) · 현행 조각 {len(cur)}개 · tol {TOL_MS}ms")
    anchors = {}
    for fid, (exp_s, exp_e) in TARGETS.items():
        s, e, seen = vc[fid]
        agree = (s, e) == (exp_s, exp_e)
        hits = [(f2, max(abs(cs - s), abs(ce - e))) for f2, cs, ce in cur
                if abs(cs - s) <= TOL_MS and abs(ce - e) <= TOL_MS]
        best = min(hits, key=lambda x: x[1]) if hits else None
        print(f"  {fid}")
        print(f"     vault {s}~{e}ms (first_seen {str(seen)[:19]})  기대값 일치={agree}")
        print(f"     재매칭 후보 {len(hits)}개" + (f" · 최적 {best[0]} 드리프트 {best[1]}ms" if best else " · 없음"))
        if not agree:
            print("[STOP] vault 좌표가 승인된 기대값과 다르다. 중단한다."); return 1
        if len(hits) != 1:
            print(f"[STOP] 후보가 {len(hits)}개다(1개여야 한다). 중단한다."); return 1
        anchors[fid] = {"source_id": SOURCE_ID, "anchor_start_ms": s, "anchor_end_ms": e}

    if not args.apply:
        print("\n[DRY-RUN] 쓰지 않았다. 실제 적용은 --apply.")
        con.close(); return 0

    dst, ok, nprog = backup(DB_PATH)
    print(f"\n[BACKUP] {dst}  integrity={ok}  programs={nprog}")
    if ok != "ok":
        print("[STOP] 백업 무결성 실패."); con.close(); return 1

    # 절벽 ① — fids 는 그대로. fidAnchors 만 더한다.
    ui["story"] = {**story, "fidAnchors": anchors}
    payload = json.dumps(ui, ensure_ascii=False)
    with con:
        con.execute("UPDATE programs SET ui_state=? WHERE program_id=?", (payload, PROGRAM_ID))

    raw_after, ui2 = load_ui(con)
    st2 = ui2.get("story") or {}
    print("\n=== 후 상태")
    print(f"  story.fids      {len(st2.get('fids') or [])}건  변경={st2.get('fids') != fids}")
    print(f"  fidAnchors      {len(st2.get('fidAnchors') or {})}건")
    for f, a in (st2.get("fidAnchors") or {}).items():
        print(f"     {f}  {a['anchor_start_ms']}~{a['anchor_end_ms']}ms  {a['source_id']}")

    # 회귀: 다른 프로그램·다른 키 무변경
    other = con.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    b4 = json.loads(raw_before) if not isinstance(json.loads(raw_before), str) else json.loads(json.loads(raw_before))
    changed_keys = [k for k in set(list(b4.keys()) + list(ui2.keys()))
                    if k != "story" and json.dumps(b4.get(k), sort_keys=True, ensure_ascii=False)
                    != json.dumps(ui2.get(k), sort_keys=True, ensure_ascii=False)]
    print("\n=== 회귀 확인")
    print(f"  programs 행 수         {nprog} -> {other}")
    print(f"  story 외 키 변경        {changed_keys if changed_keys else '없음'}")
    print(f"  story.fids 변경         {st2.get('fids') != fids}")
    con.close()
    return 0 if (st2.get("fids") == fids and not changed_keys) else 1


if __name__ == "__main__":
    sys.exit(main())
