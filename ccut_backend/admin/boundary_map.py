"""경계 지도 — 노드가 아니라 **노드 사이**를 본다.

왜: 2026-07-30~31 하루에 잡은 여섯 건이 전부 노드 안이 아니라 노드 **사이**에서 났다.
    8노드 지도로는 여섯 건 다 보이지 않는다. 지도가 있는데 문제가 안 보이면 축척이 틀린 것이다.
    그리고 그 여섯 중 하나(SEQ_INV)는 국장이 재생을 듣다 **귀로** 잡았다. 운에 기대면 안 된다.

절벽:
  ② 전용 계산식을 만들지 않는다 — 수치는 failure_ledger 참조뿐(집계는 COUNT/MIN/MAX).
  ③ 없는 것은 UNKNOWN. 0·초록·기본값으로 채우지 않는다.
  ④ 추출 대상 코드는 **읽기만** 한다.
  ⑤ 손으로 채우지 않는다 — 추출 실패는 "미추출".

자동/수동의 경계를 정직하게 나눈다:
  값·변환·상수·가드   -> 자동 (AST/정규식으로 실제 소스에서 지금 읽는다)
  기본값·폴백         -> 부분 자동 (?? || except 를 소스에서 뜬다)
  순서 의존·권위      -> 자동 불가. **수동 기장** — 감사로 알아낸 것을 여기 적고, 감사할 때마다 자란다.
  비대칭              -> 준자동 (같은 계열 두 자리를 나란히 떠서 대조)
"""

import ast
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(BACKEND_DIR)
FRONTEND_SRC = os.path.join(REPO_DIR, "ccut_frontend", "src")

router = APIRouter(prefix="/admin/anatomy", tags=["anatomy"])

UNEXTRACTED = "미추출"


# ── 추출기 (읽기 전용) ────────────────────────────────────────────────────────

def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def _abs(rel: str) -> str:
    root = FRONTEND_SRC if rel.startswith("ccut_frontend") else REPO_DIR
    return os.path.join(REPO_DIR, rel) if rel.startswith("ccut") else os.path.join(root, rel)


def probe_py_constant(rel_path: str, name: str) -> Dict[str, Any]:
    """파이썬 모듈 최상위 상수의 **현재 값**. AST — import 하지 않는다(부작용 금지)."""
    src = _read(_abs(rel_path))
    if src is None:
        return {"value": UNEXTRACTED, "where": rel_path, "why": "파일 없음"}
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return {"value": UNEXTRACTED, "where": rel_path, "why": f"파싱 실패: {exc}"}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    try:
                        return {"value": ast.literal_eval(node.value), "where": f"{rel_path}:{node.lineno}"}
                    except Exception:
                        return {"value": ast.unparse(node.value), "where": f"{rel_path}:{node.lineno}"}
    return {"value": UNEXTRACTED, "where": rel_path, "why": f"{name} 없음"}


def probe_json_field(rel_path: str, technique_id: str, field: str) -> Dict[str, Any]:
    import json
    src = _read(_abs(rel_path))
    if src is None:
        return {"value": UNEXTRACTED, "where": rel_path, "why": "파일 없음"}
    try:
        data = json.loads(src)
        for item in data.get("techniques", []):
            if item.get("technique_id") == technique_id:
                return {"value": (item.get("engine_effect") or {}).get(field, UNEXTRACTED),
                        "where": f"{rel_path}::{technique_id}.{field}"}
    except Exception as exc:
        return {"value": UNEXTRACTED, "where": rel_path, "why": str(exc)}
    return {"value": UNEXTRACTED, "where": rel_path, "why": f"{technique_id} 없음"}


def probe_line(rel_path: str, pattern: str) -> Dict[str, Any]:
    """소스에서 정규식에 걸리는 **첫 줄을 원문 그대로**. 요약하지 않는다 — 요약이 거짓말의 통로다."""
    src = _read(_abs(rel_path))
    if src is None:
        return {"value": UNEXTRACTED, "where": rel_path, "why": "파일 없음"}
    rx = re.compile(pattern)
    for i, line in enumerate(src.splitlines(), 1):
        if rx.search(line):
            return {"value": line.strip(), "where": f"{rel_path}:{i}"}
    return {"value": UNEXTRACTED, "where": rel_path, "why": f"패턴 미발견: {pattern}"}


# ── 경계 정의 ────────────────────────────────────────────────────────────────
#
# 무엇을 하나의 화살표로 보는가: **한 진실이 다른 진실로 건너가는 지점**.
# 함수 호출 단위가 아니다 — 호출은 수천 개고 사고는 진실이 갈릴 때만 난다.
# 1차 범위는 편집 계열(P3~P5). 이유: 오늘 여섯 건이 전부 여기서 났다.

BOUNDARIES: List[Dict[str, Any]] = [
    {
        "id": "approve_to_playback_contract",
        "from": "story", "to": "edit",
        "label": "승인 → 재생 계약",
        "found": "SEQ_INV 덮어쓰기 (2026-07-31)",
        "kind": "순서",
        "status": "fixed",
        "fixed_by": "dfccbcc1",
        # 수동 기장 — 자동 추출 불가
        "order": "승인이 story.fids 를 즉시 바꾸고, 제안 재생성은 await 없이 던져진다. "
                 "그 사이에 재생하면 **낡은 제안**이 계약 노릇을 한다.",
        "authority": "이중이었다 — 재생 계약=프론트 메모리 proposals / Export=story.fids(DB). "
                     "수리 후: 배열을 만든 출처가 곧 계약(스토리 경로=story.fids).",
        "user_decision_overwritten": True,
        "probes": {
            "순서(무await 호출)": ("line", "ccut_frontend/src/pages/Index.tsx", r"requestProposalsForApprovedStoryRef\.current\?\.\(\)"),
            "계약 원본": ("line", "ccut_frontend/src/components/CenterPanel.tsx", r"const raw = Array\.isArray\(p\?\.key_fragments\)"),
            "가드": ("line", "ccut_frontend/src/components/CenterPanel.tsx", r"SEQ_INV\]\[RESTORE\]"),
        },
    },
    {
        "id": "proposal_edge_to_edl",
        "from": "story", "to": "render",
        "label": "제안 경계 → EDL",
        "found": "B안 word snap 미도달 (2026-07-31)",
        "kind": "전달 누락",
        "status": "fixed",
        "fixed_by": "2b39f672",
        "order": "스냅은 제안 생성 때 일어나고 EDL 은 그 뒤에 만들어진다. 순서는 맞았으나 값이 건너오지 않았다.",
        "authority": "스냅 결과=proposals.sequence / EDL 좌표=semantic_fragments. "
                     "EDL 이 semantic 만 읽어 승인 경계가 매번 원위치로 돌아갔다(실측 11건).",
        "user_decision_overwritten": True,
        "probes": {
            "스냅 기록처": ("line", "ccut_backend/story_gate/proposal_axis.py", r"out\[key\] = round\(mark, 3\)"),
            "EDL 좌표원": ("line", "ccut_backend/ledger_r0.py", r"SELECT source_id, start, \"end\" FROM semantic_fragments"),
            "전달(수리후)": ("line", "ccut_backend/ledger_r0.py", r"PROPOSAL-EDGE"),
            "INV-6 보호": ("line", "ccut_backend/story_gate/proposal_axis.py", r"_has_user_edit_state\(program_id, fid\)"),
        },
    },
    {
        "id": "edl_empty_fallback",
        "from": "render", "to": "export",
        "label": "EDL 빈 응답 → 폴백",
        "found": "빈 EDL 부활 (2026-07-31)",
        "kind": "기본값이 결정을 덮음",
        "status": "fixed",
        "fixed_by": "80b659f1",
        "order": "EDL 취득 실패가 조각맵 파생보다 먼저 판정돼야 한다 — 실패를 '없음'으로 읽으면 폴백이 켜진다.",
        "authority": "EDL(서버) 하나. 폴백이 조각맵을 제2의 권위로 만들었다.",
        "user_decision_overwritten": True,
        "probes": {
            "폴백(수리후)": ("line", "ccut_frontend/src/pages/Index.tsx", r"부활 금지"),
            "실패 표시": ("line", "ccut_frontend/src/pages/Index.tsx", r"setLedgerEdlStatus\(\"error\"\)"),
        },
    },
    {
        "id": "ui_restore_to_edit_state",
        "from": "edit", "to": "edit",
        "label": "대사 편집 UI → /edit-state 저장",
        "found": "전부 복원이 저장되지 않음 (2026-07-31)",
        "kind": "조건 분기가 전송을 생략",
        "status": "fixed",
        "fixed_by": "2ae61acf",
        "order": "서버에 이미 제외가 있으면 '빈 배열'도 뜻이 있는 값이다 — 생략하면 이전 상태가 살아남는다.",
        "authority": "fragment_edit_state(DB) 하나. UI 는 그 위의 표시다.",
        "user_decision_overwritten": True,
        "probes": {
            "가드(수리후)": ("line", "ccut_frontend/src/pages/LedgerPage.tsx", r"serverHasExcluded"),
            "같은 가드(조각맵)": ("line", "ccut_frontend/src/components/FragmentMap.tsx", r"serverHasExcluded"),
        },
    },
    {
        "id": "edit_state_lookup_symmetry",
        "from": "edit", "to": "render",
        "label": "편집상태 조회 — 프론트 ↔ 백엔드",
        "found": "FID 재발급 시 편집 소실 (2026-07-31)",
        "kind": "비대칭",
        "status": "fixed",
        "fixed_by": "80b659f1",
        "order": "id 매칭 -> 실패 시 앵커 좌표 매칭. 이 2단이 양쪽에 똑같이 있어야 한다.",
        "authority": "fragment_edit_state 하나. 다만 '어떻게 찾는가'가 양쪽에서 달랐다.",
        "user_decision_overwritten": True,
        # 준자동 — 같은 계열 두 자리를 나란히 떠서 대조한다
        "symmetry": [
            ("프론트 좌표매칭", "ccut_frontend/src/utils/fragmentTiles.ts", r"Math\.abs\(s\.anchor_start_ms"),
            ("백엔드 좌표매칭", "ccut_backend/ledger_r0.py", r"i = rematch_anchor\(|rematch_anchor\($"),
        ],
        "probes": {
            "백엔드(수리후)": ("line", "ccut_backend/ledger_r0.py", r"ANCHOR-REMATCH"),
            "허용오차(계약)": ("line", "ccut_backend/edit_contract/edit_state.py", r"def rematch_anchor\("),
        },
    },
    {
        "id": "fade_preview_vs_export",
        "from": "render", "to": "export",
        "label": "오디오 페이드 — Preview ↔ Export",
        "found": "8ms / 30ms 불일치 (2026-07-31)",
        "kind": "상수 불일치",
        "status": "fixed",
        "fixed_by": "30aeec7b",
        "order": "게이트 판정이 먼저, 길이 결정이 그 뒤. Preview 는 게이트를 아예 보지 않았다.",
        "authority": "render_engine._audio_fade_spec 하나 (게이트 ON 이면 config).",
        "user_decision_overwritten": False,
        # 자동 — 두 상수를 나란히 뜬다. 다시 갈라지면 화면에서 바로 보인다.
        "constants": [
            ("Export 기본", "py_const", "ccut_backend/engine/render_engine.py", "AUDIO_SPLICE_FADE_SEC"),
            ("Preview 기본", "py_const", "ccut_backend/engine/proposal_preview_engine.py", "AUDIO_SPLICE_FADE_SEC"),
            ("게이트 ON 값(in)", "json", "ccut_backend/config/editing_techniques.json", "audio_fade_30ms", "fade_in_ms"),
            ("게이트 ON 값(out)", "json", "ccut_backend/config/editing_techniques.json", "audio_fade_30ms", "fade_out_ms"),
        ],
        "probes": {
            "Preview 진실원(수리후)": ("line", "ccut_backend/engine/proposal_preview_engine.py", r"from engine\.render_engine import _audio_fade_spec"),
        },
    },
]


def _run_probe(spec) -> Dict[str, Any]:
    kind = spec[0]
    if kind == "line":
        return probe_line(spec[1], spec[2])
    if kind == "py_const":
        return probe_py_constant(spec[1], spec[2])
    if kind == "json":
        return probe_json_field(spec[1], spec[2], spec[3])
    return {"value": UNEXTRACTED, "why": f"알 수 없는 추출기: {kind}"}


def _ledger_slice(boundary_id: str, domain_hint: str = "rough_cut") -> Dict[str, Any]:
    """아래 절반 — failure_ledger 참조. 새 계산식을 만들지 않는다(COUNT/MIN/MAX 뿐).

    원장이 비어 있으면 UNKNOWN 이다. 0 으로 채우지 않는다 — '실패가 없었다'와
    '아직 아무것도 적히지 않았다'는 다른 사실이다.
    """
    import failure_ledger as fl
    try:
        con = fl.connect()
    except Exception as exc:
        return {"read": "UNKNOWN", "error": str(exc)}
    try:
        try:
            row = con.execute(
                f"SELECT COUNT(*) n, MIN(created_at) first, MAX(created_at) last "
                f"FROM {fl.TABLE} WHERE domain=?", (domain_hint,)).fetchone()
        except sqlite3.OperationalError as exc:
            return {"read": "UNKNOWN", "error": f"원장 없음: {exc}"}
        n = row["n"] or 0
        if n == 0:
            return {
                "read": "OK", "domain": domain_hint,
                "failure_count": "UNKNOWN", "first_occurrence": "UNKNOWN",
                "latest": "UNKNOWN", "codes": "UNKNOWN", "phases": "UNKNOWN",
                "note": "원장에 아직 행이 없다 — 실패가 없었다는 뜻이 아니다",
            }
        codes = {r["error_code"]: r["n"] for r in con.execute(
            f"SELECT error_code, COUNT(*) n FROM {fl.TABLE} WHERE domain=? GROUP BY error_code", (domain_hint,))}
        phases = {str(r["phase"]): r["n"] for r in con.execute(
            f"SELECT phase, COUNT(*) n FROM {fl.TABLE} WHERE domain=? GROUP BY phase", (domain_hint,))}
        attempts = {str(r["attempt"]): r["n"] for r in con.execute(
            f"SELECT attempt, COUNT(*) n FROM {fl.TABLE} WHERE domain=? GROUP BY attempt", (domain_hint,))}
        return {
            "read": "OK", "domain": domain_hint,
            "failure_count": n, "first_occurrence": row["first"], "latest": row["last"],
            "codes": codes, "phases": phases, "attempts": attempts,
        }
    finally:
        con.close()


@router.get("/boundaries")
async def anatomy_boundaries():
    """경계 카드 데이터. 위 절반은 지금 소스에서 뜬 것, 아래 절반은 원장 참조."""
    out = []
    for b in BOUNDARIES:
        card = {
            "id": b["id"], "from": b["from"], "to": b["to"], "label": b["label"],
            "kind": b["kind"], "found": b["found"], "status": b["status"],
            "fixed_by": b.get("fixed_by") or "UNKNOWN",
            "user_decision_overwritten": b.get("user_decision_overwritten", False),
            "static": {
                # 수동 기장 (자동 불가 — 감사로 알아낸 사실)
                "order": b.get("order") or "UNKNOWN",
                "authority": b.get("authority") or "UNKNOWN",
                "source": "수동 기장 (감사 결과)",
            },
            "extracted": {k: _run_probe(v) for k, v in (b.get("probes") or {}).items()},
            "ledger": _ledger_slice(b["id"]),
        }
        if b.get("constants"):
            card["constants"] = [
                {"label": c[0], **_run_probe(tuple(c[1:]))} for c in b["constants"]
            ]
        if b.get("symmetry"):
            card["asymmetry"] = [
                {"side": s[0], **probe_line(s[1], s[2])} for s in b["symmetry"]
            ]
        out.append(card)
    return {
        "status": "OK",
        "gate": {
            "enabled": os.getenv("CCUT_ADMIN_ANATOMY", "OFF").upper() == "ON",
            "value": os.getenv("CCUT_ADMIN_ANATOMY", "OFF"),
        },
        "boundary_count": len(out),
        "boundaries": out,
        "note": "노드가 아니라 노드 사이. 정적 절반은 요청 시점 소스에서 직접 읽는다(캐시 없음).",
    }
