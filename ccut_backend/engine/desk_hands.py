"""[HANDS-1 2026-08-08] 젬마의 손 — 고른 것을 실제로 한다.

국장 지시: "젬마의 선택이 실제 실행이 되고, 실행의 결과가 젬마에게 사실로
돌아오고, 젬마가 그것을 국장에게 말한다."

여기까지가 끊겨 있었다. main.py 에 [DESK][HOLD] 라는 자리가 있었고,
젬마가 도구를 고르면 CCUT 은 "그렇게 해드릴게요"라고 말만 하고 아무 일도
하지 않았다. 국장 눈에는 말만 하고 딴짓하는 것으로 보였다.

원칙:
  · 실행은 Edit State(fragment_edit_state) 위에서만 — 비파괴. 원본 불변.
  · 한 일은 반드시 Receipt 로 남긴다(project_timeline, append-only).
    남기지 않으면 "뺐나?" 에 답할 수 없다 — 그게 되돌아오는 숨이다.
  · 손은 사실만 만든다. 말은 젬마가 한다(engine_desk.say_done).
"""
import json
import re
import time

FACT_KIND = "hand_done"


def _fid_by_label(fragment_labels):
    """{fid: 'A60'} → {'A60': fid}. 젬마는 라벨로 말한다."""
    out = {}
    for fid, lab in (fragment_labels or {}).items():
        if lab:
            out[str(lab).strip().upper()] = fid
    return out


def _fragment_spans(fids):
    """조각들의 원래 (source_id, start_ms, end_ms) — anchor 로 쓴다."""
    from engine.edit_propose import _connect
    from edit_contract.time_units import to_ms
    if not fids:
        return {}
    con = _connect()
    try:
        marks = ",".join("?" * len(fids))
        rows = con.execute(
            f'SELECT fragment_id, source_id, start, "end" FROM semantic_fragments '
            f"WHERE fragment_id IN ({marks})", list(fids)).fetchall()
    finally:
        con.close()
    return {r["fragment_id"]: (r["source_id"],
                               to_ms(float(r["start"] or 0)),
                               to_ms(float(r["end"] or 0))) for r in rows}


def _live_fids(program_id):
    """지금 원고에 실제로 남아 있는 조각 — 빠진 것은 뺀 채로 센다.

    ★'17조각 → 14조각'의 근거가 여기다. 승인 원고(fragment_ids)에서
      removed 표시된 것을 걸러야 실제 수가 나온다.
    """
    from engine.edit_propose import _approved_fids
    from edit_contract import service as _edit
    import ledger_r0
    fids = _approved_fids(program_id)
    if not fids:
        return [], set()
    h6 = ledger_r0._hash6(program_id)
    removed = set()
    try:
        for s in _edit.list_edit_states(program_id):
            if s.get("removed"):
                removed.add(s["timeline_item_id"])
    except Exception:
        pass
    live = [f for f in fids if f"ITEM_{h6}_{f}_0" not in removed]
    return live, removed


def _mark(program_id, fids, removed):
    """조각들을 원고에서 빼거나(removed=True) 되살린다(False)."""
    from engine.edit_propose import _apply_state
    spans = _fragment_spans(fids)
    done = []
    for fid in fids:
        sp = spans.get(fid)
        if not sp:
            continue
        source_id, s_ms, e_ms = sp
        try:
            _apply_state(program_id, fid, source_id, (s_ms, e_ms), (s_ms, e_ms),
                         "REMOVE" if removed else "RESTORE",
                         before_state={"excluded_ranges": [], "removed": removed})
            done.append(fid)
        except Exception as e:
            print(f"[HANDS][WARN] {fid} 실패: {e}")
    return done


def _receipt(program_id, what, fids, before, after, said, op="remove",
             subject=""):
    """한 일을 원장에 남긴다 — 이게 없으면 '뺐나?'에 답할 수 없다.

    op 는 사람이 읽는 말이 아니라 ★표식★이다("remove"/"restore").
    말로 가려내면 말이 바뀔 때 같이 깨진다(실측: 되살린 것을 또 되살렸다).
    """
    from engine import timeline_store as _ts
    try:
        _ts.append_entries(program_id, [{
            "kind": FACT_KIND,
            "client_id": f"hand_{int(time.time() * 1000)}",
            "ts": time.time() * 1000,
            "payload": {"what": what, "op": op, "subject": subject,
                        "fragment_ids": fids,
                        "before_count": before, "after_count": after,
                        "said": (said or "")[:160]},
        }])
    except Exception as e:
        print(f"[HANDS][WARN] Receipt 실패: {e}")


def recent_receipts(program_id, limit=5):
    """방금 무엇을 했는지 — 되돌아오는 숨."""
    from engine import timeline_store as _ts
    try:
        rows = _ts.fetch(program_id, limit=200) or []
    except Exception:
        return []
    out = []
    for r in rows:
        if r.get("kind") != FACT_KIND:
            continue
        p = r.get("payload") or {}
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                continue
        out.append({"ts": r.get("ts"), **p})
    return out[-limit:][::-1]


def _scene_fids(scenes, scene_no):
    for g in scenes or []:
        if int(g.get("group_no") or 0) == int(scene_no):
            return list(g.get("fragment_ids") or [])
    return []


_THEME_HUSK = ("장면", "부분", "조각", "구간", "나오는", "나온", "있는", "하는",
               "찍은", "들어간", "관련", "쪽", "것", "거")


def _theme_key(theme):
    """'먹는 장면' → '먹'. 사람은 껍데기를 붙여 말하고 데이터엔 알맹이만 있다."""
    t = str(theme or "").strip()
    for h in _THEME_HUSK:
        t = t.replace(h, " ")
    words = [w for w in t.split() if len(w) >= 1]
    keys = []
    for w in words:
        # 한국어 활용 어미를 떼어 어간만 남긴다 ('먹는'→'먹', '요리하는'→'요리')
        k = re.sub(r"(하는|해서|하고|한|해|는|은|을|를|이|가|의|도|만)$", "", w)
        # ★숫자·기호는 소재가 아니다. 실측: 젬마가 theme='4' 를 채워 보냈고
        #   '4' 가 대사에 우연히 든 조각만 남아 17→1조각이 됐다.
        #   소재는 뜻이 있는 글자여야 한다.
        if k and not re.fullmatch(r"[\d\W_]+", k):
            keys.append(k)
    return keys


def _theme_fids(program_id, theme, live):
    """소재가 보이는 조각들 — 화면 설명과 대사 양쪽을 본다.

    ★[실측 2026-08-08] 예전 이 함수는 semantic_fragments.visual_desc 를 읽었다.
      그런 컬럼은 없다. 매번 예외로 죽었고, 그래서 '먹는 장면 빼줘'가 조용히
      옛 경로로 새어 A/B 17개를 그대로 만들고 "엮었습니다"라고 말했다.
      진짜 자리: 화면=fragment_index.visual_desc · 대사=semantic_json.summary.
      문자열로 하나도 못 찾으면 뜻으로 찾는다(이미 계산된 embedding).
    """
    from engine.edit_propose import _connect
    keys = _theme_key(theme)
    if not keys or not live:
        return []
    con = _connect()
    try:
        marks = ",".join("?" * len(live))
        text = {f: "" for f in live}
        try:
            for r in con.execute(
                    f"SELECT fragment_id, visual_desc FROM fragment_index "
                    f"WHERE fragment_id IN ({marks})", list(live)):
                text[r["fragment_id"]] += " " + str(r["visual_desc"] or "")
        except Exception as e:
            print(f"[HANDS][WARN] 화면 설명 조회 실패: {e}")
        for r in con.execute(
                f"SELECT fragment_id, semantic_json FROM semantic_fragments "
                f"WHERE fragment_id IN ({marks})", list(live)):
            try:
                d = json.loads(r["semantic_json"] or "{}")
            except Exception:
                continue
            text[r["fragment_id"]] += " " + str(d.get("summary") or "")
    finally:
        con.close()
    hit = [f for f in live if any(k in text.get(f, "") for k in keys)]
    if hit:
        print(f"[HANDS][THEME] {keys} 글자로 {len(hit)}/{len(live)}조각")
        return hit
    return _theme_fids_by_meaning(program_id, theme, live)


def _theme_fids_by_meaning(program_id, theme, live, cut=0.42):
    """글자로 못 찾으면 뜻으로 — 이미 계산된 embedding 을 쓴다(새 계산 없음)."""
    from engine.edit_propose import _connect
    try:
        import numpy as np
        from engine import embedding_model as em
    except Exception as e:
        print(f"[HANDS][WARN] 뜻 검색 불가: {e}")
        return []
    con = _connect()
    try:
        marks = ",".join("?" * len(live))
        rows = con.execute(
            f"SELECT fragment_id, embedding FROM fragment_index "
            f"WHERE fragment_id IN ({marks})", list(live)).fetchall()
    except Exception as e:
        print(f"[HANDS][WARN] embedding 조회 실패: {e}")
        return []
    finally:
        con.close()
    q = em.encode_one(str(theme))
    scored = []
    for r in rows:
        try:
            v = np.frombuffer(r["embedding"], dtype="float32") \
                if isinstance(r["embedding"], (bytes, bytearray)) \
                else np.asarray(json.loads(r["embedding"]), dtype="float32")
            scored.append((r["fragment_id"], float(np.dot(q, v))))
        except Exception:
            continue
    hit = [f for f, s in scored if s >= cut]
    top = sorted(scored, key=lambda x: -x[1])[:3]
    print(f"[HANDS][THEME] 뜻으로 {len(hit)}/{len(live)}조각 "
          f"(최고 {[(f[-8:], round(s, 3)) for f, s in top]})")
    return hit


# ── 손이 할 수 있는 일 ────────────────────────────────────────────────
HANDS = {"remove_scene", "remove_fragment", "remove_ordinal", "set_count",
         "remove_theme", "keep_theme", "restore_fragment", "read_receipt"}
# 세상을 바꾸지 않는 손 — 묻는 말에도 그냥 해도 된다.
READ_ONLY = {"read_receipt"}


def do(cap, args, program_id, fragment_labels=None, scenes=None, said=""):
    """젬마가 고른 것을 실제로 한다. 사실(facts)을 돌려준다 — 말은 안 만든다.

    돌려주는 것:
      {"ok": True, "what": 사람이 읽는 한 일, "before": n, "after": n, ...}
      {"ok": False, "why": 왜 못 했는지}   ← 지어내지 않기 위해 이유를 준다
    """
    args = args or {}
    # 젬마가 장면을 조각 이름 자리에 넣는 일이 잦다 — 실측: '6번 장면 빼줘' →
    #   remove_fragment{fragment:'6번 장면'} → "'6번 장면'이 원고에서 안 보여요".
    #   가리키는 것이 장면이면 장면 손으로 넘긴다. 뜻은 분명한데 칸만 틀린 것을
    #   못 알아들은 척하지 않는다.
    if cap == "remove_fragment":
        _t = str(args.get("fragment") or "")
        _m = re.search(r"(\d+)\s*번", _t)
        if _m and ("장면" in _t or "씬" in _t):
            cap, args = "remove_scene", {"scene_no": int(_m.group(1))}
            print(f"[HANDS][SLOT-FIX] 조각이 아니라 장면이다 → remove_scene {_m.group(1)}번")
    live, _ = _live_fids(program_id)
    before = len(live)

    if cap == "read_receipt":
        rs = recent_receipts(program_id, 3)
        return {"ok": True, "what": "방금 한 일을 확인했어요", "before": before,
                "after": before, "receipts": rs, "nothing": not rs,
                "live": live}

    if not live:
        return {"ok": False, "why": "아직 원고가 없어요 — 먼저 이야기를 만들어야 해요"}

    targets, what, subject = [], "", ""
    if cap == "remove_scene":
        try:
            no = int(args.get("scene_no"))
        except (TypeError, ValueError):
            return {"ok": False, "why": "몇 번 장면인지 잘 못 알아들었어요"}
        n_max = len(scenes or [])
        if n_max and not (1 <= no <= n_max):
            return {"ok": False, "why": f"장면은 1번부터 {n_max}번까지 있어요"}
        targets = [f for f in _scene_fids(scenes, no) if f in live]
        what, subject = f"{no}번 장면을 뺐어요", f"{no}번 장면"
        if not targets:
            # ★장면은 촬영분 전체(135조각) 위에서 묶이고 원고는 그 중 고른 것이다.
            #   그래서 원고에 한 조각도 안 들어간 장면이 실제로 있다(실측 16장면 중 8).
            return {"ok": False, "why": f"{no}번 장면은 원고에 들어가 있지 않아요"}

    elif cap == "remove_fragment":
        lab = str(args.get("fragment") or "").strip().upper()
        fid = _fid_by_label(fragment_labels).get(lab)
        if not fid or fid not in live:
            return {"ok": False, "why": f"'{lab or '그것'}'이 원고에서 안 보여요"}
        targets, what, subject = [fid], f"{lab} 조각을 뺐어요", f"{lab} 조각"

    elif cap == "remove_ordinal":
        try:
            idx = int(args.get("index"))
        except (TypeError, ValueError):
            return {"ok": False, "why": "몇 번째인지 잘 못 알아들었어요"}
        pos = before - 1 if idx == -1 else idx - 1
        if not (0 <= pos < before):
            return {"ok": False, "why": f"지금 조각은 {before}개예요"}
        targets = [live[pos]]
        subject = f"{idx}번째 조각" if idx != -1 else "마지막 조각"
        what = f"{subject}을 뺐어요"

    elif cap == "set_count":
        try:
            want = int(args.get("count"))
        except (TypeError, ValueError):
            return {"ok": False, "why": "몇 개로 맞출지 잘 못 알아들었어요"}
        if want >= before:
            return {"ok": False,
                    "why": f"지금 {before}개예요 — 늘리는 건 아직 제가 손이 없어요"}
        if want < 1:
            return {"ok": False, "why": "하나는 남겨야 해요"}
        targets = live[want:]          # 뒤에서 덜어낸다
        what, subject = f"조각을 {want}개로 맞췄어요", "덜어낸 조각"

    elif cap == "keep_theme":
        # ★국장이 화면에서 두 번 시킨 말이 이것이다 — "먹는 장면만 남기고 다 빼줘".
        #   빼는 손만 있고 남기는 손이 없어서, 젬마가 뜻을 뒤집어 고르거나
        #   옛 경로로 새어 17조각 그대로인 A/B 를 만들고 "엮었습니다"라고 했다.
        theme = str(args.get("theme") or "").strip()
        keep = _theme_fids(program_id, theme, live)
        if not keep:
            return {"ok": False, "why": f"'{theme}'이 나오는 조각을 못 찾았어요"}
        targets = [f for f in live if f not in keep]
        if not targets:
            return {"ok": False,
                    "why": f"이미 다 '{theme}' 조각이에요 — 뺄 게 없어요"}
        what, subject = f"'{theme}'만 남겼어요", "빼 뒀던 조각"

    elif cap == "remove_theme":
        theme = str(args.get("theme") or "").strip()
        targets = _theme_fids(program_id, theme, live)
        if not targets:
            return {"ok": False, "why": f"'{theme}'이 나오는 조각을 못 찾았어요"}
        if len(targets) >= before:
            return {"ok": False,
                    "why": f"'{theme}'이 원고 전부예요 — 다 빼면 남는 게 없어요"}
        what = f"'{theme}'이 나오는 조각 {len(targets)}개를 뺐어요"
        subject = f"'{theme}' 조각"

    elif cap == "restore_fragment":
        rs = recent_receipts(program_id, 5)
        last = next((r for r in rs if r.get("fragment_ids")
                     and r.get("op", "remove") == "remove"), None)
        if not last:
            return {"ok": False, "why": "되돌릴 게 없어요 — 아직 뺀 게 없어요"}
        got = _mark(program_id, last["fragment_ids"], removed=False)
        live_after = _live_fids(program_id)[0]
        after = len(live_after)
        # 되살릴 때는 "되살렸다 — 6번 장면을 뺐어요" 처럼 겹치지 않게
        #   원래 대상만 떼어 쓴다(실측: 국장 화면에 그대로 겹쳐 나갔다).
        _tgt = last.get("subject") or "방금 뺀 것"
        what = f"{_tgt}을 다시 넣었어요"
        _receipt(program_id, what, got, before, after, said, op="restore",
                 subject=_tgt)
        print(f"[HANDS] {what}: {before}→{after}조각")
        return {"ok": True, "what": what, "before": before, "after": after,
                "n": len(got), "live": live_after}
    else:
        return {"ok": False, "why": "그건 아직 제가 손이 없어요"}

    got = _mark(program_id, targets, removed=True)
    if not got:
        return {"ok": False, "why": "빼려 했는데 저장이 안 됐어요"}
    live_after = _live_fids(program_id)[0]
    after = len(live_after)
    _receipt(program_id, what, got, before, after, said, subject=subject)
    print(f"[HANDS] {what}: {before}→{after}조각")
    # ★live 를 함께 돌려준다 — 이것이 없으면 DB 만 바뀌고 화면은
    #   그대로다(실측: 프론트는 answer_only 에서 원고를 다시 안 읽는다).
    #   그 상태가 정확히 "말만 하고 땡짓하는 것으로 보임"이다.
    return {"ok": True, "what": what, "before": before, "after": after,
            "n": len(got), "live": live_after}
