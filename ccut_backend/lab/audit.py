import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
CONFIG_DIR = BACKEND_DIR / "config"
DB_PATH = BACKEND_DIR / "ccut_app.db"
AUDIT_CONFIG = CONFIG_DIR / "lab_audit.json"
CANDIDATES_CONFIG = CONFIG_DIR / "lab_candidates.json"
_CACHE = None


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _source_files(extensions):
    blocked = {
        "node_modules", ".git", "dist", "build", "scratch", "__pycache__",
        "test", "tests",
    }
    for root in (BACKEND_DIR, REPO_DIR / "ccut_frontend" / "src"):
        for path in root.rglob("*"):
            if (
                path.suffix not in extensions
                or any(part in blocked for part in path.parts)
                or path.name.startswith(("test_", "perception_test"))
            ):
                continue
            yield path


def _code_reference_count(terms, extensions, configured_paths=None):
    hits = set()
    paths = (
        [REPO_DIR / item for item in configured_paths]
        if configured_paths is not None
        else _source_files(extensions)
    )
    for path in paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith(("#", "//", "/*", "*")):
                continue
            if any(term in raw for term in terms):
                hits.add(f"{path.relative_to(REPO_DIR).as_posix()}:{line_no}")
    return sorted(hits)


def _material_count(con, material):
    table = material["table"]
    column = material["column"]
    total = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    json_path = material.get("json_path")
    if json_path:
        query = (
            f'SELECT COUNT(*), COUNT(DISTINCT json_extract("{column}", ?)) '
            f'FROM "{table}" WHERE json_valid("{column}") '
            f'AND json_extract("{column}", ?) IS NOT NULL'
        )
        non_null, distinct = con.execute(query, (json_path, json_path)).fetchone()
    else:
        query = (
            f'SELECT COUNT("{column}"), COUNT(DISTINCT "{column}") '
            f'FROM "{table}"'
        )
        non_null, distinct = con.execute(query).fetchone()
    return total, non_null, distinct


def _registered_rules():
    from engine.story_template_resolver import registered_rule_ids

    # proposal_axis owns five production registrations and performs them at import.
    import story_gate.proposal_axis  # noqa: F401

    return set(registered_rule_ids())


def _technique_is_wired(paths):
    return all((REPO_DIR / item).is_file() for item in paths)


def _line_evidence(relative_path, needle, occurrence=1):
    path = REPO_DIR / relative_path
    if not path.is_file():
        return None
    try:
        found = 0
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if needle in raw:
                found += 1
                if found == occurrence:
                    return f"{relative_path}:{line_no}"
    except (OSError, UnicodeDecodeError):
        return None
    return None


def _edge_status(material, target_live):
    if material["non_null"] == 0:
        return "LOCKED"
    return "LIVE" if target_live else "BROKEN"


def build_lab_context(audit):
    missing = [
        item["label"] for item in audit["materials"]
        if item["non_null"] == 0
    ]
    return {
        "screen": "편집연구실",
        "재료": f"값 있음 {len(audit['materials']) - len(missing)} / 값 없음 {len(missing)}",
        "값없는_재료": missing,
        "하드룰": (
            f"선언 {audit['rules']['declared']} / 등록 {audit['rules']['registered']} / "
            f"미등록 {audit['rules']['unregistered']}"
        ),
        "기법": (
            f"선언 {audit['techniques']['declared']} / "
            f"배선 {audit['techniques']['wired']}"
        ),
        "마지막_측정": audit["audited_at"],
    }


def run_audit():
    global _CACHE
    started = time.perf_counter()
    config = _load_json(AUDIT_CONFIG)
    candidate_ledger = _load_json(CANDIDATES_CONFIG)
    extensions = set(config.get("source_extensions") or [".py", ".ts", ".tsx"])

    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    materials = []
    try:
        for item in config["materials"]:
            total, non_null, distinct = _material_count(con, item)
            consumers = _code_reference_count(
                item["consumer_terms"], extensions, item.get("consumer_paths")
            )
            producers = _code_reference_count(
                item["producer_terms"], extensions, item.get("producer_paths")
            )
            materials.append({
                "id": item["id"],
                "label": item["label"],
                "total": total,
                "non_null": non_null,
                "distinct": distinct,
                "consumer_count": len({hit.rsplit(":", 1)[0] for hit in consumers}),
                "producer_count": len({hit.rsplit(":", 1)[0] for hit in producers}),
                "consumers": consumers,
                "producers": producers,
            })
    finally:
        con.close()

    declared_rules = {
        item["rule_id"] for item in _load_json(CONFIG_DIR / "production_hard_rules.json")["rules"]
    }
    registered_rules = sorted(_registered_rules())
    registered_count = min(len(declared_rules), len(registered_rules))

    techniques = _load_json(CONFIG_DIR / "editing_techniques.json")["techniques"]
    declared_techniques = {item["technique_id"] for item in techniques}
    wired = sorted(
        technique for technique, paths in config["wired_techniques"].items()
        if technique in declared_techniques or technique == "as_is"
        if _technique_is_wired(paths)
    )
    material_by_id = {item["id"]: item for item in materials}
    wired_set = set(wired)

    declared_rule_rows = _load_json(CONFIG_DIR / "production_hard_rules.json")["rules"]
    rule_items = []
    for item in declared_rule_rows:
        rule_id = item["rule_id"]
        rule_items.append({
            "id": rule_id,
            "declared_in": _line_evidence(
                "ccut_backend/config/production_hard_rules.json",
                f'"rule_id": "{rule_id}"',
            ),
            "registered": rule_id in registered_rules,
            "checks_materials": "UNDECLARED",
            "evidence": "ccut_backend/config/production_hard_rules.json:rules",
        })

    registered_rule_sources = {
        "RULE_EDIT_STATE_NO_SHADOW": "ccut_backend/engine/story_template_resolver.py",
        "RULE_TECHNIQUE_PATH_UNIFORM": "ccut_backend/story_gate/proposal_axis.py",
        "RULE_PUNCH_ZOOM_BOUND": "ccut_backend/story_gate/proposal_axis.py",
        "RULE_BOUNDARY_PATH_UNIFORM": "ccut_backend/story_gate/proposal_axis.py",
        "RULE_NO_MID_WORD_CUT": "ccut_backend/story_gate/proposal_axis.py",
        "RULE_WORD_BOUNDARY_SNAP": "ccut_backend/story_gate/proposal_axis.py",
    }
    registered_material_checks = {
        "RULE_NO_MID_WORD_CUT": ["word_timestamps"],
        "RULE_WORD_BOUNDARY_SNAP": ["word_timestamps"],
    }
    registered_material_evidence = {
        "RULE_NO_MID_WORD_CUT": _line_evidence(
            "ccut_backend/story_gate/proposal_axis.py",
            "words = _fragment_words",
            1,
        ),
        "RULE_WORD_BOUNDARY_SNAP": _line_evidence(
            "ccut_backend/story_gate/proposal_axis.py",
            "words = _fragment_words",
            2,
        ),
    }
    for rule_id in registered_rules:
        if rule_id in declared_rules:
            continue
        source = registered_rule_sources.get(rule_id)
        evidence = (
            _line_evidence(source, f'register_rule_check("{rule_id}"')
            if source else None
        )
        rule_items.append({
            "id": rule_id,
            "declared_in": evidence,
            "registered": True,
            "checks_materials": registered_material_checks.get(rule_id, "UNDECLARED"),
            "evidence": registered_material_evidence.get(rule_id, evidence),
        })

    technique_items = []
    referenced_technique_rules = {
        "punch_in": [
            "RULE_PUNCH_ZOOM_BOUND",
            "RULE_TECHNIQUE_PATH_UNIFORM",
        ],
    }
    for item in techniques:
        technique_id = item["technique_id"]
        required_materials = [
            signal for signal in item.get("required_signals", [])
            if signal in material_by_id
        ]
        technique_items.append({
            "id": technique_id,
            "wired": technique_id in wired_set,
            "declared_in": _line_evidence(
                "ccut_backend/config/editing_techniques.json",
                f'"technique_id": "{technique_id}"',
            ),
            "requires_materials": required_materials or "UNDECLARED",
            "requires_rules": referenced_technique_rules.get(
                technique_id, "UNDECLARED"
            ),
            "failure_check": item.get("failure_check"),
        })
    technique_items.append({
        "id": "as_is",
        "wired": "as_is" in wired_set,
        "declared_in": _line_evidence(
            "ccut_backend/story_gate/proposal_axis.py",
            'TECHNIQUE_AS_IS = "as_is"',
        ),
        "requires_materials": "UNDECLARED",
        "requires_rules": "UNDECLARED",
        "failure_check": None,
    })

    edges = []
    for technique in technique_items:
        required_materials = technique["requires_materials"]
        if required_materials == "UNDECLARED":
            continue
        for material_id in required_materials:
            material = material_by_id[material_id]
            edges.append({
                "from": material_id,
                "to": technique["id"],
                "kind": "material→technique",
                "status": _edge_status(material, technique["wired"]),
                "evidence": (
                    f"{technique['declared_in']} required_signals:{material_id}"
                ),
            })

    for rule in rule_items:
        checks = rule["checks_materials"]
        if checks == "UNDECLARED":
            continue
        for material_id in checks:
            material = material_by_id[material_id]
            edges.append({
                "from": material_id,
                "to": rule["id"],
                "kind": "material→rule",
                "status": _edge_status(material, rule["registered"]),
                "evidence": rule["evidence"],
            })

    rule_technique_refs = [
        (
            "RULE_PUNCH_ZOOM_BOUND",
            "punch_in",
            _line_evidence(
                "ccut_backend/story_gate/proposal_axis.py",
                'VETO_RULE_IDS = ("RULE_PUNCH_ZOOM_BOUND"',
            ),
        ),
        (
            "RULE_TECHNIQUE_PATH_UNIFORM",
            "punch_in",
            _line_evidence(
                "ccut_backend/story_gate/proposal_axis.py",
                'VETO_RULE_IDS = ("RULE_PUNCH_ZOOM_BOUND"',
            ),
        ),
    ]
    registered_set = set(registered_rules)
    for rule_id, technique_id, evidence in rule_technique_refs:
        edges.append({
            "from": rule_id,
            "to": technique_id,
            "kind": "rule→technique",
            "status": (
                "LIVE"
                if rule_id in registered_set and technique_id in wired_set
                else "BROKEN"
            ),
            "evidence": evidence,
        })

    audited_at = datetime.now().astimezone().isoformat(timespec="seconds")
    result = {
        "audited_at": audited_at,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "materials": materials,
        "rules": {
            "declared": len(declared_rules),
            "registered": registered_count,
            "unregistered": max(0, len(declared_rules) - registered_count),
            "registered_ids": registered_rules,
            "items": rule_items,
        },
        "techniques": {
            "declared": len(declared_techniques),
            "wired": len(wired),
            "wired_ids": wired,
            "items": technique_items,
        },
        "edges": edges,
        "candidates": candidate_ledger["candidates"],
        "emotion_evidence": {
            "legacy_node": {
                "id": "emotion_score",
                "status": "재설계",
            },
            "items": [
                {"id": "facial_expression_delta", "status": "UNKNOWN"},
                {"id": "prosody_delta", "status": "VALUE"},
                {"id": "laughter_event", "status": "UNKNOWN"},
                {"id": "speech_presence", "status": "UNKNOWN"},
                {"id": "acoustic_event", "status": "UNKNOWN"},
            ],
            "aggregation": "금지",
        },
    }
    result["ai_context"] = build_lab_context(result)
    _CACHE = result
    return result


def get_audit():
    return _CACHE or run_audit()
