import json
import os
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
#  [RULE-1] 하드룰 집행기 — 적재만 하고 집행하지 않던 구조를 끊는다.
#    실측(RULE-1 R1): production_hard_rules.json 12개는 로드되어 id 목록만 통과했고
#    ccut_enforcement_point 를 역참조하는 코드가 없어 집행 0/12였다.
#    여기서 rule_id ↔ 검사 함수를 잇고, 위반이면 그 기법을 적용하지 않는다(Veto).
# ══════════════════════════════════════════════════════════════════════════
VERDICT_PASS = "PASS"
VERDICT_VIOLATION = "VIOLATION"
VERDICT_NA = "NOT_APPLICABLE"
VERDICT_UNKNOWN = "UNKNOWN"

_RULE_CHECKS = {}


def register_rule_check(rule_id: str, fn):
    """rule_id 별 검사 함수 등록. fn(context) -> {verdict, measured, threshold, detail}"""
    _RULE_CHECKS[rule_id] = fn
    return fn


def registered_rule_ids():
    return sorted(_RULE_CHECKS)


def check_rules(context: Dict[str, Any], rule_ids=None):
    """규칙 검사. 신호가 없어 검사 못 한 것은 PASS가 아니라 UNKNOWN이다.

    조용한 통과 금지 — 판정·실측값·임계값을 전부 raw 로그로 남긴다.
    """
    out = []
    for rid in (rule_ids or sorted(_RULE_CHECKS)):
        fn = _RULE_CHECKS.get(rid)
        if fn is None:
            r = {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": None,
                 "detail": "검사 함수 미등록 — 적재만 됨"}
        else:
            try:
                r = fn(context) or {}
            except Exception as e:
                r = {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": None,
                     "detail": f"검사 실패: {e}"}
        r.setdefault("verdict", VERDICT_UNKNOWN)
        r["rule_id"] = rid
        out.append(r)
        print(f"[RULE][{rid}] {r['verdict']} measured={r.get('measured')} "
              f"threshold={r.get('threshold')} {r.get('detail') or ''}")
    return out


def has_veto(results) -> bool:
    """required 규칙 위반이 하나라도 있으면 기법을 적용하지 않는다."""
    return any(r.get("verdict") == VERDICT_VIOLATION for r in results)


def _check_edit_state_no_shadow(ctx):
    """[RESTORE-1 S4] RULE_EDIT_STATE_NO_SHADOW — 빈 행이 편집 행을 가리고 있는가.

    실사고(2026-07-26 06:31): timeline_item_id 에서 제안식별자(_B_)를 떼는 이관이
    한 조각에만 실행되면서, 같은 조각에 rev=1·excluded=[] 인 새 행이 생겼다.
    선택식이 '선호 item id 우선'이라 그 빈 행이 rev=13 편집 행을 가렸고,
    사용자가 지운 6.46초가 재생·미리보기·export 어디에도 반영되지 않았다.
    이 규칙은 그 형상을 데이터에서 직접 찾는다 — 로그 전용(Veto 없음, 데이터 문제다).
    """
    import json as _json
    import os as _os
    import sqlite3 as _sq
    prog = ctx.get("program_id")
    db = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "ccut_app.db")
    try:
        con = _sq.connect("file:" + db + "?mode=ro", uri=True)
        con.row_factory = _sq.Row
    except Exception as e:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": "no shadowing row",
                "detail": f"DB 열기 실패: {e}"}
    try:
        q = "SELECT rowid,* FROM fragment_edit_state"
        args = ()
        if prog:
            q += " WHERE program_id=?"
            args = (prog,)
        rows = con.execute(q, args).fetchall()
    except _sq.OperationalError as e:
        con.close()
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": "no shadowing row",
                "detail": f"테이블 없음: {e}"}
    finally:
        try:
            con.close()
        except Exception:
            pass
    if not rows:
        return {"verdict": VERDICT_NA, "measured": {"rows": 0}, "threshold": "no shadowing row",
                "detail": "편집 상태 행 없음"}

    def _empty(r):
        try:
            return _json.loads(r["excluded_ranges_json"] or "[]") == []
        except Exception:
            return False

    groups = {}
    for r in rows:
        groups.setdefault((r["program_id"], r["parent_fragment_id"]), []).append(r)
    shadows = []
    for (pg, fid), rs in groups.items():
        if len(rs) < 2:
            continue
        # 선택식(프론트·ledger 공통): 선호 item id = ITEM_{hash6(program)}_{fid}_0
        h = 5381
        for ch in pg or "":
            h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
        want = "ITEM_%s_%s_0" % (format(h, "x").rjust(6, "0")[-6:], fid)
        chosen = next((r for r in rs if r["timeline_item_id"] == want), rs[0])
        hidden = [r for r in rs if r["rowid"] != chosen["rowid"] and not _empty(r)]
        if _empty(chosen) and hidden:
            shadows.append({
                "program_id": pg, "parent_fragment_id": fid,
                "chosen": {"rowid": chosen["rowid"], "item": chosen["timeline_item_id"],
                           "rev": chosen["revision"], "excluded": chosen["excluded_ranges_json"]},
                "hidden": [{"rowid": r["rowid"], "item": r["timeline_item_id"], "rev": r["revision"],
                            "excluded": r["excluded_ranges_json"]} for r in hidden],
            })
    return {"verdict": VERDICT_PASS if not shadows else VERDICT_VIOLATION,
            "measured": {"groups": len(groups), "rows": len(rows), "shadowed": shadows},
            "threshold": "선택된 행이 비어 있고 가려진 행이 편집을 보유하면 VIOLATION",
            "detail": "가려진 편집 없음" if not shadows
                      else "빈 행이 편집 행을 가리는 중 — 사용자 편집이 산출물에 반영되지 않는다"}


register_rule_check("RULE_EDIT_STATE_NO_SHADOW", _check_edit_state_no_shadow)


class StoryTemplateResolver:
    """Resolves User Intent into specific Story Templates and Editing Techniques."""

    def __init__(self, config_dir: str = "ccut_backend/config"):
        self.config_dir = config_dir
        self.templates: List[Dict[str, Any]] = []
        self.techniques: Dict[str, Dict[str, Any]] = {}
        self.hard_rules: Dict[str, Dict[str, Any]] = {}
        self._load_configs()

    def _load_configs(self):
        """Loads JSON configurations from the config directory."""
        template_path = os.path.join(self.config_dir, "story_direction_templates.json")
        technique_path = os.path.join(self.config_dir, "editing_techniques.json")
        rules_path = os.path.join(self.config_dir, "production_hard_rules.json")

        try:
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    self.templates = json.load(f).get("templates", [])
            
            if os.path.exists(technique_path):
                with open(technique_path, "r", encoding="utf-8") as f:
                    tech_data = json.load(f).get("techniques", [])
                    self.techniques = {t["technique_id"]: t for t in tech_data}

            if os.path.exists(rules_path):
                with open(rules_path, "r", encoding="utf-8") as f:
                    rules_data = json.load(f).get("rules", [])
                    self.hard_rules = {r["rule_id"]: r for r in rules_data}
            
            logger.info(f"Loaded {len(self.templates)} templates, {len(self.techniques)} techniques, {len(self.hard_rules)} rules.")
        except Exception as e:
            logger.error(f"Failed to load story template configs: {e}")

    def resolve_story_template(self, user_intent: Optional[Dict[str, Any]] = None, template_id: Optional[str] = None) -> Dict[str, Any]:
        """Matches user intent or a specific ID to a template and its bound techniques."""
        selected_template = None

        # 1. Direct ID match
        if template_id:
            for t in self.templates:
                if t["template_id"] == template_id:
                    selected_template = t
                    break
        
        # 2. Intent-based match
        if not selected_template and user_intent:
            selected_template = self._match_template_by_intent(user_intent)
        
        # 3. Fallback to safe_default
        if not selected_template:
            for t in self.templates:
                if t["template_id"] == "safe_default":
                    selected_template = t
                    break
        
        # 4. Final fallback (first available)
        if not selected_template and self.templates:
            selected_template = self.templates[0]
        
        if not selected_template:
            return {}

        return self._build_resolved_context(selected_template)

    def _match_template_by_intent(self, user_intent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Heuristic matching of intent fields to template definitions."""
        best_match = None
        max_score = -1

        for t in self.templates:
            match_def = t.get("story_intent_match", {})
            if not match_def:
                continue
            
            score = 0
            for key, val in match_def.items():
                if user_intent.get(key) == val:
                    score += 1
            
            if score > max_score and score > 0:
                max_score = score
                best_match = t
        
        return best_match

    def _build_resolved_context(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Bundles the template with its resolved technique and rule metadata."""
        return {
            "template_id": template["template_id"],
            "display_name": template["display_name"],
            "editing_technique_ids": template.get("editing_technique_packs", []),
            "production_hard_rule_ids": template.get("production_hard_rules", []),
            "hard_constraints": template.get("hard_constraints", {}),
            "soft_scoring": template.get("soft_scoring", {}),
            "qa_checks": template.get("qa_checks", [])
        }
