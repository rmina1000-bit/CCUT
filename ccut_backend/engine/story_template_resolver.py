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
