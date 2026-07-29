import json
import hashlib
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
CONFIG_DIR = BACKEND_DIR / "config"
DB_PATH = BACKEND_DIR / "ccut_app.db"
AUDIT_CONFIG = CONFIG_DIR / "lab_audit.json"
CANDIDATES_CONFIG = CONFIG_DIR / "lab_candidates.json"
SENSOR_CONTRACT_CONFIG = CONFIG_DIR / "sensor_contract.json"
GOLDENSET_CONFIG = CONFIG_DIR / "lab_goldenset.json"


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_head_candidate_ledger():
    relative_path = CANDIDATES_CONFIG.relative_to(REPO_DIR).as_posix()
    completed = subprocess.run(
        ["git", "show", f"HEAD:{relative_path}"],
        cwd=REPO_DIR,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def _validate_candidate_history_append_only(candidate_ledger, baseline=None):
    baseline = baseline or _load_head_candidate_ledger()
    current_by_id = {
        item["candidate_id"]: item for item in candidate_ledger["candidates"]
    }
    for previous in baseline["candidates"]:
        candidate_id = previous["candidate_id"]
        current = current_by_id.get(candidate_id)
        if current is None:
            raise ValueError(
                f"candidate measurement history rejected: {candidate_id} was deleted"
            )
        previous_history = previous.get("측정이력", [])
        current_history = current.get("측정이력", [])
        if len(current_history) < len(previous_history):
            raise ValueError(
                f"candidate measurement history rejected: {candidate_id} entries were deleted"
            )
        for index, previous_entry in enumerate(previous_history):
            if current_history[index] != previous_entry:
                raise ValueError(
                    "candidate measurement history rejected: "
                    f"{candidate_id} entry {index} was modified or reordered"
                )
    return {
        "status": "APPEND_ONLY",
        "baseline": "git_HEAD",
        "checked_candidates": len(baseline["candidates"]),
    }


def _load_sensor_contract():
    contract = _load_json(SENSOR_CONTRACT_CONFIG)
    required = {
        "sensor", "version", "fragment_id", "span",
        "values", "confidence", "unknown_reason",
    }
    declared = set(contract.get("record", {}).get("required", []))
    missing = sorted(required - declared)
    if missing:
        raise ValueError(
            f"sensor contract missing required fields: {', '.join(missing)}"
        )
    return contract


def resolve_golden_key(con, golden_key):
    canonical = (
        f"{golden_key['source_id']}:{golden_key['start_ms']}:"
        f"{golden_key['end_ms']}"
    )
    span_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()
    if span_hash != golden_key["span_hash"]:
        return {
            "status": "UNKNOWN",
            "fragment_id": None,
            "unknown_reason": "SPAN_HASH_MISMATCH",
        }

    rows = con.execute(
        'SELECT fragment_id, start, "end" FROM semantic_fragments '
        "WHERE source_id=? AND ROUND(\"end\" * 1000) > ? "
        "AND ROUND(start * 1000) < ? ORDER BY start",
        (
            golden_key["source_id"],
            golden_key["start_ms"],
            golden_key["end_ms"],
        ),
    ).fetchall()
    candidates = []
    for fragment_id, start, end in rows:
        start_ms = round(float(start) * 1000)
        end_ms = round(float(end) * 1000)
        overlap_ms = max(
            0,
            min(end_ms, golden_key["end_ms"])
            - max(start_ms, golden_key["start_ms"]),
        )
        candidates.append({
            "fragment_id": fragment_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "overlap_ms": overlap_ms,
        })

    exact = [
        item for item in candidates
        if item["start_ms"] == golden_key["start_ms"]
        and item["end_ms"] == golden_key["end_ms"]
    ]
    if len(exact) == 1:
        return {
            "status": "RESOLVED",
            "fragment_id": exact[0]["fragment_id"],
            "strategy": "EXACT_SPAN",
            "current_span": {
                "start_ms": exact[0]["start_ms"],
                "end_ms": exact[0]["end_ms"],
            },
        }
    if not candidates:
        return {
            "status": "UNKNOWN",
            "fragment_id": None,
            "unknown_reason": "NO_OVERLAP",
        }

    best_overlap = max(item["overlap_ms"] for item in candidates)
    best = [
        item for item in candidates if item["overlap_ms"] == best_overlap
    ]
    if len(best) != 1:
        return {
            "status": "UNKNOWN",
            "fragment_id": None,
            "unknown_reason": "AMBIGUOUS_OVERLAP",
            "candidates": candidates,
        }
    return {
        "status": "RESOLVED",
        "fragment_id": best[0]["fragment_id"],
        "strategy": "UNIQUE_MAX_OVERLAP",
        "current_span": {
            "start_ms": best[0]["start_ms"],
            "end_ms": best[0]["end_ms"],
        },
    }


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
        if material.get("numeric_only"):
            query = (
                f'SELECT COUNT(*), COUNT(DISTINCT json_extract("{column}", ?)) '
                f'FROM "{table}" WHERE json_valid("{column}") '
                f'AND json_type("{column}", ?) IN (\'integer\', \'real\')'
            )
        else:
            query = (
                f'SELECT COUNT(*), COUNT(DISTINCT json_extract("{column}", ?)) '
                f'FROM "{table}" WHERE json_valid("{column}") '
                f'AND json_extract("{column}", ?) IS NOT NULL'
            )
        non_null, distinct = con.execute(
            query, (json_path, json_path)
        ).fetchone()
    else:
        query = (
            f'SELECT COUNT("{column}"), COUNT(DISTINCT "{column}") '
            f'FROM "{table}"'
        )
        non_null, distinct = con.execute(query).fetchone()
    return total, non_null, distinct


def _value_condition(material, alias):
    """_material_count 의 '값 있음' 판정을 다른 별칭에서 그대로 재사용한다."""
    column = material["column"]
    json_path = material.get("json_path")
    if not json_path:
        return f'{alias}."{column}" IS NOT NULL', ()
    if material.get("numeric_only"):
        return (
            f'json_valid({alias}."{column}") AND '
            f"json_type({alias}.\"{column}\", ?) IN ('integer', 'real')",
            (json_path,),
        )
    return (
        f'json_valid({alias}."{column}") AND '
        f'json_extract({alias}."{column}", ?) IS NOT NULL',
        (json_path,),
    )


def _span_has_words(segments_raw, start, end):
    """proposal_axis._fragment_words 와 같은 판정 — 구간 안에 단어가 하나라도 있나.

    이중 인코딩된 segments 도 같은 방식으로 한 번 더 푼다.
    """
    if not segments_raw:
        return False
    try:
        segments = json.loads(segments_raw)
        if isinstance(segments, str):
            segments = json.loads(segments)
    except (TypeError, ValueError):
        return False
    if not isinstance(segments, list):
        return False
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words") or []:
            if not isinstance(word, dict):
                continue
            if word.get("start") is None or word.get("end") is None:
                continue
            if float(word["end"]) > start and float(word["start"]) < end:
                return True
    return False


def _json_list(raw, key):
    try:
        return (json.loads(raw or "{}") or {}).get(key) or []
    except (TypeError, ValueError):
        return []


def _consumed_count(con, material, probe):
    """기법·룰이 실제로 읽는 단위(조각)로 재료 보유량을 다시 센다.

    저장 행 수를 그대로 보이면 분모가 과장된다. 예: word_timestamps 는
    subtitles 77행 기준으로 77/77 이지만, 소비자는 조각마다 자기 구간의 단어를
    찾으므로 실제로는 670 조각 중 일부만 값을 가진다.

    method 는 선언이 아니라 실제 소비 코드 경로를 그대로 흉내낸다.
    """
    method = material["consumption"]["method"]
    table = material["table"]
    if method == "fragment_id_join":
        condition, params = _value_condition(material, "t")
        return con.execute(
            "SELECT COUNT(*) FROM semantic_fragments f "
            f'JOIN "{table}" t ON t.fragment_id = f.fragment_id '
            f"WHERE {condition}",
            params,
        ).fetchone()[0]
    if method == "temporal_overlap":
        condition, params = _value_condition(material, "e")
        return con.execute(
            "SELECT COUNT(*) FROM semantic_fragments f WHERE EXISTS ("
            f'SELECT 1 FROM "{table}" e WHERE e.source_id = f.source_id '
            'AND e."end" > f.start AND e.start < f."end" '
            f"AND {condition})",
            params,
        ).fetchone()[0]
    if method == "evidence_refs_in_span":
        # 소비자는 source_id 시간 겹침이 아니라 semantic_json.evidence_refs 로
        # evidence_board 행을 지목한 뒤, 구간 안에 든 beat 만 쓴다.
        hits = 0
        for _, _, start, end, semantic_json in probe["fragments"]:
            span_start, span_end = float(start or 0), float(end or 0)
            for ref in _json_list(semantic_json, "evidence_refs"):
                beats = _json_list(probe["evidence_meta"].get(ref), "audio_beat")
                if any(span_start <= float(t) < span_end for t in beats):
                    hits += 1
                    break
        return hits
    if method == "subtitle_word_overlap":
        return sum(
            1 for _, source_id, start, end, _ in probe["fragments"]
            if _span_has_words(
                probe["subtitle_segments"].get(source_id),
                float(start or 0),
                float(end or 0),
            )
        )
    raise ValueError(f"unknown consumption method: {method}")


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


# [LAB-15] '집행'은 성격이 다른 둘을 뭉갠 말이었다. 갈라서 센다.
#   CORRECTIVE = 값을 실제로 보정한다 (경계를 움직인다)
#   VETO       = 위반 판정으로 기법 적용을 차단한다
# 한 룰이 둘 다일 수 있고, 선언만 되고 도달하지 못하는 veto 도 있다.
RULE_ACTIONS = {
    "RULE_PUNCH_ZOOM_BOUND": {
        "veto": "ccut_backend/story_gate/proposal_axis.py:621-627",
    },
    "RULE_TECHNIQUE_PATH_UNIFORM": {
        "veto": "ccut_backend/story_gate/proposal_axis.py:621-627",
    },
    "RULE_WORD_BOUNDARY_SNAP": {
        "corrective": "ccut_backend/story_gate/proposal_axis.py:322-323",
        "corrective_entry": "ccut_backend/main.py:2593",
        "corrective_gate": "CCUT_TECHNIQUE_WORD_SNAP",
        "veto_unreachable": {
            "declared_in": "ccut_backend/story_gate/proposal_axis.py:491-492",
            "reason": (
                "punch_rule_results ctx 에 program_id 가 없어 이 룰은 항상 "
                "UNKNOWN 을 반환한다. has_veto 는 VIOLATION 만 보므로 차단이 서지 않는다."
            ),
            "evidence": "ccut_backend/story_gate/proposal_axis.py:596-598",
        },
    },
}

# 등록됐지만 아무 동작도 하지 않는 룰의 사유. 선언만 된 12개는 아래 기본 사유를 쓴다.
RULE_NO_ACTION_REASON = {
    "RULE_BOUNDARY_PATH_UNIFORM":
        "boundary_rule_results 로그 전용 — ccut_backend/story_gate/proposal_axis.py:601-606",
    "RULE_NO_MID_WORD_CUT":
        "boundary_rule_results 로그 전용 — ccut_backend/story_gate/proposal_axis.py:601-606",
    "RULE_EDIT_STATE_NO_SHADOW":
        "등록만 · check_rules 호출자 없음 — ccut_backend/engine/story_template_resolver.py:137",
}
DECLARED_NO_ACTION_REASON = (
    "검사 함수 미등록 — ccut_enforcement_point 를 역참조하는 코드가 없다"
)


def _gate_state(env_name):
    """게이트가 실제로 켜져 있는가. 코드가 있어도 게이트가 꺼져 있으면 동작하지 않는다."""
    if not env_name:
        return None
    raw = os.getenv(env_name, "")
    return {
        "env": env_name,
        "value": raw or None,
        "on": raw.strip().upper() in ("1", "ON", "TRUE", "YES"),
    }


def _rule_action_view(rule_id, registered):
    """룰 하나를 NONE / CORRECTIVE / VETO 로 재판정한다. 복수 허용."""
    spec = RULE_ACTIONS.get(rule_id, {}) if registered else {}
    actions = []
    if spec.get("corrective"):
        actions.append("CORRECTIVE")
    if spec.get("veto"):
        actions.append("VETO")
    gate = _gate_state(spec.get("corrective_gate"))
    return {
        "actions": actions or ["NONE"],
        "corrective_evidence": spec.get("corrective"),
        "corrective_entry": spec.get("corrective_entry"),
        "corrective_gate": gate,
        "veto_evidence": spec.get("veto"),
        "veto_unreachable": spec.get("veto_unreachable"),
        "no_action_reason": (
            None if actions
            else RULE_NO_ACTION_REASON.get(rule_id)
            if registered else DECLARED_NO_ACTION_REASON
        ),
    }

REGISTERED_RULE_EVIDENCE = {
    "RULE_BOUNDARY_PATH_UNIFORM": "ccut_backend/story_gate/proposal_axis.py:315-326",
    "RULE_NO_MID_WORD_CUT": "ccut_backend/story_gate/proposal_axis.py:315-326",
    "RULE_WORD_BOUNDARY_SNAP": "ccut_backend/story_gate/proposal_axis.py:315-326",
    "RULE_EDIT_STATE_NO_SHADOW": "ccut_backend/engine/story_template_resolver.py:62-70",
}


EVIDENCE_SUFFIXES = (".py", ".ts", ".tsx", ".json", ".md")
_REF_PATTERN = re.compile(
    r"^(?P<path>[\w\-./]+\.(?:py|ts|tsx|json|md))(?::(?P<anchor>[\w\-.]+))?$"
)
_LINE_ANCHOR = re.compile(r"^\d+(?:-\d+)?$")


def _symbol_line(path, symbol):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    for pattern in (f"def {symbol}", f"class {symbol}", symbol):
        for line_no, raw in enumerate(lines, 1):
            if pattern in raw:
                return line_no
    return None


_DEFINITION = re.compile(r"^\s*(?:async\s+)?(?:def|class|function)\s+(\w+)")


def _build_definition_index():
    """심볼 → 첫 정의 위치. 못 찾은 심볼마다 트리를 다시 걷지 않도록 한 번만 만든다."""
    index = {}
    for path in _source_files({".py", ".ts", ".tsx"}):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(REPO_DIR).as_posix()
        for line_no, raw in enumerate(lines, 1):
            match = _DEFINITION.match(raw)
            if match:
                index.setdefault(match.group(1), f"{relative}:{line_no}")
    return index


def _resolve_reference(token, definitions):
    """config 에 적힌 근거 한 줄이 실재하는가.

    EXISTS / MISSING / MOVED / NOT_A_CODE_REF 넷 중 하나로 판정한다.
    선언값은 건드리지 않는다 — 판정만 따로 붙인다.
    """
    head = str(token or "").split()[0] if str(token or "").strip() else ""
    match = _REF_PATTERN.match(head)
    if not match:
        return {"declared": token, "status": "NOT_A_CODE_REF", "found_at": None}
    relative = match.group("path")
    anchor = match.group("anchor")
    path = REPO_DIR / relative
    if not path.is_file():
        return {"declared": token, "status": "MISSING", "found_at": None,
                "detail": "파일 없음"}
    if anchor is None:
        return {"declared": token, "status": "EXISTS",
                "found_at": relative, "detail": None}
    if _LINE_ANCHOR.match(anchor):
        try:
            total = len(path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            total = 0
        first = int(anchor.split("-")[0])
        if 1 <= first <= total:
            return {"declared": token, "status": "EXISTS",
                    "found_at": f"{relative}:{anchor}", "detail": None}
        return {"declared": token, "status": "MISSING", "found_at": None,
                "detail": f"파일 {total}줄 — 선언 줄번호 초과"}
    line_no = _symbol_line(path, anchor)
    if line_no:
        return {"declared": token, "status": "EXISTS",
                "found_at": f"{relative}:{line_no}", "detail": None}
    moved = definitions().get(anchor)
    if moved:
        return {"declared": token, "status": "MOVED", "found_at": moved,
                "detail": "선언 파일에는 없고 다른 파일에 있음"}
    return {"declared": token, "status": "MISSING", "found_at": None,
            "detail": "심볼을 저장소 어디에서도 찾지 못함"}


def _collect_evidence_refs(audit_config, techniques, candidate_ledger):
    """세 config 파일이 근거로 지목한 코드 참조를 전부 모은다."""
    refs = []

    def add(source, field, token):
        refs.append({"source": source, "field": field, "token": token})

    source = "config/lab_audit.json"
    for item in audit_config["materials"]:
        add(source, f"{item['id']}.projection_evidence", item["projection_evidence"])
        add(source, f"{item['id']}.consumption.evidence",
            item["consumption"]["evidence"])
        for path in item.get("producer_paths") or []:
            add(source, f"{item['id']}.producer_paths", path)
        for path in item.get("consumer_paths") or []:
            add(source, f"{item['id']}.consumer_paths", path)
    for technique, paths in audit_config["wired_techniques"].items():
        for path in paths:
            add(source, f"wired_techniques.{technique}", path)

    source = "config/editing_techniques.json"
    for item in techniques:
        relationship = item.get("relationship_source") or {}
        for token in relationship.get("derived_from") or []:
            add(source, f"{item['technique_id']}.relationship_source.derived_from",
                token)

    source = "config/lab_candidates.json"
    for record in candidate_ledger.get("ledger_records") or []:
        for token in record.get("근거") or []:
            add(source, f"{record['기록id']}.근거", token)

    cache = {}

    def definitions():
        if "index" not in cache:
            cache["index"] = _build_definition_index()
        return cache["index"]

    resolved = []
    for ref in refs:
        if ref["token"] is None:
            continue
        resolved.append({**ref, **_resolve_reference(ref["token"], definitions)})
    return resolved


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
            f"보정 {audit['rules']['corrective']} / veto {audit['rules']['veto']} / "
            f"ID 교집합 {audit['rules']['identity_overlap']}"
        ),
        "기법": (
            f"선언 {audit['techniques']['declared']} / "
            f"배선 {audit['techniques']['wired']}"
        ),
        "마지막_측정": audit["audited_at"],
    }


def run_audit():
    started = time.perf_counter()
    config = _load_json(AUDIT_CONFIG)
    candidate_ledger = _load_json(CANDIDATES_CONFIG)
    candidate_guard = _validate_candidate_history_append_only(candidate_ledger)
    sensor_contract = _load_sensor_contract()
    extensions = set(config.get("source_extensions") or [".py", ".ts", ".tsx"])

    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    materials = []
    golden_set = _load_json(GOLDENSET_CONFIG)
    golden_resolutions = []
    try:
        probe = {
            "fragments": con.execute(
                'SELECT fragment_id, source_id, start, "end", semantic_json '
                "FROM semantic_fragments"
            ).fetchall(),
            "subtitle_segments": dict(
                con.execute("SELECT source_id, segments FROM subtitles").fetchall()
            ),
            "evidence_meta": dict(
                con.execute(
                    "SELECT fragment_id, metadata_json FROM evidence_board"
                ).fetchall()
            ),
        }
        fragment_total = len(probe["fragments"])
        for item in config["materials"]:
            total, non_null, distinct = _material_count(con, item)
            consumed = _consumed_count(con, item, probe)
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
                "storage_unit": item["storage_unit"],
                "fragment_consumer_contract": item["fragment_consumer_contract"],
                "projection": item["projection"],
                "projection_evidence": item["projection_evidence"],
                "consumption": {
                    "unit": item["consumption"]["unit"],
                    "non_null": consumed,
                    "total": fragment_total,
                    "method": item["consumption"]["method"],
                    "evidence": item["consumption"]["evidence"],
                    "same_as_storage": (consumed, fragment_total)
                    == (non_null, total),
                },
            })
        for item in golden_set["goldens"]:
            golden_resolutions.append({
                "label": item["label"],
                "golden_key": item["golden_key"],
                "reference_fragment_id": item["fragment_id"],
                "resolution": resolve_golden_key(con, item["golden_key"]),
            })
    finally:
        con.close()

    declared_rules = {
        item["rule_id"] for item in _load_json(CONFIG_DIR / "production_hard_rules.json")["rules"]
    }
    registered_rules = sorted(_registered_rules())
    rule_identity_overlap = sorted(declared_rules.intersection(registered_rules))

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
            "acts": False,
            "state": "DECLARED",
            "checks_materials": "UNDECLARED",
            "evidence": "ccut_backend/config/production_hard_rules.json:rules",
            **_rule_action_view(rule_id, rule_id in registered_rules),
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
        action_view = _rule_action_view(rule_id, True)
        acts = action_view["actions"] != ["NONE"]
        rule_items.append({
            "id": rule_id,
            "declared_in": evidence,
            "registered": True,
            "acts": acts,
            "state": "ACTING" if acts else "REGISTERED",
            "checks_materials": registered_material_checks.get(rule_id, "UNDECLARED"),
            "evidence": (
                action_view["veto_evidence"]
                or action_view["corrective_evidence"]
                or REGISTERED_RULE_EVIDENCE.get(rule_id)
                or registered_material_evidence.get(rule_id, evidence)
            ),
            **action_view,
        })

    technique_items = []
    referenced_technique_rules = {
        "punch_in": [
            "RULE_PUNCH_ZOOM_BOUND",
            "RULE_TECHNIQUE_PATH_UNIFORM",
        ],
        "word_boundary_snap": [
            "RULE_WORD_BOUNDARY_SNAP",
        ],
    }
    for item in techniques:
        technique_id = item["technique_id"]
        relationship = item.get("relationship_source") or {}
        relationship_source = relationship.get("type", "UNDECLARED")
        if technique_id == "punch_in":
            relationship_source = "DERIVED"
        required_materials = item.get("requires_materials")
        if required_materials is None and technique_id == "punch_in":
            required_materials = [
                signal for signal in item.get("required_signals", [])
                if signal in material_by_id
            ]
        required_materials = required_materials or []
        required_rules = item.get("requires_rules")
        if required_rules is None:
            required_rules = referenced_technique_rules.get(
                technique_id, "UNDECLARED"
            )
        blockers = []
        if not required_materials:
            blockers.append({
                "kind": "관계 미선언",
                "detail": "requires_materials 미선언",
            })
        for material_id in required_materials:
            material = material_by_id.get(material_id)
            if material is None:
                blockers.append({
                    "kind": "관계 미선언",
                    "detail": f"감사 재료에 없음: {material_id}",
                })
                continue
            if material["non_null"] == 0:
                blockers.append({
                    "kind": "재료 없음",
                    "detail": material_id,
                })
            elif (
                material["storage_unit"] != "semantic_fragment"
                and not material["fragment_consumer_contract"]
            ):
                blockers.append({
                    "kind": "재료 단위 불일치",
                    "detail": material_id,
                })
        if required_rules == "UNDECLARED":
            blockers.append({
                "kind": "관계 미선언",
                "detail": "requires_rules 미선언",
            })
        else:
            for rule_id in required_rules:
                if _rule_action_view(rule_id, True)["actions"] == ["NONE"]:
                    blockers.append({
                        "kind": "룰 무동작",
                        "detail": rule_id,
                    })
        technique_items.append({
            "id": technique_id,
            "wired": technique_id in wired_set,
            "declared_in": _line_evidence(
                "ccut_backend/config/editing_techniques.json",
                f'"technique_id": "{technique_id}"',
            ),
            "requires_materials": required_materials or "UNDECLARED",
            "requires_rules": required_rules,
            "relationship_source": relationship_source,
            "relationship_source_detail": relationship,
            "blockers": blockers,
            "wireable_now": not blockers,
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
        "relationship_source": "UNDECLARED",
        "relationship_source_detail": {},
        "blockers": [],
        "wireable_now": True,
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
                "status": (
                    "LOCKED"
                    if material["non_null"] == 0
                    else "LIVE"
                    if rule["acts"]
                    else "REGISTERED"
                    if rule["registered"]
                    else "BROKEN"
                ),
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
        (
            "RULE_WORD_BOUNDARY_SNAP",
            "word_boundary_snap",
            _line_evidence(
                "ccut_backend/story_gate/proposal_axis.py",
                '"RULE_WORD_BOUNDARY_SNAP"',
                2,
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

    evidence_refs = _collect_evidence_refs(config, techniques, candidate_ledger)
    audited_at = datetime.now().astimezone().isoformat(timespec="seconds")
    blocker_counts = {}
    for technique in technique_items:
        if technique["wired"]:
            continue
        for kind in {blocker["kind"] for blocker in technique["blockers"]}:
            blocker_counts[kind] = blocker_counts.get(kind, 0) + 1
    material_status = {
        item["id"]: ("VALUE" if item["non_null"] > 0 else "UNKNOWN")
        for item in materials
    }
    result = {
        "audited_at": audited_at,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "materials": materials,
        "rules": {
            "declared": len(declared_rules),
            "registered": len(registered_rules),
            "corrective": sum(
                1 for item in rule_items if "CORRECTIVE" in item["actions"]
            ),
            "veto": sum(1 for item in rule_items if "VETO" in item["actions"]),
            "veto_unreachable": sum(
                1 for item in rule_items if item["veto_unreachable"]
            ),
            "unregistered": len(declared_rules - set(registered_rules)),
            "identity_overlap": len(rule_identity_overlap),
            "identity_overlap_ids": rule_identity_overlap,
            "registered_ids": registered_rules,
            "items": rule_items,
        },
        "techniques": {
            "declared": len(declared_techniques),
            "wired": len(wired),
            "wired_ids": wired,
            "wireable_unwired": sum(
                1 for item in technique_items
                if not item["wired"] and item["wireable_now"]
            ),
            "blocker_counts": blocker_counts,
            "items": technique_items,
        },
        "edges": edges,
        "candidates": candidate_ledger["candidates"],
        "ledger_records": candidate_ledger.get("ledger_records", []),
        "evidence_audit": {
            "checked": len(evidence_refs),
            "exists": sum(1 for r in evidence_refs if r["status"] == "EXISTS"),
            "missing": sum(1 for r in evidence_refs if r["status"] == "MISSING"),
            "moved": sum(1 for r in evidence_refs if r["status"] == "MOVED"),
            "not_a_code_ref": sum(
                1 for r in evidence_refs if r["status"] == "NOT_A_CODE_REF"
            ),
            "items": [r for r in evidence_refs if r["status"] != "EXISTS"],
        },
        "candidate_ledger_guard": candidate_guard,
        "sensor_contract": {
            "exists": True,
            "path": SENSOR_CONTRACT_CONFIG.relative_to(REPO_DIR).as_posix(),
            "schema_version": sensor_contract["schema_version"],
            "required_fields": sensor_contract["record"]["required"],
            "sensor_count": len(sensor_contract["sensors"]),
        },
        "golden_set": {
            "exists": True,
            "path": GOLDENSET_CONFIG.relative_to(REPO_DIR).as_posix(),
            "address_authority": "source_id+start_ms+end_ms+span_hash",
            "fragment_id_authority": "reference_only_may_change",
            "items": golden_resolutions,
        },
        "emotion_evidence": {
            "legacy_node": {
                "id": "emotion_score",
                "status": "재설계",
            },
            "items": [
                {"id": "facial_expression_delta", "status": "UNKNOWN"},
                {"id": "prosody_delta", "status": "VALUE"},
                {"id": "laughter_event", "status": "UNKNOWN"},
                {
                    "id": "speech_presence",
                    "status": material_status.get("speech_presence", "UNKNOWN"),
                },
                {"id": "acoustic_event", "status": "UNKNOWN"},
            ],
            "aggregation": "금지",
        },
    }
    result["ai_context"] = build_lab_context(result)
    return result


def get_audit():
    """조회마다 다시 측정한다.

    이전에는 모듈 전역 캐시를 그대로 돌려줬다. 백필로 DB가 바뀌어도 첫 GET은
    낡은 수치를 반환했고, 국장이 그 위에서 판정을 내릴 위험이 있었다.
    감사는 read-only 이고 100ms 안쪽이라 매 조회 재측정이 부담이 되지 않는다.
    """
    return run_audit()
