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
import os                       # [NIGHT-2] 밤중 렌더 차단 게이트(기본 OFF)
import re
import time

FACT_KIND = "hand_done"


def _fid_by_label(fragment_labels):
    """{'A60': fid} → {'A60': fid}(대문자 정규화). 젬마는 라벨로 말한다.

    ★[RENDER-1 2026-08-09 · 한 줄 수리] 여기는 원래 {fid: 라벨} 로 오는 줄 알고
      한 번 더 뒤집었다. 그런데 계기판의 진실은 정반대다 —
      main._project_fragment_labels 는 {'A1': 'SF_9901B8…'}(라벨→fid)를 내고,
      converse._clean_fragment_labels·edit_propose._display_texts·
      gemma_breath.world·intent_router 전부 그 방향으로 읽는다.
      여기만 뒤집혀서 .get('A3') 이 영원히 None 이었고, remove_fragment 의
      유일한 대상 지정 경로(라벨 지목)가 통째로 죽어 있었다.
    """
    out = {}
    for lab, fid in (fragment_labels or {}).items():
        if lab and fid:
            out[str(lab).strip().upper()] = str(fid)
    return out


def _resolve_label(spoken, label_map, said=""):
    """말한 것을 라벨로 — 지도를 넓히지, 검문을 세우지 않는다.

    ★[RENDER-1 실측] 위 한 줄을 고치자마자 다음 벽이 나왔다: 결이 'A60 빼줘'를
      remove_fragment{fragment:'60'} 로 채운다(글자를 떼고 숫자만 남긴다).
      라벨은 A60 인데 '60' 으로 오니 여전히 "'60'이 원고에서 안 보여요".
      결에게 제약을 걸지 않고(국장 지시) 읽는 쪽에서 이어 준다 —
      숫자만 왔고 그 숫자로 끝나는 라벨이 **딱 하나면** 그것이다.
      둘 이상이면(소스가 여러 개라 A60·B60 이 동시에 있으면) 잇지 않는다 —
      찍는 것이 아니라 아는 것만 잇는다.
    """
    t = re.sub(r"[^0-9A-Z]", "", str(spoken or "").upper())
    # [RENDER-1 되돌아옴 2026-08-09 · 라이브에서 세 번째 모양이 나왔다]
    #   여기 원래 `if not t: return None, t` 가 있었다. 그래서 결이 슬롯을
    #   **아예 비워 보내면** 사용자가 친 문장을 읽어보지도 못하고 끝났다.
    #   실측(재기동 직후 라이브, proj_sim_ghost16, 원고에 A61 이 살아 있는 상태):
    #     사용자 'A61 조각 빼줘' → 결 fragment='' → "'그것'이 원고에서 안 보여요"
    #   결이 흘리는 모양이 '숫자만'(A60→'60') · '끝을 흘림'(A51→'5') 에 이어
    #   '통째로 빈칸'까지 셋이다. 앞의 둘은 이었는데 셋째만 못 이을 이유가 없다.
    #   아래 said 블록이 이미 "원문 안 아는 라벨이 딱 하나일 때만" 이라는
    #   똑같이 좁은 조건을 갖고 있고, t 가 비면 `t in m` 이 항상 참이라
    #   그 조건이 그대로 적용된다 — 찍는 것이 아니라 아는 것만 잇는다.
    #   빈칸을 먼저 걸러내지 않고, 아래로 흘려보낸다.
    if t and t in label_map:
        return label_map[t], t
    # [RENDER-1 되돌아옴 2026-08-09 · 라이브 실측] ★사용자가 친 문장을 숫자 규칙보다
    #   **먼저** 읽는다. 순서가 바뀌면 엉뚱한 조각을 뺀다 — 실측한 사고 모양:
    #     사용자 'A51 조각 빼줘' → 결 fragment='5' (끝 글자를 흘렸다)
    #       → 숫자 규칙이 먼저 돌면 '5' 로 끝나는 라벨 A5 **하나**뿐이라
    #         자신 있게 A5 를 고른다. 사용자는 A5 를 말한 적이 없다.
    #         (이번엔 A5 가 원고 밖이라 '안 보여요'로 떨어져 살았을 뿐이다.)
    #   결이 흘리는 모양(같은 프롬프트·같은 모델, 2026-08-09 라이브):
    #     'A39 조각 빼줘'  → '39'  (정상 — A39·A60·A45 는 이래서 붙었다)
    #     'A51 조각 빼줘'  → '5'
    #     'A111 조각 빼줘' → '11'
    #   흘린 뒤의 '5'·'11' 로는 원리상 못 고른다. 그래서 사용자의 원문을 하나 더
    #   읽는다 — 결에게 검문을 세우는 게 아니라(국장 지시) 읽는 쪽 지도를 넓힌다.
    #   조건: 원문 안 라벨 토큰 중 지도에 있는 것이 **딱 하나**이고, 결이 남긴
    #   조각(t)이 그 토큰 안에 실제로 들어 있을 때만. 찍지 않는다.
    if said:
        seen = sorted({m for m in re.findall(r"[A-Z]+[0-9]+", str(said).upper())
                       if m in label_map})
        uniq = [m for m in seen if t in m]
        if len(uniq) == 1:
            _sp = f"'{spoken}' 로 흘렸지만" if t else "슬롯을 비웠지만"
            print(f"[HANDS][LABEL] 결은 {_sp} 사용자가 친 문장에 "
                  f"{uniq[0]} 이 있다 → 잇는다")
            return label_map[uniq[0]], uniq[0]
        if seen:
            # ★사용자가 라벨을 분명히 말했는데 어느 것인지 못 좁혔다.
            #   여기서 아래 숫자 규칙으로 내려가면 **사용자가 말한 적 없는 라벨**을
            #   고른다(실측: 'A51 이랑 A59 빼줘' + 결 '5' → 숫자 규칙이 A5 를 골랐다).
            #   모를 때는 안 잇는다 — 못 하는 것보다 나쁜 것은 엉뚱한 것을 하는 것이다.
            print(f"[HANDS][LABEL] 사용자 문장 안 라벨 {seen} · 결은 '{spoken}' "
                  f"— 어느 것인지 못 좁혀서 안 잇는다")
            return None, t
    if t.isdigit():
        cand = [k for k in label_map if re.fullmatch(r"[A-Z]+" + t, k)]
        if len(cand) == 1:
            print(f"[HANDS][LABEL] 숫자만 왔다 '{spoken}' → {cand[0]} (유일)")
            return label_map[cand[0]], cand[0]
        if len(cand) > 1:
            print(f"[HANDS][LABEL] '{spoken}' 후보 {cand} — 여럿이라 안 잇는다")
    return None, t


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

    ★'17조각 → 14조각'의 근거가 여기다. [HANDS-3] 원고(resolve_sequence)에서
      removed 표시된 것을 걸러야 실제 수가 나온다.
    """
    from edit_contract import service as _edit
    import ledger_r0
    # ★[HANDS-3 2026-08-10] 순서 진실원 단일화.
    #   구판(HANDS-2)은 승인 스냅샷(story_approval.fragment_ids)을 뼈대로 삼고
    #   "집합이 같을 때만" ui_state 순서를 채택했다. 집합이 갈라진 프로젝트
    #   (국장 실물이 그렇다 — approved 5 vs ui 3)에서는 손이 승인 배열을 세고
    #   EDL·화면은 ui_state 를 세서, 결이 센 N번째와 화면의 N번째가 달랐다.
    #   이제 세는 것도 EDL 도 같은 함수 하나(resolve_sequence)를 본다.
    #   승인 배열은 지문 비교(story_gate.service)에만 남는다.
    try:
        fids = _full_story_fids(program_id)          # [HANDS-3]
    except Exception as e:
        # 진실원이 아예 안 읽히면 지어내지 않는다 — 사실을 찍고 비운다.
        print(f"[HANDS][LIVE] 원고를 못 읽었다(resolve_sequence 실패): {e}")
        return [], set()
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


def _state_snapshot(program_id, fids):
    """[HANDS-2] 빼기 직전의 excluded_ranges 를 떠 둔다.

    계약(edit_contract.edit_state.normalize:45-48)은 removed=True 인 상태에
    excluded_ranges 를 두지 않는다 — `removed_input_clears_excluded`.
    그래서 조각을 빼는 순간 사용자가 파 둔 구멍은 **계약상** 사라진다(trim 과
    달리 이건 버그가 아니라 규칙이다). 계약을 바꾸지 않고 되살릴 수 있게,
    빼기 직전 값을 Receipt 에 적어 두고 되살릴 때 그대로 되돌려 넣는다.
    """
    from edit_contract import service as _edit
    import ledger_r0
    want = {f"ITEM_{ledger_r0._hash6(program_id)}_{f}_0": f for f in fids}
    out = {}
    try:
        for s in _edit.list_edit_states(program_id):
            f = want.get(s["timeline_item_id"])
            if f and (s.get("excluded_ranges") or []):
                out[f] = [[int(a), int(b)] for a, b in s["excluded_ranges"]]
    except Exception as e:
        print(f"[HANDS][WARN] 구멍 스냅샷 실패: {e}")
    return out


def _mark(program_id, fids, removed, excluded_by_fid=None):
    """조각들을 원고에서 빼거나(removed=True) 되살린다(False).

    excluded_by_fid: [HANDS-2] 되살릴 때만 쓴다 — 뺄 때 계약이 지운 구멍을
    Receipt 에 적힌 값으로 되돌려 넣는다.
    """
    from engine.edit_propose import _apply_state
    spans = _fragment_spans(fids)
    done = []
    for fid in fids:
        sp = spans.get(fid)
        if not sp:
            continue
        source_id, s_ms, e_ms = sp
        try:
            # [HANDS-2 2026-08-09] 빼고 넣는 손은 removed 한 칸만 만진다.
            #   전에는 trim 자리에 anchor 를 넣고 excluded_ranges=[] 를 함께
            #   보내서, 조각을 뺐다 되살리는 것만으로 사용자가 걸어 둔
            #   trim·excluded 가 통째로 사라졌다(실측 raw: 634000/648000 →
            #   632000/650000, [[640000,642000]] → []). trim=None 은
            #   _apply_state 에서 "현재 값 유지"다.
            _apply_state(program_id, fid, source_id, (s_ms, e_ms), None,
                         "REMOVE" if removed else "RESTORE",
                         before_state={"removed": removed},
                         # [HANDS-2] 되살릴 때만 구멍을 되돌려 넣는다. None 은
                         #   "현재 값 유지"라, 뺄 때는 계약이 알아서 비운다.
                         excluded_ranges=(None if removed else
                                          (excluded_by_fid or {}).get(fid)))
            done.append(fid)
        except Exception as e:
            print(f"[HANDS][WARN] {fid} 실패: {e}")
    return done


def _receipt(program_id, what, fids, before, after, said, op="remove",
             subject="", extra=None):    # [HANDS-2] extra: 되돌리기용 전 값
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
                        "said": (said or "")[:160],
                        # [HANDS-2] 되돌리는 데 필요한 것만 더 싣는다
                        #   (뺄 때 계약이 지운 구멍 · 순서를 바꾸기 전 배열).
                        **(extra or {})},
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
        kind = r.get("kind")
        # [HANDS-2 되돌아옴] 내보내기도 "방금 한 일"이다. 전에는 hand_done 만 봐서,
        #   내보낸 직후 "방금 뭐 했지?"에 그 앞의 되살리기를 답했다(검증 실측).
        #   원장에 이미 있는 것을 안 읽던 것뿐이라 새 kind 를 만들지 않는다.
        if kind not in (FACT_KIND, EXPORT_DONE_KIND):
            continue
        p = r.get("payload") or {}
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                continue
        if kind == EXPORT_DONE_KIND:
            _d = p.get("duration_sec") or 0
            _fc = p.get("fragment_count")
            # [HANDS-2] before_count/after_count 는 say_done 이 반드시 읽는다 —
            #   빠뜨리면 KeyError 로 답 자체가 죽는다(이 손을 넓히다 실제로 밟았다).
            #   내보내기는 조각 수를 바꾸지 않으므로 둘 다 같은 값이다.
            p = {"what": (f"영상으로 내보냈어요 — 조각 {_fc}개"
                          + (f", 길이 {_d:.1f}초" if _d else "")),
                 "op": "export", "said": p.get("said") or "",
                 "before_count": _fc, "after_count": _fc}
        out.append({"ts": r.get("ts"), **p})
    return out[-limit:][::-1]


def _scene_fids(scenes, scene_no):
    for g in scenes or []:
        if int(g.get("group_no") or 0) == int(scene_no):
            return list(g.get("fragment_ids") or [])
    return []


# ── 순서 바꾸기 ────────────────────────────────────────────────────────
#   [HANDS-2 2026-08-09] "마지막 조각을 맨 앞으로 옮겨줘" — 결은 이걸 이미
#   정확히 알아듣고 reorder_story{from_index,to_index} 까지 뽑는데, 손이 없어
#   main.py:6009 [DESK][HOLD] 로 떨어졌다. 결은 "옮겨드릴게요"라고 답하고
#   아무 일도 일어나지 않았다(3/3). 실패한 것조차 국장이 몰랐다.
_KO_ORDINAL = {"한": 1, "하나": 1, "첫": 1, "처음": 1, "두": 2, "둘": 2,
               "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6,
               "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
_FRONT_RE = re.compile(r"(맨|제일|가장)?\s*(앞|처음|첫)")
_BACK_RE = re.compile(r"(맨|제일|가장)?\s*(뒤|끝|마지막)")


def _spoken_pos(text, n):
    """사용자가 말한 자리 하나를 0-기점 위치로. 못 읽으면 None.

    ★결의 index 는 밑수가 흔들린다 — 같은 문장에 5조각 원고인데 마지막을
      from_index=4(0-기점)로도, 5(1-기점)로도 준다. 어느 쪽이라 정할 수 없다.
      그래서 검문을 세우는 대신(국장 지시) **사용자가 친 문장을 먼저 읽는다** —
      _resolve_label 이 라벨에서 한 것과 같은 방식이다.
    """
    t = str(text or "")
    m = re.search(r"(\d+)\s*번째", t)
    if m:
        k = int(m.group(1))
        return k - 1 if 1 <= k <= n else None
    m = re.search(r"(" + "|".join(_KO_ORDINAL) + r")\s*번째", t)
    if m:
        k = _KO_ORDINAL[m.group(1)]
        return k - 1 if 1 <= k <= n else None
    if _BACK_RE.search(t):
        return n - 1
    if _FRONT_RE.search(t):
        return 0
    return None


def _resolve_move(args, said, n):
    """(src, dst) 0-기점. 못 읽으면 (None, None, 왜).

    읽는 순서: ①사용자 원문(옮길 것 / 갈 자리를 나눠 읽는다)
              ②결이 준 from_index·to_index (밑수는 범위로 짐작한다)
    """
    t = str(said or "")
    src = dst = None
    # ① 원문 — '…을/를 …으로' 로 갈라 앞은 옮길 것, 뒤는 갈 자리.
    m = re.search(r"(.*?[을를])\s*(.*)", t)
    if m:
        src = _spoken_pos(m.group(1), n)
        dst = _spoken_pos(m.group(2), n)
    if src is None and dst is None:
        # 조사가 없어도 '앞으로/뒤로' 같은 방향말은 갈 자리다.
        m2 = re.search(r"(앞|처음|첫|뒤|끝|마지막)\s*(으로|로)", t)
        if m2:
            dst = 0 if m2.group(1) in ("앞", "처음", "첫") else n - 1
    # ② 결의 슬롯 — 지도를 넓혀 밑수를 짐작한다(막지 않는다).
    def _idx(v):
        try:
            k = int(v)
        except (TypeError, ValueError):
            return None
        if k < 0:
            return n + k if -n <= k else None          # -1 = 마지막
        if k == 0:
            return 0                                    # 0-기점으로 말했다
        if k <= n:
            return k - 1                                # 1-기점(needs 가 그렇게 적혀 있다)
        if k == n + 1:
            return n - 1                                # 개수+1 = "맨 뒤"로 읽는다
        return None
    if src is None:
        src = _idx(args.get("from_index"))
    if dst is None:
        dst = _idx(args.get("to_index"))
    if src is None and dst is None:
        return None, None, "어느 조각을 어디로 옮길지 못 알아들었어요"
    if src is None:
        return None, None, "어느 조각을 옮길지 못 알아들었어요"
    if dst is None:
        return None, None, "어디로 옮길지 못 알아들었어요"
    if not (0 <= src < n and 0 <= dst < n):
        return None, None, f"지금 조각은 {n}개예요"
    return src, dst, ""


def _full_story_fids(program_id):
    """원고에 적힌 조각 전부(뺀 것 포함) — 순서를 쓸 때 이 배열을 통째로 쓴다."""
    from story_gate.service import resolve_sequence as _seq
    from engine.edit_propose import _connect as _c
    con = _c()
    try:
        return list(_seq(con, program_id)[1] or [])
    finally:
        con.close()


def _write_order(program_id, order):
    """순서를 쓰는 자리는 하나 — ledger_r0.save_ledger_order.

    ★HTTP 자기호출을 하지 않는다(교착 위험). 이 함수는 라우트 핸들러이면서
      동시에 순수 async(str, dict)라 그냥 부르면 된다. 다만 우리는 이미
      이벤트 루프 안일 수도 있어서, 제 루프를 가진 별도 스레드에서 돌린다.
    """
    import asyncio
    import concurrent.futures
    import ledger_r0
    payload = {"order": list(order), "selected": list(order)}

    def _run():
        return asyncio.run(ledger_r0.save_ledger_order(program_id, payload))
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(_run).result(timeout=30)


def _place_back(cur, missing, ref):
    """[HANDS-3] 되끼울 자리를 정한다 — 승인 원고(ref)에서의 상대 위치.

    ref 에서 그 조각 **앞**에 있던 것 중 지금 원고에 남아 있는 마지막 것 바로 뒤.
    앞쪽에 아무도 없으면 **뒤** 이웃 바로 앞. 둘 다 없으면 맨 뒤.
    ref 에 없는 fid 는 맨 뒤 — 지어낼 근거가 없으니 순서를 꾸미지 않는다.
    """
    new = list(cur)
    for f in missing:
        if f in new:
            continue
        pos = len(new)
        if f in ref:
            i = ref.index(f)
            anchor = next((g for g in reversed(ref[:i]) if g in new), None)
            if anchor is not None:
                pos = new.index(anchor) + 1
            else:
                nxt = next((g for g in ref[i + 1:] if g in new), None)
                pos = new.index(nxt) if nxt is not None else len(new)
        new.insert(pos, f)
    return new


def _reinsert_into_story(program_id, fids, ref=None):
    """[HANDS-3] '되살려줘'의 뜻은 **원고에 다시 넣는 것**이다.

    구판은 edit_state.removed=False 만 되돌렸다. 그런데 그 fid 가
    ui_state.story.fids 에 없으면 원고에도 EDL 에도 안 나타난다 — 되살렸다고
    말해 놓고 화면은 그대로다(실측: Marigold removed 16건 중 11건이 ui 밖).
    여기서 ui_state.story.fids 에 되끼운다. 못 끼우면 조용히 넘어가지 않는다.

    ref: 자리를 정할 때 볼 순서. 뺄 때 Receipt 에 적어 둔 **그때의 원고**가
    1순위다 — 사용자가 보던 자리가 그 자리니까. 없으면(옛 Receipt) 승인 원고.

    돌려주는 것: {"added": [...], "failed": [...], "error": str|None}
    """
    try:
        cur = _full_story_fids(program_id)
    except Exception as e:
        return {"added": [], "failed": list(fids), "error": f"원고를 못 읽었어요 ({e})"}
    missing = [f for f in fids if f not in cur]
    if not missing:
        return {"added": [], "failed": [], "error": None}
    ref = [str(f) for f in (ref or []) if f]
    if not ref:
        try:
            from engine.edit_propose import _approved_fids
            ref = list(_approved_fids(program_id) or [])
        except Exception:
            ref = []
    res = _write_order(program_id, _place_back(cur, missing, ref))
    try:
        after = _full_story_fids(program_id)
    except Exception:
        after = []
    added = [f for f in missing if f in after]
    failed = [f for f in missing if f not in after]
    _nm = lambda f: f"{f[3:9]}…{f.rsplit('_', 1)[-1]}"   # 뒤 6자만 찍으면 P001 뿐이라 못 가린다
    if failed:
        print(f"[HANDS][RESTORE] 원고에 못 되끼운 조각 {[_nm(f) for f in failed]} "
              f"— save_ledger_order={(res or {}).get('error')}")
    else:
        print(f"[HANDS][RESTORE] 원고에 되끼웠다 {[_nm(f) for f in added]} "
              f"({len(cur)}→{len(after)}조각)")
    return {"added": added, "failed": failed,
            "error": (res or {}).get("error") if failed else None}


def _take_out(program_id, targets, what, subject, said, before, extra=None):
    """조각들을 실제로 빼고 Receipt 를 남긴다 — ★빼는 자리는 하나다.★

    [FIX-CORRECT 2026-08-11] do() 꼬리에 인라인으로 있던 것을 함수로 꺼냈다.
    정정(_do_correct_last)이 '대신 이걸 빼기'를 하려면 같은 일이 필요한데,
    복사하면 구멍 스냅샷(_state_snapshot)이나 order_before 를 한쪽만 고치는 날이
    온다 — 이 저장소가 fid 저장처 13곳으로 이미 겪은 부채다.
    """
    # [HANDS-2 2026-08-09] 빼기 **전에** 구멍을 떠 둔다 — 계약이
    #   removed=True 에서 excluded_ranges 를 비우는 것은 규칙이라(edit_state
    #   normalize:45-48) 뺀 뒤에는 읽을 수 없다.
    _holes = _state_snapshot(program_id, targets)
    # [HANDS-3] 뺄 때의 원고 순서를 적어 둔다 — 되살릴 때 **그 자리로** 되끼운다.
    try:
        _order_before = _full_story_fids(program_id)
    except Exception:
        _order_before = []
    got = _mark(program_id, targets, removed=True)
    if not got:
        return {"ok": False, "why": "빼려 했는데 저장이 안 됐어요"}
    live_after = _live_fids(program_id)[0]
    after = len(live_after)
    _receipt(program_id, what, got, before, after, said, subject=subject,
             extra={**({"excluded_by_fid": _holes} if _holes else {}),
                    **({"order_before": _order_before} if _order_before else {}),
                    **(extra or {})})
    print(f"[HANDS] {what}: {before}→{after}조각")
    # ★live 를 함께 돌려준다 — 이것이 없으면 DB 만 바뀌고 화면은 그대로다.
    return {"ok": True, "what": what, "before": before, "after": after,
            "n": len(got), "live": live_after}


def _undo_remove(program_id, last, said, before):
    """뺀 것을 되살린다 — restore_fragment 의 알맹이. [FIX-CORRECT] 정정도 이걸 쓴다.

    [HANDS-3] 되살리기 = 원고에 다시 넣기. removed 를 푸는 것만으로는
    ui_state.story.fids 밖에 있는 조각이 안 돌아온다.
    """
    _ins = _reinsert_into_story(program_id, last["fragment_ids"],
                                ref=last.get("order_before"))   # [HANDS-3]
    if _ins["failed"] and not _ins["added"]:
        return {"ok": False,
                "why": f"그 조각을 원고에 되끼우지 못했어요 "
                       f"({_ins.get('error') or '원고 저장 거절'}) — "
                       f"그래서 되살리지 못했어요"}
    # [HANDS-2] 뺄 때 계약이 지운 구멍(excluded_ranges)을 Receipt 에서 되돌려 넣는다.
    got = _mark(program_id,
                [f for f in last["fragment_ids"] if f not in _ins["failed"]],
                removed=False,
                excluded_by_fid=last.get("excluded_by_fid") or {})
    live_after = _live_fids(program_id)[0]
    after = len(live_after)
    # 되살릴 때는 "되살렸다 — 6번 장면을 뺐어요" 처럼 겹치지 않게
    #   원래 대상만 떼어 쓴다(실측: 국장 화면에 그대로 겹쳐 나갔다).
    _tgt = last.get("subject") or "방금 뺀 것"
    what = f"{_tgt}을 다시 넣었어요"
    _receipt(program_id, what, got, before, after, said, op="restore",
             # [HANDS-2] 어느 Receipt 를 소비했는지 적어 둔다 — 두 번째
             #   되돌리기가 같은 것을 또 집지 않게.
             subject=_tgt, extra={"undid_ts": last.get("ts")})
    print(f"[HANDS] {what}: {before}→{after}조각")
    return {"ok": True, "what": what, "before": before, "after": after,
            "n": len(got), "live": live_after}


def _render_needs_approval(program_id):
    """순서를 바꾸면 승인 지문이 어긋난다 — 사실대로 말하기 위해 확인한다.

    story_gate.service:216-244 is_render_allowed / :273 approve(actor!="user" 403).
    자동 재승인은 하지 않는다. 거짓 완주 대신 사실을 말한다(국장 지시).
    """
    try:
        from story_gate import service as _sg
        # [HANDS-2 되돌아옴] 게이트가 꺼져 있으면 승인은 애초에 필요 없다.
        #   전에는 이 확인이 없어서, 게이트 OFF 인데도 "승인이 한 번 필요해요"라고
        #   말할 수 있었다 — 아무도 요구하지 않는 절차를 사용자에게 시키는 거짓말.
        from story_gate import gate as _sgg
        if not _sgg.is_enabled():
            return False
        return str(_sg.story_state(program_id).get("story_state")) != "story_approved"
    except Exception as e:
        print(f"[HANDS][WARN] 승인 상태 못 읽음: {e}")
        return False


def _reach_render_gate(program_id, said):
    """[HANDS-2 되돌아옴] ★승인 관문에 실제로 닿는다.

    검증이 잡은 결함: story_gate.is_render_allowed 의 호출처가 채팅 내보내기
    경로에 **0건**이었다(main.py:1998·3162·3617 의 HTTP 렌더 라우트뿐).
    그래서 CCUT 은 "내보내기 전에 승인이 한 번 필요해요"라고 말한 직후
    승인 없이 mp4 를 끝까지 만들었다 — CLAUDE.md 가 경계하는
    "등록·정의는 있는데 호출처가 0건" 그 모양이다.

    여기서 관문을 부르고, 막혀 있으면 **사용자가 방금 한 말**을 승인으로 적는다.
    기계가 스스로 도장을 찍는 게 아니다 — 이 함수는 propose_export 가 조각 수·
    클립 수·길이를 보여 주고 사용자가 "그렇게 해줘"라고 답했을 때만 도달한다.
    그래서 actor="user" 가 사실이다(I-5). 그리고 찍었다는 사실을 완료 문구로
    말한다(아래 반환값 note) — 조용한 변경 금지.

    돌려주는 것: (ok, note, why)
    """
    try:
        from story_gate import service as _sg
        from story_gate import gate as _sgg
    except Exception as e:
        print(f"[HANDS][EXPORT][GATE][WARN] 관문 모듈을 못 읽음: {e}")
        return True, None, None
    if not _sgg.is_enabled():
        print("[HANDS][EXPORT][GATE] 게이트 OFF — 승인 확인 없이 진행")
        return True, None, None
    try:
        if _sg.is_render_allowed(program_id):
            print("[HANDS][EXPORT][GATE] 승인 유효 — 그대로 진행")
            return True, None, None
        st = _sg.story_state(program_id)
        _sg.approve(program_id, st.get("sequence_hash"), actor="user",
                    note=f"채팅 내보내기 확인: {(said or '')[:80]}")
        print(f"[HANDS][EXPORT][GATE] ★관문 도달 — {st.get('story_state')} "
              f"상태였다. 사용자 확인을 승인으로 적었다 "
              f"hash={st.get('sequence_hash')}")
        return True, "바뀐 원고는 방금 확인해 주신 걸로 승인 처리했어요", None
    except Exception as e:
        # 관문이 막았는데 도장도 못 찍었다 — 여기서 렌더하면 그게 거짓 완주다.
        print(f"[HANDS][EXPORT][GATE] ★관문이 막았다: {e}")
        return False, None, f"원고 승인이 아직 안 잡혀서 내보낼 수 없어요 — {e}"


def _grow_count(program_id, want, before, said, live):
    """[HANDS-2 되돌아옴] 조각 수를 늘린다 = 빼 뒀던 것을 되넣는다.

    검증이 잡은 자리: set_count 는 줄이기만 됐고 "다시 5조각으로 되돌려줘"가
    'ok=False 늘리는 건 아직 제가 손이 없어요'로 막혔다. 되살릴 재료는
    이미 Receipt 에 다 있다(fragment_ids · excluded_by_fid) — 없는 걸
    만드는 게 아니라 안 읽던 걸 읽는다. restore_fragment 와 같은 통로를 쓴다.
    """
    rs = recent_receipts(program_id, 20)
    used = {r.get("undid_ts") for r in rs if r.get("undid_ts")}
    need = want - before
    picked, holes, consumed = [], {}, []
    order_ref = []                     # [HANDS-3] 되끼울 자리의 근거
    for r in rs:                      # recent_receipts 는 최신이 앞
        if len(picked) >= need:
            break
        if r.get("op", "remove") != "remove" or r.get("ts") in used:
            continue
        fids = [f for f in (r.get("fragment_ids") or []) if f not in picked]
        if not fids:
            continue
        take = fids[:need - len(picked)]
        picked += take
        consumed.append(r.get("ts"))
        if not order_ref:              # [HANDS-3] 가장 최근에 뺀 그때의 원고
            order_ref = list(r.get("order_before") or [])
        for f in take:
            h = (r.get("excluded_by_fid") or {}).get(f)
            if h:
                holes[f] = h
    if not picked:
        return {"ok": False,
                "why": f"지금 {before}개인데 빼 둔 조각이 없어서 더 못 늘려요"}
    # [HANDS-3] removed 만 풀면 원고 밖 조각은 안 돌아온다 — 원고에 되끼운다.
    _ins = _reinsert_into_story(program_id, picked, ref=order_ref)
    if _ins["failed"] and not _ins["added"]:
        return {"ok": False,
                "why": f"빼 뒀던 조각 {len(_ins['failed'])}개를 원고에 되끼우지 "
                       f"못했어요 ({_ins.get('error') or '원고 저장 거절'}) — "
                       f"그래서 수를 못 늘렸어요"}
    picked = [f for f in picked if f not in _ins["failed"]]
    got = _mark(program_id, picked, removed=False, excluded_by_fid=holes)
    live_after = _live_fids(program_id)[0]
    after = len(live_after)
    if after < want:
        # 지어내지 않는다 — 원한 만큼 못 채웠으면 채운 만큼만 말한다.
        what = f"빼 뒀던 조각을 다 되넣어 {after}개가 됐어요 ({want}개까지는 재료가 없었어요)"
    else:
        # [HANDS-2] "조각을 5개로 맞췄어요"라고만 하면 결이 '이미 5개였다'로 읽고
        #   "이미 맞춰줬어요, 계속 유지할게요"라고 답했다(실측) — 4개를 되넣었는데
        #   아무 일도 안 한 것처럼 들린다. 한 일을 동사로 준다.
        what = f"빼 뒀던 조각 {len(got)}개를 다시 넣어 {want}개로 맞췄어요"
    _receipt(program_id, what, got, before, after, said, op="restore",
             subject="빼 뒀던 조각",
             extra={"undid_ts": consumed[0] if len(consumed) == 1 else None})
    print(f"[HANDS] {what}: {before}→{after}조각 (되넣은 fid "
          f"{[f[-6:] for f in got]})")
    return {"ok": True, "what": what, "before": before, "after": after,
            "n": len(got), "live": live_after}


def _do_reorder(program_id, args, said, live):
    """조각 하나를 원고 안에서 다른 자리로 옮긴다. 조각 수는 안 변한다."""
    n = len(live)
    if n < 2:
        return {"ok": False,
                "why": f"지금 조각이 {n}개뿐이라 바꿀 순서가 없어요"}
    src, dst, why = _resolve_move(args, said, n)
    if src is None:
        return {"ok": False, "why": why}
    if src == dst:
        return {"ok": False, "why": "그 조각은 이미 그 자리에 있어요"}
    moved = live[src]
    new_live = list(live)
    new_live.insert(dst, new_live.pop(src))

    # 원고 전체 배열에서 '살아 있는 자리'만 새 순서로 갈아 끼운다.
    #   뺀 조각은 제자리에 그대로 둔다 — 원고(story.fids)는 '무엇이 적혀 있나'
    #   이고 뺐다는 사실은 edit_state 에 있다. [HANDS-3] 여기서 뺀 것을 지우면
    #   되살리기가 되끼울 자리를 잃는다.
    full = _full_story_fids(program_id)
    if not full or set(live) - set(full):
        return {"ok": False, "why": "원고를 못 읽었어요 — 순서를 못 바꿨어요"}
    it = iter(new_live)
    new_full = [next(it) if f in set(live) else f for f in full]

    order_before = list(full)
    res = _write_order(program_id, new_full)
    if not (res or {}).get("ok"):
        return {"ok": False,
                "why": f"순서 저장이 안 됐어요 ({(res or {}).get('error')})"}
    live_after = _live_fids(program_id)[0]
    if live_after != new_live:
        print(f"[HANDS][REORDER] 쓴 순서와 읽은 순서가 다르다 "
              f"want={[f[-6:] for f in new_live]} got={[f[-6:] for f in live_after]}")

    where = ("맨 앞으로" if dst == 0 else
             "맨 뒤로" if dst == n - 1 else f"{dst + 1}번째로")
    subject = ("마지막 조각" if src == n - 1 else
               "첫 조각" if src == 0 else f"{src + 1}번째 조각")
    what = f"{subject}을 {where} 옮겼어요"
    if _render_needs_approval(program_id):
        # 지어내지 않는다 — 순서가 바뀌면 승인 지문이 어긋나 렌더가 막힌다.
        what += " — 순서가 바뀌어서 내보내기 전에 승인이 한 번 필요해요"
    _receipt(program_id, what, [moved], n, n, said, op="reorder",
             subject=subject,
             extra={"order_before": order_before, "order_after": new_full})
    print(f"[HANDS] {what}: {[f[-6:] for f in live]} → "
          f"{[f[-6:] for f in live_after]}")
    return {"ok": True, "what": what, "before": n, "after": n, "n": 1,
            "op": "reorder", "live": live_after,
            # [HANDS-2] 자리 숫자는 say_done 의 사실 문장에 그대로 들어간다
            #   (NUM-GUARD 는 사실 문장에 있는 숫자만 통과시킨다).
            "from_pos": src + 1, "to_pos": dst + 1,
            "order_before": [f[-6:] for f in live],
            "order_after": [f[-6:] for f in live_after]}


def _undo_reorder(program_id, last, said, before):
    """[HANDS-2] 순서를 되돌린다 — Receipt 에 적어 둔 order_before 를 그대로 쓴다."""
    order = list(last.get("order_before") or [])
    if not order:
        return {"ok": False, "why": "되돌릴 순서를 못 찾았어요"}
    res = _write_order(program_id, order)
    if not (res or {}).get("ok"):
        return {"ok": False,
                "why": f"순서 저장이 안 됐어요 ({(res or {}).get('error')})"}
    live_after = _live_fids(program_id)[0]
    what = f"{last.get('subject') or '옮긴 조각'}을 원래 자리로 되돌렸어요"
    if _render_needs_approval(program_id):
        what += " — 내보내기 전에 승인이 한 번 필요해요"
    _receipt(program_id, what, list(last.get("fragment_ids") or []),
             before, len(live_after), said, op="reorder_undo",
             subject=last.get("subject") or "",
             extra={"undid_ts": last.get("ts")})      # [HANDS-2]
    print(f"[HANDS] {what}: {[f[-6:] for f in live_after]}")
    return {"ok": True, "what": what, "before": before,
            "after": len(live_after), "n": 1, "op": "reorder",
            "live": live_after, "order_after": [f[-6:] for f in live_after]}


# ── 좌표를 건드리는 손 — 다듬기(trim) · 구간 빼기(exclude) ─────────────
#   [HANDS-2 2026-08-09] 착수 시점 지형: CAPABILITIES 에는 있고 HANDS 에는 없어
#   전부 main.py [DESK][HOLD] 로 떨어졌다. 게다가 역전된 우회로가 있었다 —
#   조각을 ★지목하면★ HOLD, 지목 ★안 하면★ 서버가 알아서 자리를 골라 TRIM.
#   여기서 지목한 쪽을 손이 받는다. 지목도 분량도 없는 말은 그대로 초안 회로
#   (edit_propose.draft_gate)로 간다 — 그건 별개 기능이라 죽이지 않는다.

# 사람이 말하는 분량. 모호어는 여기 없다 — 모호함의 답은 발명이 아니라 실측이다.
_KO_NUM = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4,
           "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
_MINSEC_RE = re.compile(r"(\d+)\s*분(?:\s*(\d+(?:\.\d+)?)\s*초)?")
_SEC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*초")
_KOSEC_RE = re.compile(r"(" + "|".join(_KO_NUM) + r")\s*초")
_PCT_RE = re.compile(r"(\d+)\s*(?:%|퍼센트)")
_HALF_RE = re.compile(r"절반|반절|(?<![가-힣])반(?![가-힣])")
_VAGUE_RE = re.compile(r"조금|살짝|약간|좀|적당|다듬|대충")
# '분량을 말했는가' 하나로 묻는 자리(can_reach·_route_by_words)가 여럿이라 모아 둔다.
_AMT_ANY_RE = re.compile(r"\d+\s*(?:분|초|%|퍼센트)|"
                         + "|".join(_KO_NUM) + r"\s*초|절반|반절")
# 조각 ★안쪽★을 가리키는 말 — 이게 있으면 '조각을 통째로 빼 달라'가 아니다.
_INNER_RE = re.compile(r"가운데|중간|중반|한가운데|앞부분|뒷부분|뒤부분|앞쪽|뒤쪽|"
                       r"초반|후반|일부|구간|사이")
# 경계(앞·뒤)가 아니라 ★조각 한가운데★를 가리키는 말만. _INNER_RE 보다 좁다 —
#   '뒤쪽'은 조각 안쪽 지칭이기도 하고 꼬리 경계이기도 해서 여기 넣지 않는다.
_MID_ONLY_RE = re.compile(r"가운데|한가운데|중간|중반|사이|일부|구간")
_MIN_KEEP_MS = 1000     # edit_propose.MIN_KEEP_MS 와 같은 값(다듬은 뒤 남을 하한)


def _fmt_sec(ms):
    """ms → '2초' / '1분 30초'. 사실 문장에 들어갈 숫자는 전부 여기서 난다."""
    ms = int(round(ms))
    s = ms / 1000.0
    if s >= 60:
        m, r = int(s // 60), s - int(s // 60) * 60
        if r < 0.05:
            return f"{m}분"
        return f"{m}분 {r:.1f}초".replace(".0초", "초")
    return f"{s:.1f}초".replace(".0초", "초")


def _parse_amount(spoken, said, span_ms):
    """말한 분량 → (ms, kind). kind: explicit / ratio / vague / none.

    ★지어내지 않는다. 모호어('조금','살짝')는 숫자를 만들지 않고 vague 로 낸다 —
      그 답은 말공백 실측(edit_propose.find_candidates)이 준다.
    읽는 순서는 _resolve_label 과 같다: ①사용자 원문 ②결이 준 슬롯.
      (결은 슬롯을 통째로 흘리기도 하고, 원문에 없는 말을 넣기도 한다.)
    """
    for src, who in ((said, "원문"), (spoken, "결")):
        t = str(src or "")
        if not t:
            continue
        m = _MINSEC_RE.search(t)
        if m:
            ms = int(m.group(1)) * 60000 + (int(float(m.group(2)) * 1000)
                                            if m.group(2) else 0)
            print(f"[HANDS][AMOUNT] {who} '{m.group(0)}' → {ms}ms")
            return ms, "explicit"
        m = _SEC_RE.search(t)
        if m:
            ms = int(round(float(m.group(1)) * 1000))
            print(f"[HANDS][AMOUNT] {who} '{m.group(0)}' → {ms}ms")
            return ms, "explicit"
        m = _KOSEC_RE.search(t)
        if m:
            ms = _KO_NUM[m.group(1)] * 1000
            print(f"[HANDS][AMOUNT] {who} '{m.group(0)}' → {ms}ms")
            return ms, "explicit"
        m = _PCT_RE.search(t)
        if m and span_ms:
            ms = span_ms * int(m.group(1)) // 100
            print(f"[HANDS][AMOUNT] {who} '{m.group(0)}' → {ms}ms (조각 {span_ms}ms 의 비율)")
            return ms, "ratio"
        if _HALF_RE.search(t) and span_ms:
            print(f"[HANDS][AMOUNT] {who} '절반' → {span_ms // 2}ms")
            return span_ms // 2, "ratio"
    for src in (said, spoken):
        if _VAGUE_RE.search(str(src or "")):
            return None, "vague"
    return None, "none"


def _target_pos(text, n):
    """말 안에서 '몇 번째 조각'을 짚는다 → 0-기점. 없으면 None.

    _spoken_pos 와 다르다 — 저건 '맨 뒤로' 같은 ★갈 자리★도 읽는다. 여기서
    그걸 읽으면 '뒤 2초 잘라줘'가 마지막 조각을 가리키게 된다(자리가 아니라
    조각 안쪽 방향인데). 그래서 조각을 짚는 말만 좁게 읽는다.
    """
    t = str(text or "")
    m = re.search(r"(\d+)\s*번째", t) or re.search(r"(\d+)\s*번\s*(?:조각|거|것)", t)
    if m:
        k = int(m.group(1))
        return k - 1 if 1 <= k <= n else None
    m = re.search(r"(" + "|".join(_KO_ORDINAL) + r")\s*번째", t)
    if m:
        k = _KO_ORDINAL[m.group(1)]
        return k - 1 if 1 <= k <= n else None
    if re.search(r"마지막\s*(?:조각|거|것|번째)?", t) and not re.search(r"마지막\s*으?로", t):
        return n - 1
    if re.search(r"(?:맨\s*)?(?:첫|처음)\s*(?:조각|번째|거|것)", t):
        return 0
    return None


def _labels_in(said, fragment_labels):
    lm = _fid_by_label(fragment_labels)
    return [m for m in re.findall(r"[A-Z]+[0-9]+", str(said or "").upper()) if m in lm]


def _resolve_target(args, said, live, fragment_labels):
    """어느 조각인가 → (fid, 사람이 읽는 이름, 못 짚은 이유).

    읽는 순서: ①사용자 원문의 라벨 ②사용자 원문의 순번 ③결이 준 슬롯.
    라벨을 순번보다 먼저 읽는 이유: 'A51 조각 앞 2초' 의 51 을 순번으로 읽으면
    엉뚱한 조각을 짚는다.

    ★[HANDS-3 2026-08-10] 세 번째 값이 새로 생겼다. 구판은 "알아봤지만 원고
      밖"과 "아예 못 알아들음"을 한 조건(len(labs)==1 and ... in live)에 묶어
      (None,"") 하나만 돌려줬고, 부르는 쪽은 둘 다 "어느 조각을 다듬을지 못
      들었어요"라고 말했다 — 라벨을 정확히 부른 사용자에게 못 알아들었다고
      하는 거짓말이다. remove_fragment(:1588-1593)는 이미 제대로 구별한다.
      돌려주는 이유: None(못 알아들음) | "원고 밖: <라벨>"
    """
    n = len(live)
    lm = _fid_by_label(fragment_labels)
    labs = _labels_in(said, fragment_labels)
    if len(labs) == 1:
        if lm[labs[0]] in live:
            return lm[labs[0]], f"{labs[0]} 조각", None
        # 라벨은 알아봤다 — 다만 지금 원고 안에 없다. 순번으로 넘어가지 않는다
        # (사용자는 조각을 이름으로 지목했다).
        return None, "", f"'{labs[0]}'이 원고에서 안 보여요"
    pos = _target_pos(said, n)
    if pos is not None:
        nm = ("마지막 조각" if pos == n - 1 and re.search(r"마지막", str(said or ""))
              else f"{pos + 1}번째 조각")
        return live[pos], nm, None
    spoken = str(args.get("fragment") or "").strip()
    if spoken:
        fid, lab = _resolve_label(spoken, lm, said)
        if fid and fid in live:
            return fid, f"{lab} 조각", None
        pos = _target_pos(spoken, n)
        if pos is not None:
            return live[pos], f"{pos + 1}번째 조각", None
        if fid:
            return None, "", f"'{lab or spoken}'이 원고에서 안 보여요"
    return None, "", None


def _cur_state(program_id, fid, anchor):
    """그 조각의 지금 편집 상태 — 없으면 anchor 그대로."""
    from edit_contract import service as _edit
    import ledger_r0
    item_id = f"ITEM_{ledger_r0._hash6(program_id)}_{fid}_0"
    try:
        for s in _edit.list_edit_states(program_id):
            if s["timeline_item_id"] == item_id:
                return {"trim_start_ms": int(s["trim_start_ms"]),
                        "trim_end_ms": int(s["trim_end_ms"]),
                        "excluded_ranges": [[int(a), int(b)]
                                            for a, b in (s.get("excluded_ranges") or [])],
                        "removed": bool(s.get("removed"))}
    except Exception as e:
        print(f"[HANDS][WARN] 편집 상태 못 읽음: {e}")
    return {"trim_start_ms": anchor[0], "trim_end_ms": anchor[1],
            "excluded_ranges": [], "removed": False}


def _kept_ms(cur):
    """실제로 남아 있는 길이 — 구멍을 뺀 값."""
    span = cur["trim_end_ms"] - cur["trim_start_ms"]
    return span - sum(b - a for a, b in cur["excluded_ranges"])


def _trim_side(said, args):
    """앞을 더는가 뒤를 더는가. 못 읽으면 None — 지어내지 않는다."""
    t = str(said or "")
    # 대상 지칭('마지막 조각','첫 조각')은 자리 이름이 아니다 — 떼고 읽는다.
    t = re.sub(r"(마지막|첫|처음)\s*(?:조각|거|것|번째)", " ", t)
    t = re.sub(r"\d+\s*번째", " ", t)
    a = re.search(r"앞|처음|시작|초반", t)
    b = re.search(r"뒤|끝|후반|말미", t)
    if a and b:
        return "start" if a.start() < b.start() else "end"
    if a:
        return "start"
    if b:
        return "end"
    s = str(args.get("side") or "").strip().lower()
    if s in ("start", "앞", "front", "begin", "head"):
        return "start"
    if s in ("end", "뒤", "back", "tail", "finish"):
        return "end"
    return None


def _gap_trim(program_id, fid, side):
    """말공백에서 잰 다듬기 후보 — 모호어('조금')의 답은 여기서 난다.

    새로 재지 않는다. edit_propose.find_candidates(99-198)를 그대로 쓴다
    (MIN_GAP_MS 500 · PAD_MS 120 · MIN_DELTA_MS 300 · MIN_KEEP_MS 1000).
    """
    from engine import edit_propose as _ep
    try:
        cands = [c for c in _ep.find_candidates(program_id)
                 if c["fragment_id"] == fid and (side is None or c["side"] == side)]
    except Exception as e:
        print(f"[HANDS][WARN] 말공백 후보 실패: {e}")
        return None
    if not cands:
        return None
    cands.sort(key=lambda c: -c["gap_ms"])
    return cands[0]


def _inner_gaps(source_id, s_ms, e_ms):
    """조각 ★안쪽★의 말 없는 구간들 [[s,e], ...] — 단어 경계는 PAD 로 비켜난다.

    '가운데'는 기하학이 아니라 말공백이다. PAD_MS 가 있는 이유가 단어 중간
    절단 방지라(edit_propose.py:37), 한가운데를 그냥 자르면 사용자가 되돌린다.
    """
    from engine.edit_propose import _connect, _words_by_source, MIN_GAP_MS, PAD_MS
    from edit_contract.time_units import to_ms
    con = _connect()
    try:
        words = _words_by_source(con, source_id, {})
    finally:
        con.close()
    ws = sorted((to_ms(a), to_ms(b)) for a, b in words
                if to_ms(b) > s_ms and to_ms(a) < e_ms)
    gaps, prev = [], None
    for a, b in ws:
        if prev is not None and a - prev >= MIN_GAP_MS:
            g0, g1 = max(prev + PAD_MS, s_ms), min(a - PAD_MS, e_ms)
            if g1 - g0 >= 200:
                gaps.append([g0, g1])
        prev = b if prev is None else max(prev, b)
    return gaps


def _overlaps(rng, ranges):
    return [r for r in ranges if rng[0] < r[1] and r[0] < rng[1]]


def _edit_receipt(program_id, what, fid, cur, said, op, subject, extra=None):
    """좌표 손의 Receipt — 되돌리는 데 필요한 '전 값'을 함께 싣는다."""
    _receipt(program_id, what, [fid], 0, 0, said, op=op, subject=subject,
             extra={"trim_before": [cur["trim_start_ms"], cur["trim_end_ms"]],
                    "excl_before": [list(r) for r in cur["excluded_ranges"]],
                    **(extra or {})})


def _do_trim(program_id, args, said, live, fragment_labels):
    """조각의 앞이나 뒤를 말한 만큼 덜어낸다."""
    from engine.edit_propose import _apply_state
    fid, name, miss = _resolve_target(args, said, live, fragment_labels)   # [HANDS-3]
    if not fid:
        return {"ok": False,
                "why": (f"{miss} — 지금 원고는 {len(live)}조각이에요"
                        if miss else
                        "어느 조각을 다듬을지 못 들었어요 — "
                        "'3번째 조각 앞 2초'처럼 짚어 주시면 그만큼 덜어낼게요")}
    sp = _fragment_spans([fid]).get(fid)
    if not sp:
        return {"ok": False, "why": "그 조각의 원본 자리를 못 찾았어요"}
    source_id, a_s, a_e = sp
    cur = _cur_state(program_id, fid, (a_s, a_e))
    cur_s, cur_e = cur["trim_start_ms"], cur["trim_end_ms"]
    span = cur_e - cur_s
    side = _trim_side(said, args)
    amt, kind = _parse_amount(args.get("amount"), said, span)

    measured = ""
    if kind in ("explicit", "ratio"):
        if side is None:
            return {"ok": False,
                    "why": f"{name} 앞을 덜지 뒤를 덜지 못 들었어요 — "
                           f"'앞 {_fmt_sec(amt)}'처럼 말해 주시면 그만큼 덜어낼게요"}
        if amt < 100:
            return {"ok": False, "why": "그건 너무 짧아서 티도 안 나요"}
        if span - amt < _MIN_KEEP_MS:
            # 조용한 clamp 금지 — 실제 숫자로 거절한다.
            return {"ok": False,
                    "why": f"{name}은 {_fmt_sec(span)}라 {_fmt_sec(amt)}를 "
                           f"덜면 남는 게 없어요"}
        new_s = cur_s + amt if side == "start" else cur_s
        new_e = cur_e if side == "start" else cur_e - amt
    else:
        # 모호어거나 아무 말 없음 → 지어내지 않고 말공백을 잰다.
        c = _gap_trim(program_id, fid, side)
        if not c:
            _w = "앞" if side == "start" else "뒤" if side == "end" else "양쪽"
            return {"ok": False,
                    "why": f"{name} {_w}쪽엔 덜어낼 만한 말 없는 구간이 없어요 — "
                           f"'앞 2초'처럼 분량을 말해 주시면 그만큼 덜어낼게요"}
        side = c["side"]
        new_s = c["proposed"]["trim_start_ms"]
        new_e = c["proposed"]["trim_end_ms"]
        amt = c["delta_ms"]
        measured = " (말 없는 구간을 재서)"

    where = "앞" if side == "start" else "뒤"
    # 구멍이 잘려 나가는 창 밖으로 밀리면 계약이 조용히 버린다 — 미리 말한다.
    lost = [r for r in cur["excluded_ranges"] if r[1] <= new_s or r[0] >= new_e]
    try:
        _apply_state(program_id, fid, source_id, (a_s, a_e), (new_s, new_e), "TRIM")
    except Exception as e:
        return {"ok": False, "why": f"저장이 안 됐어요 ({e})"}
    after = _cur_state(program_id, fid, (a_s, a_e))
    len_b, len_a = _kept_ms(cur), _kept_ms(after)
    what = (f"{name} {where}쪽을 {_fmt_sec(amt)} 덜어냈어요{measured} — "
            f"{_fmt_sec(len_b)}에서 {_fmt_sec(len_a)}가 됐어요")
    if lost:
        what += f" (거기 있던 구멍 {len(lost)}개는 잘려 나갔어요)"
    _edit_receipt(program_id, what, fid, cur, said, "trim", name)
    print(f"[HANDS] {what}: trim {cur_s}/{cur_e} → "
          f"{after['trim_start_ms']}/{after['trim_end_ms']}")
    n_live = len(live)
    return {"ok": True, "what": what, "before": n_live, "after": n_live, "n": 1,
            "op": "trim", "live": live, "fragment_id": fid,
            "trim_before": [cur_s, cur_e],
            "trim_after": [after["trim_start_ms"], after["trim_end_ms"]],
            "amount_ms": amt, "side": side,
            "len_before_ms": len_b, "len_after_ms": len_a,
            "len_before_text": _fmt_sec(len_b), "len_after_text": _fmt_sec(len_a)}


def _do_exclude(program_id, args, said, live, fragment_labels):
    """조각 안의 한 구간만 뺀다 — 조각은 남고 가운데가 뚫린다."""
    from engine.edit_propose import _apply_state
    fid, name, miss = _resolve_target(args, said, live, fragment_labels)   # [HANDS-3]
    if not fid:
        return {"ok": False,
                "why": (f"{miss} — 지금 원고는 {len(live)}조각이에요"
                        if miss else
                        "어느 조각 가운데를 뺄지 못 들었어요 — "
                        "'3번째 조각 가운데 2초'처럼 짚어 주시면 그만큼 뺄게요")}
    sp = _fragment_spans([fid]).get(fid)
    if not sp:
        return {"ok": False, "why": "그 조각의 원본 자리를 못 찾았어요"}
    source_id, a_s, a_e = sp
    cur = _cur_state(program_id, fid, (a_s, a_e))
    cur_s, cur_e = cur["trim_start_ms"], cur["trim_end_ms"]
    span = cur_e - cur_s
    amt, kind = _parse_amount(args.get("amount"), said, span)
    hint = str(args.get("where") or "") + " " + str(said or "")
    if re.search(r"앞쪽|앞부분|초반", hint):
        aim = cur_s
    elif re.search(r"뒤쪽|뒷부분|뒤부분|후반", hint):
        aim = cur_e
    else:
        aim = (cur_s + cur_e) // 2       # '가운데' 가 기본

    gaps = _inner_gaps(source_id, cur_s, cur_e)
    said_geo = ""
    if gaps:
        g = min(gaps, key=lambda g: abs((g[0] + g[1]) // 2 - aim))
        if kind in ("explicit", "ratio"):
            hole = [g[0], g[0] + amt]
        else:
            hole = list(g)               # 분량을 안 말했으면 그 공백 전체
    else:
        if kind not in ("explicit", "ratio"):
            return {"ok": False,
                    "why": f"{name} 안에 말 없는 데가 없어요 — "
                           f"'가운데 2초'처럼 분량을 말해 주시면 그만큼 뺄게요"}
        hole = [aim - amt // 2, aim - amt // 2 + amt]
        # 조용한 대체 금지 — 기하학으로 떨어졌으면 그렇다고 말한다.
        said_geo = " (말 없는 데가 없어서 한가운데를 뺐어요)"

    hole = [max(hole[0], cur_s), min(hole[1], cur_e)]
    if hole[1] - hole[0] < 100:
        return {"ok": False,
                "why": f"{name} 안에서 뺄 자리가 안 나와요 — 조각이 {_fmt_sec(span)}뿐이에요"}
    dup = _overlaps(hole, cur["excluded_ranges"])
    if dup:
        # 계약(normalize)은 겹치면 조용히 합쳐 버린다. 합쳐진 걸 '2초 뺐다'고
        #   말하면 거짓이 된다 — 겹치면 지어내지 말고 사실대로 말한다.
        d = dup[0]
        return {"ok": False,
                "why": f"{name}의 그 자리는 이미 빼 뒀어요 "
                       f"({_fmt_sec(d[0] - cur_s)}~{_fmt_sec(d[1] - cur_s)} 지점)"}
    merged = sorted([list(r) for r in cur["excluded_ranges"]] + [hole])
    keep_after = span - sum(b - a for a, b in merged)
    if keep_after < _MIN_KEEP_MS:
        return {"ok": False,
                "why": f"{name}은 {_fmt_sec(span)}라 {_fmt_sec(hole[1] - hole[0])}를 "
                       f"더 빼면 남는 게 없어요"}
    try:
        _apply_state(program_id, fid, source_id, (a_s, a_e), None, "EXCLUDE_RANGE",
                     excluded_ranges=merged)
    except Exception as e:
        return {"ok": False, "why": f"저장이 안 됐어요 ({e})"}
    after = _cur_state(program_id, fid, (a_s, a_e))
    len_b, len_a = _kept_ms(cur), _kept_ms(after)
    cut = hole[1] - hole[0]
    what = (f"{name} 가운데 {_fmt_sec(cut)}를 뺐어요{said_geo} — "
            f"{_fmt_sec(len_b)}에서 {_fmt_sec(len_a)}가 됐어요")
    _edit_receipt(program_id, what, fid, cur, said, "exclude", name)
    print(f"[HANDS] {what}: excl {cur['excluded_ranges']} → "
          f"{after['excluded_ranges']}")
    n_live = len(live)
    return {"ok": True, "what": what, "before": n_live, "after": n_live, "n": 1,
            "op": "exclude", "live": live, "fragment_id": fid,
            "hole": hole, "excl_before": cur["excluded_ranges"],
            "excl_after": after["excluded_ranges"], "amount_ms": cut,
            "len_before_ms": len_b, "len_after_ms": len_a,
            "len_before_text": _fmt_sec(len_b), "len_after_text": _fmt_sec(len_a)}


def _undo_edit(program_id, last, said, live):
    """[HANDS-2] 다듬기·구간빼기를 Receipt 에 적힌 전 값으로 되돌린다."""
    from engine.edit_propose import _apply_state
    fids = list(last.get("fragment_ids") or [])
    tb = last.get("trim_before")
    if not fids or not tb:
        return {"ok": False, "why": "되돌릴 값을 못 찾았어요"}
    fid = fids[0]
    sp = _fragment_spans([fid]).get(fid)
    if not sp:
        return {"ok": False, "why": "그 조각의 원본 자리를 못 찾았어요"}
    source_id, a_s, a_e = sp
    cur = _cur_state(program_id, fid, (a_s, a_e))
    try:
        _apply_state(program_id, fid, source_id, (a_s, a_e),
                     (int(tb[0]), int(tb[1])), "RESTORE",
                     excluded_ranges=[[int(a), int(b)]
                                      for a, b in (last.get("excl_before") or [])])
    except Exception as e:
        return {"ok": False, "why": f"되돌리기 저장이 안 됐어요 ({e})"}
    after = _cur_state(program_id, fid, (a_s, a_e))
    len_b, len_a = _kept_ms(cur), _kept_ms(after)
    subj = last.get("subject") or "그 조각"
    what = (f"{subj}을 손대기 전으로 되돌렸어요 — "
            f"{_fmt_sec(len_b)}에서 {_fmt_sec(len_a)}가 됐어요")
    _receipt(program_id, what, [fid], 0, 0, said, op="edit_undo", subject=subj,
             extra={"undid_ts": last.get("ts")})      # [HANDS-2]
    print(f"[HANDS] {what}")
    n_live = len(live)
    return {"ok": True, "what": what, "before": n_live, "after": n_live, "n": 1,
            "op": "edit_undo", "live": live, "fragment_id": fid,
            "trim_after": [after["trim_start_ms"], after["trim_end_ms"]],
            "excl_after": after["excluded_ranges"],
            "len_before_ms": len_b, "len_after_ms": len_a,
            "len_before_text": _fmt_sec(len_b), "len_after_text": _fmt_sec(len_a)}


# ── 정정 — "아니야, 그거 말고 A60이야" ─────────────────────────────────
#   [FIX-CORRECT 2026-08-11] 착수 시점 지형(실측 raw, 같은 무대 8조각):
#     T16 "두번째 조각 빼줘" → "아니야, 두번째조각은 a60이야"
#        turn2 cap=remove_fragment args={} → A60 을 뺐다. ★그런데 잘못 뺀 A59 를
#        되살리지 않았다.★ 8→7→6. 정정을 ★새로운 삭제 명령★으로 읽었다.
#     T17 "3번째 조각 빼줘" → "아 잘못 말했어. 4번째였어"
#        turn2 cap=None(just_talk) — 결은 "4번째 조각을 빼드릴게요"라고 ★말만★ 했다.
#     T18 "마지막 조각 빼줘" → "아니 그거 말고 첫번째"
#        turn2 cap=None(just_talk) — 같은 모양. 세상은 무변.
#   두 모양이지만 병은 하나다: CCUT 의 손 어휘에 ★'정정'이라는 개념이 없다.★
#   매 턴이 독립 명령이라, 앞 턴을 무른다는 뜻을 담을 칸이 어디에도 없었다.
#   맨몸 젬마3(프롬프트 주입 0)은 같은 말을 알아듣고 "A60을 다시 넣겠다"고
#   답했다 — 모델의 한계가 아니라 ★배선★이다.
#
#   여기서 만드는 것: 직전 실행을 무르고(restore_fragment 와 ★같은 통로★),
#   새로 말한 대상에 같은 일을 다시 한다. 되끼우는 자리 규칙도 두 벌을 안 만든다
#   (_reinsert_into_story 가 order_before 1순위로 이미 정해 놓은 것을 그대로 쓴다).

# 앞의 말을 고치는 말. ★이것 하나로는 안 잇는다★ — 아래 correcting() 이
#   '새 대상까지 말했는가'와 '되돌릴 것이 있는가'를 함께 본다(찍지 않는다).
_CORRECT_RE = re.compile(
    r"아니(?:야|아|요|라|고|\s)|아냐|"
    r"잘못\s*(?:말했|말한|봤|짚|골랐|했|들었)|틀렸|틀렸어|"
    r"(?:그거|그게|그건|저거|저게|이거|그것)\s*말고|"
    r"말고\s*(?:그|저|이|첫|처음|마지막|앞|뒤|\d)")


def _last_undoable(program_id, limit=12):
    """되돌릴 수 있는 직전 실행 하나.

    ★restore_fragment 가 쓰던 규칙을 ★그대로★ 함수로 꺼낸 것이다(두 벌 금지).
      되돌린 것을 또 되돌리지 않게 undid_ts 로 소비 표시를 본다 — 그 규칙이
      두 곳에 흩어지면 언젠가 한 곳만 고쳐진다(이 저장소가 반복해서 겪은 부채).
    """
    rs = recent_receipts(program_id, limit)
    _used = {r.get("undid_ts") for r in rs if r.get("undid_ts")}
    return next((r for r in rs
                 if r.get("op", "remove") in ("remove", "reorder", "trim", "exclude")
                 and (r.get("fragment_ids") or r.get("order_before"))
                 and r.get("ts") not in _used), None)


def correcting(said, program_id, fragment_labels=None):
    """[FIX-CORRECT] 방금 한 것을 무르고 대신 이걸 해 달라는 말인가.

    ★둘이 다 있어야 참이다. 하나라도 없으면 안 잇는다 — 찍는 것이 아니라
      아는 것만 잇는다(_resolve_label 이 라벨에서 지킨 것과 같은 규율).
        ① 앞말을 고치는 말      '아니야' · '잘못 말했어' · '그거 말고'
        ② 대신 할 ★새 대상★     라벨(A60) 또는 순번(4번째·첫번째·마지막)
      ②가 없으면 안 잇는 이유: "아니 진짜 좋다" 한 마디에 방금 한 멀쩡한 편집이
      무를 뻔한다. T11 '그거 말고 앞에꺼'(되묻기가 정답인 자리)도 여기서 걸린다 —
      '앞에꺼'는 짚을 수 있는 자리가 아니다.

    ★'되돌릴 직전 실행이 있는가'는 ★여기서 묻지 않는다.★ 그건 손 안에서
      묻는다(_do_correct_last). 여기서 걸러 버리면 마른 경로에서 손이 아예
      안 불리고, 그러면 결이 "수정해 드릴게요"라고 ★말만★ 하고 아무 일도 안
      일어난다(실측 S2). 그게 CCUT 이 제일 싫어하는 모양이라, 무를 게 없다는
      사실도 손이 말하게 한다.
    """
    t = str(said or "")
    if not _CORRECT_RE.search(t):
        return False
    live, _ = _live_fids(program_id)
    if not live:
        return False
    return bool(_labels_in(t, fragment_labels)
                or _target_pos(t, len(live)) is not None)


def _do_correct_last(program_id, args, said, live, fragment_labels):
    """[FIX-CORRECT] 무르고 → 새 대상에 같은 일을.

    ★순서가 중요하다: 먼저 무르고 나서 순번을 읽는다.
      "3번째 빼줘" → "4번째였어" 의 4번째는 ★사용자가 처음에 보던 목록★의
      4번째다(잘못 뺀 것이 돌아온 뒤의 목록). 무르기 전 목록에서 세면 한 칸씩
      밀린 엉뚱한 조각을 뺀다.
    ★못 읽으면 지어내지 않는다. 무른 것까지는 사실이니 그것만 말하고 되묻는다.
    """
    # ★무르기 ★전에★ '대신 무엇을'이 말 안에 있는지부터 본다.
    #   실측(24과제 2회차): 결이 '그럼 다시' · '그거 말고 앞에꺼' 같은 흐린 말에도
    #   correct_last 를 골랐다. 그 말들은 정답이 ★되묻기★인 자리다. 대상을 안
    #   보고 먼저 무르면, 흐린 한마디에 방금 한 멀쩡한 편집이 사라진다.
    #   자리 수는 len(live)+1 로 센다 — 무르고 나면 조각이 하나 돌아오니까
    #   ("8번째였어"를 지금 7조각이라고 내치지 않는다).
    if not (_labels_in(said, fragment_labels)
            or _target_pos(said, len(live) + 1) is not None):
        return {"ok": False, "why": "대신 어느 조각인지 못 알아들었어요"}
    last = _last_undoable(program_id)
    if not last:
        # ★마른 경로 — 무를 것이 없다. 지어내지 않는다.
        #   여기서 '그럼 그냥 그 조각을 빼자'로 가지 않는 이유: 첫 턴의
        #   "아니야, 두번째 조각은 A60이야" 는 ★이름이 틀렸다고 알려 주는 말★일
        #   수도 있다. 뜻이 둘인데 하나를 골라 세상을 바꾸면 그게 지어내는 것이다.
        return {"ok": False,
                "why": "아직 무를 게 없어요(방금 한 편집이 없어요)"}
    op = last.get("op", "remove")
    before = len(live)
    if op == "reorder":
        undo = _undo_reorder(program_id, last, said, before)
    elif op in ("trim", "exclude"):
        undo = _undo_edit(program_id, last, said, live)
    else:
        undo = _undo_remove(program_id, last, said, before)
    if not undo.get("ok"):
        return undo
    live2 = list(undo.get("live") or _live_fids(program_id)[0])
    back = str(undo.get("what") or "방금 한 것을 되돌렸어요")
    if op != "remove":
        # 뺀 것 말고는 '대신 무엇을'을 아직 못 읽는다(순서·분량은 대상 하나로
        #   안 정해진다). 무른 것은 사실대로 말하고 다시 묻는다 — 지어내지 않는다.
        print(f"[HANDS][CORRECT] {op} 를 무르기까지만 했다 — 대신 무엇을 할지는 "
              f"못 읽는다: {str(said)[:30]!r}")
        return {**undo, "what": back + " — 대신 어떻게 할지 다시 말씀해 주세요"}
    fid, name, why = _resolve_target(args, said, live2, fragment_labels)
    if not fid:
        _tail = (f" — 그런데 {why}" if why
                 else " — 그런데 대신 어느 조각을 뺄지는 못 알아들었어요")
        print(f"[HANDS][CORRECT] 무르기는 했는데 새 대상을 못 짚었다: "
              f"{str(said)[:30]!r}")
        return {"ok": True, "what": back + _tail, "before": before,
                "after": len(live2), "n": 0, "live": live2}
    res = _take_out(program_id, [fid], f"{name}을 대신 뺐어요", name, said,
                    len(live2), extra={"corrected_from": last.get("ts")})
    if not res.get("ok"):
        # 무르기는 실제로 됐다 — 그 사실을 삼키지 않는다.
        return {"ok": True, "what": back + f" — 그런데 {res.get('why')}",
                "before": before, "after": len(live2), "n": 0, "live": live2}
    _und = last.get("subject") or "방금 뺀 것"
    what = f"{_und}을 다시 넣고 {name}을 대신 뺐어요"
    print(f"[HANDS][CORRECT] {what}: {before}→{res['after']}조각")
    return {"ok": True, "what": what, "before": before, "after": res["after"],
            "n": res.get("n") or 1, "op": "correct", "live": res["live"]}


def can_reach(cap, args, said, fragment_labels=None):
    """[HANDS-2] 좌표 손이 짚을 데가 있나 — main.py 의 우회로 판단에 쓰인다.

    착수 시점 모양이 뒤집혀 있었다(main.py:5920-5923): cap 이 trim/exclude 이고
    args.fragment 가 비면 무조건 초안 회로로 넘겼다. 그래서 ★조각을 지목하면
    HOLD(아무 일도 안 남), 지목 안 하면 서버가 알아서 TRIM★ 이었다.
    이제 손이 있으니 반대로 읽는다 — 짚을 수 있으면 손이 하고, 짚을 데도 분량도
    없는 말('여기가 늘어져')만 초안 회로로 간다. 초안 회로는 죽이지 않는다.
    """
    t = str(said or "")
    if str((args or {}).get("fragment") or "").strip():
        return True
    if _AMT_ANY_RE.search(t) or _INNER_RE.search(t):
        return True
    if re.search(r"번째|마지막|첫\s*조각", t):
        return True
    if _labels_in(t, fragment_labels):
        return True
    return False


def _route_by_words(cap, args, said, live, fragment_labels):
    """결이 고른 손과 사용자가 한 말이 어긋날 때 — 읽는 쪽을 넓혀 같은 자리로 모은다.

    ★결에게 검문을 세우지 않는다(국장 지시). 결이 흘리거나 옆칸을 고른 것을
      사용자의 원문으로 이어 준다 — _resolve_label 이 라벨에서 한 것과 같은 방식.
    실측(수리 전, 같은 문장 5회씩): '2번째 빼줘' 0/5 · '세 번째 조각 빼줘' 0/5.
      전자는 exclude_range 로 가서 [DESK][HOLD](세상 무변인데 "제외하겠습니다"),
      후자는 remove_fragment{fragment:''} 로 가서 "'그것'이 원고에서 안 보여요".
    """
    t = str(said or "")
    n = len(live)
    # ⓪ [HANDS-2 되돌아옴] "몇 조각으로" 는 개수를 맞춰 달라는 말이다.
    #   실측(검증 뒤): '다시 5조각으로 되돌려줘' → 결이 remove_ordinal 을 골라
    #   "지금 조각은 1개예요" 로 막혔다. 늘리는 손은 아래 set_count 안에 있는데
    #   말이 거기까지 못 갔다. '조각을'(대상)과 '조각으로'(개수)를 가르는 것은
    #   원문의 조사 하나뿐이라, 읽는 쪽에서 그 하나를 본다.
    from engine import night2_probe as _n2                    # [NIGHT-2] E축
    if cap in ("remove_ordinal", "remove_fragment", "set_count"):
        _cm = re.search(r"(\d+|" + "|".join(_KO_NUM) + r")\s*(?:조각|개)\s*(?:으)?로", t)
        if _cm:
            _cw = _cm.group(1)
            _cnt = int(_cw) if _cw.isdigit() else _KO_NUM[_cw]
            _changes = (cap != "set_count"
                        or str((args or {}).get("count")) != str(_cnt))
            # 바꾸는 게 없는 경우(이미 set_count·같은 수)는 검문이 아니라 무동작이다
            #   — 그림자에서도 그대로 둔다(기록만 부풀리지 않는다).
            if not _changes or _n2.guard(
                    "SLOT-FIX", which="count_josa", cap_in=cap, args_in=args,
                    said=t[:100], cap_out="set_count", count=_cnt):
                if _changes:
                    print(f"[HANDS][SLOT-FIX] '{_cw}조각으로' = 개수 이야기다 "
                          f"→ {cap} → set_count {_cnt}: {t[:30]!r}")
                cap, args = "set_count", {"count": _cnt}
    # ① 좌표 손으로 왔는데 말에는 분량도 조각 안쪽 지칭도 없다 → 통째로 빼 달라는 말.
    if cap in ("trim_boundary", "exclude_range"):
        if (not _AMT_ANY_RE.search(t) and not _INNER_RE.search(t)
                and re.search(r"빼|지워|삭제|없애", t)
                and _n2.guard("SLOT-FIX", which="no_amount_remove_whole",
                              cap_in=cap, args_in=args, said=t[:100],
                              cap_out="remove_fragment")):
            print(f"[HANDS][SLOT-FIX] 분량도 안쪽 지칭도 없다 → {cap} → 통째로 빼기: {t[:30]!r}")
            cap, args = "remove_fragment", dict(args or {})
    # ①-2 경계(앞·뒤)와 가운데는 다른 손이다. 결이 둘을 바꿔 잡는다 —
    #   실측: '두 번째 조각 뒤 3초 덜어줘' → exclude_range → 조각 ★한가운데★에
    #   3초 구멍이 뚫렸다(사용자는 꼬리를 자르라고 했다). 사용자가 어디를
    #   말했는지는 원문에 있다. 결을 막지 않고 원문으로 손을 바로잡는다.
    _mid = bool(_MID_ONLY_RE.search(t))
    _side = _trim_side(t, {})            # 결의 슬롯은 보지 않는다 — 원문만
    if (cap == "exclude_range" and not _mid and _side and _n2.guard(
            "SLOT-FIX", which="middle_to_boundary", cap_in=cap, args_in=args,
            said=t[:100], cap_out="trim_boundary", side=_side)):
        print(f"[HANDS][SLOT-FIX] 가운데가 아니라 경계({_side}) 이야기다 "
              f"→ exclude_range → trim_boundary: {t[:30]!r}")
        cap = "trim_boundary"
    elif (cap == "trim_boundary" and _mid and not _side and _n2.guard(
            "SLOT-FIX", which="boundary_to_middle", cap_in=cap, args_in=args,
            said=t[:100], cap_out="exclude_range")):
        print(f"[HANDS][SLOT-FIX] 경계가 아니라 가운데 이야기다 "
              f"→ trim_boundary → exclude_range: {t[:30]!r}")
        cap = "exclude_range"
    # ② 조각 이름 자리에 순번이 왔거나 슬롯이 비었는데 원문에 순번이 있다.
    if cap == "remove_fragment":
        spoken = str((args or {}).get("fragment") or "")
        if not _labels_in(t, fragment_labels) and not _labels_in(spoken, fragment_labels):
            pos = _target_pos(spoken, n)
            if pos is None:
                pos = _target_pos(t, n)
            if pos is not None and _n2.guard(
                    "SLOT-FIX", which="label_is_ordinal", cap_in=cap,
                    args_in=args, said=t[:100], cap_out="remove_ordinal",
                    index=pos + 1):
                print(f"[HANDS][SLOT-FIX] 라벨이 아니라 순번이다 → remove_ordinal "
                      f"{pos + 1}번째: {t[:30]!r}")
                cap, args = "remove_ordinal", {"index": pos + 1}
    # ③ 순번 손인데 index 를 흘렸다 → 사용자 원문에서 읽는다.
    if cap == "remove_ordinal":
        try:
            int((args or {}).get("index"))
        except (TypeError, ValueError):
            pos = _target_pos(t, n)
            if pos is not None and _n2.guard(
                    "SLOT-FIX", which="index_dropped", cap_in=cap, args_in=args,
                    said=t[:100], index=pos + 1):
                print(f"[HANDS][SLOT-FIX] index 를 흘렸다 → 원문에서 {pos + 1}번째")
                args = {"index": pos + 1}
    return cap, args


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


# ── 내보내기(Export) — CLAUDE.md "Export는 되돌릴 수 없는 유일한 문" ──────
#   [EXPORT-1 2026-08-09] "편집한 대로 결과가 나온다"를 처음 잇는다.
#   흐름: propose_export(요약 승인 문구, 상태 지문 저장)
#         → confirm_export(실행 직전 재검증 → 렌더 → Receipt)
#   렌더 자체는 새로 안 만든다 — ledger_r0.get_render_edl 이 이미 REMOVE/
#   RESTORE를 compile_spans 로 반영한 EDL을 만들고, engine.render_engine 이
#   이미 검증된 ffmpeg 파이프라인이다. 여기서 하는 일은 그 둘을 잇고,
#   승인·재검증 안전벨트를 두르는 것뿐이다.
EXPORT_PROPOSE_KIND = "export_propose"
EXPORT_DONE_KIND = "export_done"
_EXPORT_STALE_MS = 30 * 60 * 1000  # 30분 지난 승인은 다시 확인받는다.


def _edit_state_fingerprint(program_id, live):
    """지금 이 순간의 편집 상태를 하나의 문자열로 — 승인과 실행 사이에 편집이
    바뀌었는지 비교하는 유일한 방법(안전벨트②, 국장 지시).

    조각 '집합·순서'뿐 아니라 trim_start/trim_end/excluded_ranges/removed 까지
    담는다 — 조각 수가 같아도 trim 만 바뀌면 다른 산출물이 나오기 때문이다.
    fid 키는 CONCEPT_CODE_MAP 의 Timeline Item 발급식(ITEM_{h6}_{fid}_0)과
    ★같은 식★을 쓴다 — 제3의 키 체계를 만들면 fid 좌표 앵커 원칙을 어긴다.
    """
    import hashlib
    from edit_contract import service as _edit
    try:
        states = _edit.list_edit_states(program_id)
    except Exception:
        states = []
    by_item = {s["timeline_item_id"]: s for s in states}
    h6 = None
    try:
        import ledger_r0
        h6 = ledger_r0._hash6(program_id)
    except Exception as e:
        print(f"[HANDS][EXPORT][WARN] h6 계산 실패: {e}")
    parts = []
    for fid in live:
        item_id = f"ITEM_{h6}_{fid}_0" if h6 else fid
        s = by_item.get(item_id)
        if s:
            parts.append("|".join(str(x) for x in (
                fid, s.get("trim_start_ms"), s.get("trim_end_ms"),
                json.dumps(s.get("excluded_ranges") or [], sort_keys=True),
                s.get("removed"))))
        else:
            parts.append(f"{fid}|_|_|_|_")
    return hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:16]


def _export_edl(program_id):
    """ledger_r0.get_render_edl 을 그대로 부른다(REMOVE/RESTORE 반영된
    Render Span) — 계산 로직을 여기서 복제하지 않는다. 비동기 함수를
    desk_hands 의 동기 세계에서 쓰기 위한 얇은 다리일 뿐이다."""
    import asyncio
    import ledger_r0
    return asyncio.run(ledger_r0.get_render_edl(program_id))


def _fmt_ms(ms):
    s = round((ms or 0) / 1000.0)
    m, s = divmod(int(s), 60)
    return f"{m}분{s:02d}초" if m else f"{s}초"


def _do_propose_export(program_id, said):
    """① 승인 문구 — 지금 편집 상태의 요약(조각 수·예상 길이)을 반드시 담는다
    (안전벨트①). 세상을 바꾸지 않는다 — 지문만 원장에 남겨 confirm 이 비교할
    수 있게 한다."""
    live, _ = _live_fids(program_id)
    if not live:
        return {"ok": False, "why": "아직 원고가 없어요 — 먼저 이야기를 만들어야 해요"}
    edl = _export_edl(program_id)
    if not edl.get("ok"):
        return {"ok": False, "why": f"편집 결과를 계산하지 못했어요 — {edl.get('reason', edl)}"}
    clip_count = edl.get("clip_count", 0)
    total_ms = edl.get("total_ms", 0)
    if clip_count == 0:
        return {"ok": False, "why": "지금 상태로는 남는 장면이 없어요 — 다 빼면 만들 게 없어요"}
    snap = _edit_state_fingerprint(program_id, live)
    from engine import timeline_store as _ts
    _ts.append_entries(program_id, [{
        "kind": EXPORT_PROPOSE_KIND,
        "client_id": f"export_propose_{int(time.time() * 1000)}",
        "ts": time.time() * 1000,
        "payload": {"snapshot": snap, "fragment_count": len(live),
                    "clip_count": clip_count, "total_ms": total_ms,
                    "said": (said or "")[:160]},
    }])
    what = (f"지금 상태로 내보내면 조각 {len(live)}개(클립 {clip_count}개), "
            f"길이 약 {_fmt_ms(total_ms)}짜리 영상이 나와요. 이대로 만들까요?")
    print(f"[HANDS][EXPORT] propose: {len(live)}조각 · {clip_count}클립 · "
          f"{total_ms}ms · snap={snap}")
    return {"ok": True, "what": what, "propose": True,
            "fragment_count": len(live), "clip_count": clip_count,
            "total_ms": total_ms, "live": live}


def _last_export_propose(program_id):
    from engine import timeline_store as _ts
    try:
        rows = _ts.fetch(program_id, limit=200) or []
    except Exception:
        return None
    for r in reversed(rows):
        if r.get("kind") == EXPORT_PROPOSE_KIND:
            p = r.get("payload") or {}
            p["ts"] = r.get("ts")
            return p
    return None


def _render_edl_to_file(program_id, edl):
    """검증된 렌더 엔진을 그대로 쓴다 — engine.render_engine.RenderEngine.
    ExportInput(제안 파이프라인 전용 DB 행)을 새로 만들지 않는다. 그 테이블은
    A/B 제안·펀치인 실험을 위한 것이고, 여기는 Edit State → EDL → 파일이라는
    더 짧은 경로다. _render_with_ffmpeg 자체(클립 추출·concat·faststart)는
    100% 재사용한다 — 새 ffmpeg 파이프라인을 만들지 않는다."""
    from engine.render_engine import render_engine as _renderer
    clips = [{
        "source_id": c["source_id"], "start": c["start_sec"], "end": c["end_sec"],
        "duration": c["duration_sec"], "order": c["order"],
        "fragment_id": c["fragment_id"],
    } for c in edl.get("clips", [])]
    source_map = _renderer._resolve_source_paths(
        clips, {"source_id": clips[0]["source_id"] if clips else None})
    if not source_map["ok"]:
        return {"success": False, "error_msg": source_map["reason"]}
    import uuid
    h6 = ""
    try:
        import ledger_r0
        h6 = ledger_r0._hash6(program_id)
    except Exception:
        pass
    out_name = f"EXPORT_{h6}_{uuid.uuid4().hex[:8].upper()}.mp4"
    out_path = _renderer.export_dir / out_name
    result = _renderer._render_with_ffmpeg(
        clips=clips, source_paths=source_map["paths"], output_path=str(out_path),
        technique=None, program_id=program_id)
    result["output_path"] = str(out_path)
    result["output_url"] = f"/static/exports/{out_name}"
    return result


def _render_edl_with_heartbeat(program_id, edl, on_progress=None, beat_sec=15):
    """_render_edl_to_file 을 별도 스레드에서 돌리고, 끝날 때까지 주기적으로
    깨어나 on_progress 에 '아직 하고 있다'를 알린다. ffmpeg 진행률(%) 파이프는
    없다(정찰 확인) — 대신 살아있다는 것만이라도 말한다."""
    if not on_progress:
        return _render_edl_to_file(program_id, edl)
    import threading
    box = {}

    def _work():
        try:
            box["result"] = _render_edl_to_file(program_id, edl)
        except Exception as e:
            box["result"] = {"success": False, "error_msg": str(e)}

    th = threading.Thread(target=_work, daemon=True)
    th.start()
    beats = 0
    while th.is_alive():
        th.join(timeout=beat_sec)
        if th.is_alive():
            beats += 1
            on_progress({"type": "token",
                         "text": "\n(아직 렌더링 중이에요, 조금만 더 기다려 주세요…)\n"})
    return box.get("result") or {"success": False, "error_msg": "렌더 스레드가 결과를 안 남겼어요"}


def _do_confirm_export(program_id, said, on_progress=None):
    """② 실행 직전 재검증(안전벨트②) → ③ 렌더 → ④ Receipt(안전벨트③).

    승인과 실행 사이에 편집이 바뀌었으면 멈추고 다시 묻는다 — 실행하지 않는다.

    on_progress(선택): 렌더가 도는 동안 결이 침묵하지 않게 부르는 콜백.
    ★[EXPORT-2 2026-08-09] "오래 걸리는 일에서 말이 끊기면 사용자는 고장으로
      읽는다"(국장 지시) — ffmpeg 진행률 파이프는 없지만(정찰 결과), 렌더를
      별도 스레드로 옮기고 여기서 주기적으로 깨어나 부르면 최소한 "시작했다"
      "아직 하고 있다"는 말은 낼 수 있다. 풀 스트리밍이 아니어도 침묵보다는 낫다.
    """
    pending = _last_export_propose(program_id)
    if not pending:
        return {"ok": False,
                "why": "아직 요약을 보여드린 적이 없어요 — 먼저 내보내기를 요청해 주세요"}
    if (time.time() * 1000 - float(pending.get("ts") or 0)) > _EXPORT_STALE_MS:
        return {"ok": False,
                "why": "승인해 주신 지 시간이 좀 지났어요 — 다시 한 번 확인할게요. "
                       "내보내기를 다시 요청해 주세요"}
    live, _ = _live_fids(program_id)
    if not live:
        return {"ok": False, "why": "지금은 원고에 남은 조각이 없어요"}
    now_snap = _edit_state_fingerprint(program_id, live)
    if now_snap != pending.get("snapshot"):
        # ★안전벨트② — 승인 시점과 실행 시점의 Edit State가 다르면 실행하지
        #   않는다. 조용히 옛 승인으로 진행하지 않는다.
        print(f"[HANDS][EXPORT][RE-VERIFY] 상태 바뀜: {pending.get('snapshot')} "
              f"→ {now_snap} — 실행 중단, 다시 승인 받는다")
        return _do_propose_export(
            program_id,
            "(승인 이후 편집이 바뀌어 다시 확인합니다) " + (said or ""))

    # [HANDS-2 되돌아옴] ★안전벨트④ — 승인 관문(story_gate)에 실제로 닿는다.
    #   여기가 검증이 잡은 "정의는 있는데 호출처 0건" 자리다. 렌더 전에 부른다.
    _gate_ok, _gate_note, _gate_why = _reach_render_gate(program_id, said)
    if not _gate_ok:
        return {"ok": False, "why": _gate_why}

    edl = _export_edl(program_id)
    if not edl.get("ok") or not edl.get("clips"):
        return {"ok": False, "why": "편집 결과를 다시 계산하지 못했어요"}

    # ★[NIGHT-2 2026-08-10] 밤 실험 중에는 여기서 멈춘다 — ffmpeg 바로 앞이다.
    #   왜 READ_ONLY 에서 confirm_export 를 빼지 않았나(국장 원안): 그렇게 하면
    #   승인 답이 "네"처럼 짧아 ASK-GUARD 의 tiny-ack(6자)에 걸려 제품이 깨진다
    #   (HANDS-2 가 의도적으로 넣은 자리다). 그래서 제품 배선은 그대로 두고
    #   env 로 렌더만 막는다. ★기본 OFF = 현행 그대로.★
    #   여기까지 온 것은 안전벨트②(상태 재검증)·④(승인 관문)를 이미 통과한
    #   상태다 — 막는 것은 파일을 만드는 일 하나뿐이고, 막았다는 사실을 숨기지
    #   않고 그대로 말한다(조용한 변경 금지).
    if (os.getenv("CCUT_NIGHT2_NO_RENDER") or "").strip() in ("1", "true", "True", "on"):
        print(f"[HANDS][EXPORT][NIGHT-2] 렌더 차단(CCUT_NIGHT2_NO_RENDER=1) — "
              f"{pending.get('fragment_count')}조각 {pending.get('clip_count')}클립까지 "
              f"확인하고 멈춘다")
        return {"ok": False, "night2_blocked": True,
                "why": "지금은 시험 중이라 실제 영상 파일은 만들지 않아요 — "
                       "여기까지는 다 확인했어요"}

    print(f"[HANDS][EXPORT] confirm → 렌더 시작: {pending.get('fragment_count')}조각 "
          f"{pending.get('clip_count')}클립")
    if on_progress:
        on_progress({"type": "token",
                      "text": f"\n(내보내기를 시작할게요 — 조각 {pending.get('fragment_count')}개, "
                              f"약 {_fmt_ms(pending.get('total_ms') or 0)}. 렌더링에는 시간이 "
                              f"좀 걸릴 수 있어요, 끝나면 바로 말씀드릴게요.)\n"})
    result = _render_edl_with_heartbeat(program_id, edl, on_progress)
    if not result.get("success"):
        return {"ok": False,
                "why": f"렌더가 실패했어요 — {result.get('error_msg') or result.get('stderr', '')[:200]}"}

    # [NIGHT-2] 여기 있던 함수-지역 `import os` 를 걷었다 — 지역 import 는 함수
    #   전체에서 os 를 지역 이름으로 만들어, 위 렌더 차단의 os.getenv 가
    #   UnboundLocalError 로 죽는다. os 는 이제 모듈 상단에 있다.
    out_path = result["output_path"]
    size_bytes = os.path.getsize(out_path) if os.path.exists(out_path) else 0
    duration_sec = result.get("duration", 0.0)
    from engine import timeline_store as _ts
    _ts.append_entries(program_id, [{
        "kind": EXPORT_DONE_KIND,
        "client_id": f"export_done_{int(time.time() * 1000)}",
        "ts": time.time() * 1000,
        "payload": {"output_path": out_path, "output_url": result["output_url"],
                    "size_bytes": size_bytes, "duration_sec": duration_sec,
                    "fragment_count": pending.get("fragment_count"),
                    "clip_count": pending.get("clip_count"), "said": (said or "")[:160],
                    # [RENDER-1] 어떤 규격으로 나왔는지도 원장에 남긴다 —
                    #   "왜 세로가 가로가 됐나"를 나중에 물으면 답할 수 있어야 한다.
                    "spec": result.get("spec"), "spec_note": result.get("spec_note")},
    }])
    _spec = result.get("spec") or {}
    # [RENDER-1 되돌아옴] 읽지 못한 규격은 **말하지 않는다**. unread 이면 숫자
    #   자체가 기본값이라, 그걸 완료 문구에 적으면 결이 읽은 적 없는 값을
    #   사실처럼 말하게 된다(실측으로 잡힌 모양). 대신 spec_note 가 사실을 말한다.
    _spec_txt = ("" if _spec.get("unread")
                 else (f", {_spec['width']}x{_spec['height']}" if _spec.get("width") else ""))
    # [RENDER-1 되돌아옴 · 마른 경로 실측 2026-08-09] 길이도 같은 문제였다.
    #   duration 은 렌더 끝에 ffprobe 로 재는데, ffprobe 가 죽으면 0.0 이 온다.
    #   실측: 실제 13.7초짜리 파일을 두고 결이 "길이 0.0초" 라고 말했다 —
    #   못 잰 값을 0 으로 말하는 것도 지어내는 것이다. 못 쟀으면 못 쟀다고 한다.
    _dur_txt = (f"길이 {duration_sec:.1f}초" if duration_sec > 0
                else "길이는 확인하지 못했어요")
    what = (f"내보내기를 완료했어요 — 조각 {pending.get('fragment_count')}개, "
            f"{_dur_txt}{_spec_txt}, 크기 {size_bytes / 1024 / 1024:.1f}MB")
    # [HANDS-2 되돌아옴] 승인 도장을 찍었으면 찍었다고 말한다 — 조용한 변경 금지.
    if _gate_note:
        what += f" ({_gate_note})"
    # ★규격이 섞였을 때만 한 문장 통보한다(질문 게이트를 새로 만들지 않는다 —
    #   CLAUDE.md "제약은 내부 계약에만", 메모리 "결에게는 제약 대신 교육").
    if result.get("spec_note"):
        what += "\n" + result["spec_note"]
    print(f"[HANDS][EXPORT] done: {out_path} ({size_bytes}B, {duration_sec:.1f}s)")
    return {"ok": True, "what": what, "output_path": out_path,
            "output_url": result["output_url"], "size_bytes": size_bytes,
            "duration_sec": duration_sec, "spec": result.get("spec"),
            "spec_note": result.get("spec_note"),
            "fragment_count": pending.get("fragment_count"), "live": live}


# ── 손이 할 수 있는 일 ────────────────────────────────────────────────
HANDS = {"remove_scene", "remove_fragment", "remove_ordinal", "set_count",
         "remove_theme", "keep_theme", "restore_fragment", "read_receipt",
         "propose_export", "confirm_export",
         "reorder_story",                          # [HANDS-2] 순서 바꾸기
         "trim_boundary", "exclude_range",         # [HANDS-2] 좌표 손 둘
         "correct_last"}                           # [FIX-CORRECT] 정정
# 세상을 바꾸지 않는 손 — 묻는 말에도 그냥 해도 된다.
#   confirm_export 도 여기 둔다: 국장 화면 흐름상 승인 문구 다음에 오는 답은
#   "네"·"응 해줘" 처럼 아주 짧다(ASK-GUARD의 tiny_ack 문턱 6자에 자주 걸린다).
#   propose_export 가 이미 요약과 재확인 문구를 보여줬으므로, 짧은 대답으로
#   실행이 막히면 오히려 관통이 끊긴다. 안전은 여기가 아니라 confirm_export
#   내부의 상태 재검증(안전벨트②)이 진다.
READ_ONLY = {"read_receipt", "propose_export", "confirm_export"}


def do(cap, args, program_id, fragment_labels=None, scenes=None, said="",
       on_progress=None):
    """젬마가 고른 것을 실제로 한다. 사실(facts)을 돌려준다 — 말은 안 만든다.

    돌려주는 것:
      {"ok": True, "what": 사람이 읽는 한 일, "before": n, "after": n, ...}
      {"ok": False, "why": 왜 못 했는지}   ← 지어내지 않기 위해 이유를 준다

    on_progress(선택): confirm_export 처럼 오래 걸리는 손에게만 쓰인다 —
    나머지 손은 순간에 끝나 필요 없다.
    """
    args = args or {}
    # ★[HANDS-2 2026-08-09] 옮기라는 말에 지우는 손이 잡히는 일이 있다.
    #   실측(같은 문장 3회): "마지막 조각을 맨 앞으로 옮겨줘" → 1회 reorder_story,
    #   2회 remove_ordinal. 그때 index 가 안 맞아 실패해서 살았을 뿐, 맞았으면
    #   **옮겨 달라는 조각을 지웠다.** 되돌릴 수는 있어도 일어나선 안 되는 일이다.
    #   결을 막지 않는다 — 사용자가 친 문장에 옮기는 말이 있고 지우는 말이 없으면
    #   손 쪽에서 옮기기로 읽는다(위 장면 SLOT-FIX 와 같은 모양).
    from engine import night2_probe as _n2                    # [NIGHT-2] E축
    if cap in ("remove_ordinal", "remove_fragment", "remove_scene"):
        _s = str(said or "")
        if (re.search(r"옮겨|옮기|이동|보내", _s)
                and not re.search(r"빼|지워|삭제|없애|잘라", _s)
                and _n2.guard("SLOT-FIX", which="move_not_remove", cap_in=cap,
                              args_in=args, said=_s[:100], cap_out="reorder_story")):
            print(f"[HANDS][SLOT-FIX] 지우라는 말이 아니라 옮기라는 말이다 "
                  f"→ {cap} → reorder_story: {_s[:30]!r}")
            cap, args = "reorder_story", {}
    # 젬마가 장면을 조각 이름 자리에 넣는 일이 잦다 — 실측: '6번 장면 빼줘' →
    #   remove_fragment{fragment:'6번 장면'} → "'6번 장면'이 원고에서 안 보여요".
    #   가리키는 것이 장면이면 장면 손으로 넘긴다. 뜻은 분명한데 칸만 틀린 것을
    #   못 알아들은 척하지 않는다.
    if cap == "remove_fragment":
        _t = str(args.get("fragment") or "")
        _m = re.search(r"(\d+)\s*번", _t)
        if _m and ("장면" in _t or "씬" in _t) and _n2.guard(
                "SLOT-FIX", which="fragment_is_scene", cap_in=cap, args_in=args,
                said=str(said or "")[:100], cap_out="remove_scene"):
            cap, args = "remove_scene", {"scene_no": int(_m.group(1))}
            print(f"[HANDS][SLOT-FIX] 조각이 아니라 장면이다 → remove_scene {_m.group(1)}번")
    live, _ = _live_fids(program_id)
    before = len(live)

    if cap == "read_receipt":
        rs = recent_receipts(program_id, 3)
        return {"ok": True, "what": "방금 한 일을 확인했어요", "before": before,
                "after": before, "receipts": rs, "nothing": not rs,
                "live": live}

    if cap == "propose_export":
        return _do_propose_export(program_id, said)

    if cap == "confirm_export":
        return _do_confirm_export(program_id, said, on_progress=on_progress)

    if not live:
        return {"ok": False, "why": "아직 원고가 없어요 — 먼저 이야기를 만들어야 해요"}

    # ★[FIX-CORRECT 2026-08-11] 정정은 _route_by_words 보다 ★먼저★ 받는다.
    #   저 함수는 "이 말이 어느 손인가"를 원문에서 다시 읽는데, 정정 문장에는
    #   '빼'도 '옮겨'도 없다. 이미 정정이라고 정해진 것을 다시 흔들지 않는다.
    if cap == "correct_last":
        return _do_correct_last(program_id, args, said, live, fragment_labels)

    # [HANDS-2] 결이 고른 손과 사용자의 말이 어긋난 자리를 먼저 모은다.
    cap, args = _route_by_words(cap, args, said, live, fragment_labels)

    if cap == "reorder_story":                      # [HANDS-2]
        return _do_reorder(program_id, args, said, live)
    if cap == "trim_boundary":                      # [HANDS-2]
        return _do_trim(program_id, args, said, live, fragment_labels)
    if cap == "exclude_range":                      # [HANDS-2]
        return _do_exclude(program_id, args, said, live, fragment_labels)

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
        _spoken = str(args.get("fragment") or "").strip().upper()
        fid, lab = _resolve_label(_spoken, _fid_by_label(fragment_labels), said)
        if not fid or fid not in live:
            # [RENDER-1 되돌아옴] 라벨까지는 알아냈는데 원고에 없는 경우, 결이
            #   흘린 조각('7')이 아니라 **알아낸 라벨**('A7')로 말한다.
            #   실측: 사용자가 'A7' 이라고 쳤는데 답은 "'7'이 원고에서 안 보여요".
            return {"ok": False,
                    "why": f"'{(lab if fid else _spoken) or '그것'}'이 원고에서 안 보여요"}
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
        if want == before:
            return {"ok": False, "why": f"이미 {before}개예요"}
        if want > before:
            # [HANDS-2 되돌아옴] 늘리는 손이 없어서 "다시 5조각으로 되돌려줘"가
            #   막혔다(검증 실측). 되살릴 것은 이미 원장에 있다 — 빼 둔 조각을
            #   최근에 뺀 것부터 되넣는다. 새 저장소·새 계약 0, restore 와 같은 길.
            return _grow_count(program_id, want, before, said, live)
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
        # ★[HANDS-2 2026-08-09 라이브 실측] 되돌리기를 두 번 하면 두 번째가
        #   ★이미 되돌린 것을 또★ 되돌렸다. 실측: trim → exclude → "되돌려줘"
        #   (exclude 되돌아감 13.7→15.7초) → "그것도 되돌려줘" → 다시 exclude 를
        #   집어 15.7→15.7초(아무 일도 안 남). trim 은 영영 안 돌아온다.
        #   되돌린 것을 표시해 두고 건너뛴다 — 새 테이블 0, Receipt 안에 적는다.
        # [HANDS-2] 되돌릴 수 있는 것이 '뺀 것' 하나뿐이었다. 순서도, 좌표 손
        #   (trim·exclude)도 되돌린다 — 가장 최근 것 하나만 본다.
        # ★[FIX-CORRECT 2026-08-11] 그 고르는 규칙을 _last_undoable 로 꺼냈다.
        #   정정(_do_correct_last)이 ★같은 통로★를 쓴다 — 두 벌을 만들지 않는다.
        last = _last_undoable(program_id)
        if not last:
            return {"ok": False, "why": "되돌릴 게 없어요 — 아직 손댄 게 없어요"}
        if last.get("op") == "reorder":
            return _undo_reorder(program_id, last, said, before)
        if last.get("op") in ("trim", "exclude"):    # [HANDS-2]
            return _undo_edit(program_id, last, said, live)
        return _undo_remove(program_id, last, said, before)   # [FIX-CORRECT]
    else:
        return {"ok": False, "why": "그건 아직 제가 손이 없어요"}

    # ★[FIX-CORRECT 2026-08-11] 여기 인라인으로 있던 '실제로 빼고 Receipt 남기기'를
    #   _take_out 으로 꺼냈다 — 정정도 같은 자리를 쓴다(빼는 자리는 하나다).
    return _take_out(program_id, targets, what, subject, said, before)
