# -*- coding: utf-8 -*-
"""CCUT 검증 오케스트레이터 — 4층 검증의 L0/L1/L2 실행기.

  L0 단위      LLM 없음, <5초. 결정론 함수만 (revision 파서/적용, intent 어휘,
               골든 단락, alias 매칭, honest-empty 시퀀스 규칙).
  L1 격리판정  golden_cases.json 전 케이스.
               invariant: 골든 단락(_golden_exact_verdict)이 gold를 정확 반환 (결정론 PASS/FAIL)
               drift:     LLM raw 판정과 gold의 일치율 (정보 제공용 — FAIL 없음, 추세 감시)
  L2 제품완주  tools/golden_runner.py run 위임 (백엔드 기동 + LLM 필요, 분 단위)

사용:
  python tools/verify.py L0 | L1 | L2 | all [--no-drift]
커밋 규칙: L0+L1 GREEN 없이 커밋 금지, L2 GREEN 없이 push 금지.
비결정성 원칙: LLM 경로는 불변식/범위로만 판정, 골든 단락 영역만 exact.
"""
import json
import os
import subprocess
import sys

# Windows 콘솔 cp949에서도 유니코드 출력 안전
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "ccut_backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

PASS, FAIL = "PASS", "FAIL"
_results = []


def check(layer, name, ok, detail=""):
    _results.append((layer, name, ok))
    print(f"[{layer}] {PASS if ok else FAIL} {name}" + (f" | {detail}" if detail else ""))
    return ok


# ─────────────────────────────────────────────────────────────── L0
def run_l0():
    os.environ["CCUT_REVISION"] = "1"
    import importlib
    from engine import revision as rev
    importlib.reload(rev)

    seq = [{"fragment_id": f"SF_{i}", "start": i * 10, "end": i * 10 + 5, "duration": 5}
           for i in range(5)]

    d = rev.detect_revision("마지막 조각 빼줘", True)
    check("L0", "rev.detect 마지막빼줘", d == {"op": "remove_ordinal", "index": -1}, str(d))
    s, _ = rev.apply_revision({"op": "remove_ordinal", "index": -1}, seq)
    check("L0", "rev.apply 마지막제거", [f["fragment_id"] for f in s] == ["SF_0", "SF_1", "SF_2", "SF_3"])

    d = rev.detect_revision("3개로 줄여줘", True)
    check("L0", "rev.detect 3개로", d == {"op": "set_count", "count": 3}, str(d))
    s, _ = rev.apply_revision({"op": "set_count", "count": 3}, seq)
    check("L0", "rev.apply set_count", len(s) == 3)
    s, _ = rev.apply_revision({"op": "set_count", "count": 40}, seq)
    check("L0", "rev.apply count>len 무해", len(s) == 5)
    s, _ = rev.apply_revision({"op": "remove_ordinal", "index": 9}, seq)
    check("L0", "rev.apply idx범위밖 no-op", len(s) == 5)

    check("L0", "rev.detect 신규지시는 None", rev.detect_revision("실내만", True) is None)
    check("L0", "rev.detect 제안없으면 None", rev.detect_revision("마지막 조각 빼줘", False) is None)
    os.environ["CCUT_REVISION"] = "0"
    importlib.reload(rev)
    check("L0", "rev 게이트 OFF → None", rev.detect_revision("마지막 조각 빼줘", True) is None)
    os.environ["CCUT_REVISION"] = "1"

    from engine import hub
    di = hub._deterministic_intent("실내만")
    check("L0", "intent 실내만", di["keep"] == "실내" and di["exclude"] is None)
    di = hub._deterministic_intent("실내 빼줘")
    check("L0", "intent 실내빼줘", di["exclude"] == "실내")
    di = hub._deterministic_intent("아이들만 편집해줘")
    check("L0", "intent 아이들만(person palette)", di["keep"] in ("아이", "아이들"), str(di))
    di = hub._deterministic_intent("조각 5개로")
    check("L0", "intent 5개", di["count"] == 5)

    check("L0", "alias 해변→beach",
          bool(hub._scene_alias_hits("beach with sand and waves", hub._aliases_for_theme("해변"))))
    check("L0", "alias 무관장면 미매칭",
          not hub._scene_alias_hits("office desk computer", hub._aliases_for_theme("해변")))

    # [INTENT-ROUTER] 종업원 결정론 사다리 — 지시 케이스 6종 (LLM off, vocab 주입 = DB 무관)
    from engine import intent_router as ir
    _pv = [("PER_TEST", "정은한", ["은한이"])]
    r = ir.route_edit_intent(input_text="은한이만 편집해줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 애칭→정규화 실행", r["action"] == "run_proposal" and "정은한" in (r["normalized_instruction"] or ""),
          f'{r["action"]}/{r["normalized_instruction"]}')
    r = ir.route_edit_intent(input_text="은한이 나오는 장면만 골라줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 애칭+나오는", r["action"] == "run_proposal" and "정은한" in (r["normalized_instruction"] or ""))
    r = ir.route_edit_intent(input_text="정은한만 편집해줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 풀네임", r["action"] == "run_proposal")
    r = ir.route_edit_intent(input_text="이 사람 나오는 것만", allow_llm=False, person_vocab=_pv)
    check("L0", "router 장면어휘(사람)", r["action"] == "run_proposal", r["action"])
    r = ir.route_edit_intent(input_text="B안에서 은한이 아닌 장면 빼줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 제외+애칭 정규화", r["action"] == "run_proposal" and "정은한" in (r["normalized_instruction"] or ""),
          f'{r["action"]}/{r["normalized_instruction"]}')
    r = ir.route_edit_intent(input_text="좀 더 감성적으로 해줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 모호→되묻기(llm off)", r["action"] == "ask_clarification", r["action"])
    r = ir.route_edit_intent(input_text="", allow_llm=False, person_vocab=_pv)
    check("L0", "router 빈입력→되묻기", r["action"] == "ask_clarification")

    # [ARCHIVE P1] 인물+장소 복합 filters — archive_lookup 주입으로 DB 무관
    def _fake_proj(filters, project_source_ids=None):
        return {"scope": "project", "fids": ["SF_X1", "SF_X2", "SF_X3"],
                "by_program": {}, "coverage": {"place_labeled": 90, "total": 100},
                "filter_counts": {}}

    def _fake_arch(filters, project_source_ids=None):
        return {"scope": "archive", "fids": ["SF_A1_SRC_F8AB3DCE"],
                "sources": ["SRC_F8AB3DCE"], "by_program": {"Alnilam": 3},
                "coverage": {"place_labeled": 90, "total": 100}, "filter_counts": {}}

    r = ir.route_edit_intent(input_text="병원 장면만", allow_llm=False, person_vocab=_pv)
    check("L0", "router 장소단독(병원)→det 어휘", r["action"] == "run_proposal", r["action"])
    r = ir.route_edit_intent(input_text="은한이가 병원에 있는 장면만", allow_llm=False,
                             person_vocab=_pv, archive_lookup=_fake_proj)
    check("L0", "router 인물+장소 교집합(project)",
          r["action"] == "run_proposal" and len(r.get("candidate_fragment_ids") or []) == 3
          and {f["type"] for f in r.get("filters") or []} == {"person", "place"},
          f'{r["action"]}/cand={len(r.get("candidate_fragment_ids") or [])}')
    r = ir.route_edit_intent(input_text="바다에서 정은한 나온 장면", allow_llm=False,
                             person_vocab=_pv, archive_lookup=_fake_proj)
    check("L0", "router 장소+인물 순서 무관", r["action"] == "run_proposal"
          and {f["type"] for f in r.get("filters") or []} == {"person", "place"})
    r = ir.route_edit_intent(input_text="은한이가 병원에 있는 장면만", allow_llm=False,
                             person_vocab=_pv, archive_lookup=_fake_arch)
    check("L0", "router 아카이브 히트→ask_include_archive",
          r["action"] == "ask_include_archive" and "Alnilam" in (r.get("reply") or ""),
          r["action"])
    # [ARCHIVE B] "응, 포함해줘" 승인 응답 → 원 지시 재해석 + 소스 포함 실행
    _msgs = [
        {"sender": "user", "text": "은한이가 병원에 있는 장면만 편집해줘"},
        {"sender": "ai", "text": "지금 프로젝트에는 정은한+병원 조각이 없고, "
                                 "아카이브에 있어요 (Alnilam 3개). 아카이브까지 포함할까요?"},
    ]
    r = ir.route_edit_intent(input_text="응, 포함해줘", recent_messages=_msgs,
                             allow_llm=False, person_vocab=_pv, archive_lookup=_fake_arch)
    check("L0", "router 포함승인→실행+소스",
          r["action"] == "run_proposal" and r.get("include_source_ids") == ["SRC_F8AB3DCE"]
          and "정은한이" in (r.get("normalized_instruction") or ""),
          f'{r["action"]}/src={r.get("include_source_ids")}/norm={r.get("normalized_instruction")}')
    r = ir.route_edit_intent(input_text="응", recent_messages=[],
                             allow_llm=False, person_vocab=_pv)
    check("L0", "router 맥락없는 긍정→오작동 없음", r["action"] != "run_proposal" or not r.get("include_source_ids"),
          r["action"])

    # [SHOW] 조회/열람 — "보여줘/있나"는 편집이 아니라 보여주기 (편집 동사 동반 시 편집 우선)
    def _fake_show(text, person):
        return {"results": [{"fragment_id": "SF_X", "title": "테스트영상", "time": "0:00–0:15",
                             "thumbnail_url": None, "video_url": "/static/uploads/SRC_X.mp4",
                             "start": 0, "end": 15, "score": None}],
                "in_project": 1, "in_archive": 0,
                "person": (person or {}).get("canonical")}

    r = ir.route_edit_intent(input_text="정은한 나오는 영상 있나?", allow_llm=False,
                             person_vocab=_pv, search_lookup=_fake_show)
    check("L0", "router 조회(있나)→show_fragments",
          r["action"] == "show_fragments" and len(r.get("results") or []) == 1, r["action"])
    r = ir.route_edit_intent(input_text="은한이 보여줘", allow_llm=False,
                             person_vocab=_pv, search_lookup=_fake_show)
    check("L0", "router 조회(보여줘)+애칭 안내",
          r["action"] == "show_fragments" and "정은한" in (r.get("reply") or ""), r.get("reply"))
    r = ir.route_edit_intent(input_text="은한이 찾아서 편집해줘", allow_llm=False,
                             person_vocab=_pv, search_lookup=_fake_show)
    check("L0", "router 조회+편집동사→편집 우선", r["action"] == "run_proposal", r["action"])

    # [BARE-REDO] 새 조건 없는 "다시해줘"는 옛 지시 무단 재사용 금지 — 되묻기 (물놀이 사건)
    r = ir.route_edit_intent(input_text="편집을 다시해줘.", allow_llm=False,
                             recent_messages=[{"sender": "user", "text": "물놀이 위주로 편집해줘"},
                                              {"sender": "ai", "text": "네"}])
    check("L0", "router 맨몸 다시해줘→되묻기(이전지시 인용)",
          r["action"] == "ask_clarification" and "물놀이" in (r.get("reply") or ""), r.get("reply"))
    r = ir.route_edit_intent(input_text="은한이만 다시 편집해줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 조건있는 다시→정상 편집", r["action"] == "run_proposal", r["action"])

    # [OPEN-EDIT] 메뉴판 밖 자유 테마도 편집 동사가 명확하면 판사 통과 (생일잔치 거부 사건)
    r = ir.route_edit_intent(input_text="생일잔치 장면만 나오게 해줘.", allow_llm=False)
    check("L0", "router 자유테마+편집동사→판사 통과",
          r["action"] == "run_proposal" and "생일잔치" in ((r.get("matched") or {}).get("core") or ""),
          f"{r['action']}/{(r.get('matched') or {}).get('core')}")
    r = ir.route_edit_intent(input_text="생일잔치만 편집해줘.", allow_llm=False)
    check("L0", "router 자유테마 축약형→판사 통과", r["action"] == "run_proposal", r["action"])

    # [SMALLTALK] 질문/잡담은 거절하지 않는다 — 편집 동사 있으면 질문 꼴이어도 편집
    r = ir.route_edit_intent(input_text="편하게 말해도 되?", allow_llm=False)
    check("L0", "router 잡담→따뜻한 응답(거절 금지)",
          r["action"] == "answer_only" and "편집기예요" not in (r.get("reply") or ""),
          (r.get("reply") or "")[:30])
    r = ir.route_edit_intent(input_text="생일잔치만 편집해줄래?", allow_llm=False)
    check("L0", "router 질문꼴 편집요청→편집 우선", r["action"] == "run_proposal", r["action"])
    r = ir.route_edit_intent(input_text="너가 누군지 설명해줘.", allow_llm=False)
    check("L0", "router 정체성 질문→자기소개",
          r["action"] == "answer_only" and "CCUT" in (r.get("reply") or ""), (r.get("reply") or "")[:25])

    # [조사 교정] 단순 replace의 '정은한가' 문법 붕괴 수리 검증
    r = ir.route_edit_intent(input_text="은한이가 병원에 있는 장면만", allow_llm=False,
                             person_vocab=_pv, archive_lookup=_fake_proj)
    check("L0", "router 조사교정 가→이", (r.get("normalized_instruction") or "").startswith("정은한이 "),
          r.get("normalized_instruction"))
    check("L0", "router 조사교정 는→은",
          ir.replace_name("은한이는 어디 있어", "은한이", "정은한") == "정은한은 어디 있어",
          ir.replace_name("은한이는 어디 있어", "은한이", "정은한"))
    check("L0", "router 조사교정 를→을",
          ir.replace_name("은한이를 보여줘", "은한이", "정은한") == "정은한을 보여줘",
          ir.replace_name("은한이를 보여줘", "은한이", "정은한"))
    check("L0", "router 조사교정 무조사 무변",
          ir.replace_name("은한이 나오는 장면만", "은한이", "정은한") == "정은한 나오는 장면만",
          ir.replace_name("은한이 나오는 장면만", "은한이", "정은한"))

    # [TIMELINE] append-only 저장소 — 멱등/시간순/커서/blob 이관 (temp DB, 라이브 무관)
    from engine import timeline_store as tls
    import tempfile
    _tmp = os.path.join(tempfile.gettempdir(), "ccut_l0_timeline.db")
    if os.path.exists(_tmp):
        os.remove(_tmp)
    _orig_tls = tls.DB_PATH
    tls.DB_PATH = _tmp
    try:
        n1 = tls.append_entries("proj_T", [
            {"kind": "message", "client_id": "m1", "ts": 1, "payload": {"t": "a"}},
            {"kind": "generation", "client_id": "gen_g1", "ts": 2, "payload": {"p": 1}}])
        n2 = tls.append_entries("proj_T", [
            {"kind": "message", "client_id": "m1", "ts": 1, "payload": {"t": "a"}}])
        rows = tls.fetch("proj_T")
        check("L0", "timeline append+멱등", n1 == 2 and n2 == 0 and len(rows) == 2,
              f"n1={n1} n2={n2} rows={len(rows)}")
        check("L0", "timeline 시간순+커서",
              rows[0]["client_id"] == "m1"
              and tls.fetch("proj_T", before=rows[1]["entry_id"])[0]["client_id"] == "m1")
        n3 = tls.migrate_from_blob("proj_T", json.dumps({
            "story_plan": {"messages": [{"id": "m1", "timestamp": 1},
                                        {"id": "m9", "timestamp": 9}]},
            "proposal_history": [{"id": "g1", "ts": 2}]}))
        check("L0", "timeline blob 이관(중복 skip)", n3 == 1
              and len(tls.fetch("proj_T")) == 3, f"n3={n3}")
    finally:
        tls.DB_PATH = _orig_tls

    # 골든 단락: 대소문/공백 정규화 포함 exact
    cases = hub._load_golden_cases()
    if cases:
        c0 = cases[0]
        v = hub._golden_exact_verdict(c0["theme"], "  " + c0["tags"].upper() + " ")
        check("L0", "골든 단락 정규화 일치", v == bool(c0["gold"]))
    check("L0", "골든 단락 비골든 None",
          hub._golden_exact_verdict("운동장", "totally unknown scene xyz") is None)


# ─────────────────────────────────────────────────────────────── L1
def run_l1(drift=True):
    from engine import hub
    cases = hub._load_golden_cases()
    check("L1", f"골든 케이스 로드 ({len(cases)}건)", len(cases) > 0)

    # invariant: 단락이 모든 골든에 gold를 정확 반환 (결정론)
    bad = [c for c in cases
           if hub._golden_exact_verdict(c["theme"], c["tags"]) != bool(c["gold"])]
    check("L1", "invariant: 골든 단락 exact 전건",
          not bad, "; ".join(c["tags"][:40] for c in bad))

    if not drift:
        return
    # drift: raw LLM 판정 vs gold 일치율 (정보용, FAIL 없음)
    agree = total = 0
    for c in cases:
        try:
            out = hub._ollama_json(hub._build_judge_lean(c["theme"], [{"fid": "x", "scene": c["tags"]}]))
            item = next((it for it in (out.get("items") or []) if int(it.get("n", 0) or 0) == 1), {})
            raw = bool(item.get("t"))
            total += 1
            agree += (raw == bool(c["gold"]))
            print(f"[L1-drift] {'ok ' if raw == bool(c['gold']) else 'DIFF'} theme={c['theme']} "
                  f"gold={c['gold']} raw={raw} | {c['tags'][:60]}")
        except Exception as e:
            print(f"[L1-drift] skip ({e})")
    if total:
        print(f"[L1-drift] LLM-gold 일치율 {agree}/{total} = {agree / total:.0%} "
              "(정보용 — 단락이 있어 제품 판정은 100% gold)")


# ─────────────────────────────────────────────────────────────── L2
def run_l2():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "golden_runner.py"), "run"])
    check("L2", "golden_runner run", r.returncode == 0)


def summary():
    fails = [(l, n) for l, n, ok in _results if not ok]
    print("\n=== VERIFY SUMMARY ===")
    for layer in ("L0", "L1", "L2"):
        rs = [ok for l, _, ok in _results if l == layer]
        if rs:
            print(f"{layer}: {sum(rs)}/{len(rs)} PASS")
    print("VERDICT:", "GREEN" if not fails else f"RED ({len(fails)} fail)")
    return 1 if fails else 0


if __name__ == "__main__":
    mode = (sys.argv[1] if len(sys.argv) > 1 else "L0").lower()
    drift = "--no-drift" not in sys.argv
    if mode in ("l0", "all"):
        run_l0()
    if mode in ("l1", "all"):
        run_l1(drift=drift)
    if mode in ("l2", "all"):
        run_l2()
    sys.exit(summary())
