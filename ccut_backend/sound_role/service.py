"""Derived sound handling labels plus user corrections.

Authority boundaries:
* Membership and order come from the current story.fids.
* Sensors remain evidence and are read-only.
* Only explicit user corrections are persisted in this module's table.
* Rendering and fragment_edit_state are not read or written here.
"""
import datetime
import json
import os
import sqlite3

from edit_contract.time_units import ms_to_seconds, to_ms
from story_gate.service import resolve_sequence

from .models import ALLOWED_ROLES, SCHEMA_VERSION, TABLE

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")


class SoundRoleError(Exception):
    def __init__(self, code, message, http_status=400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.extra = extra


def _connect(db_path=None):
    con = sqlite3.connect(db_path or DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _as_json(raw):
    for _ in range(3):
        if not isinstance(raw, str):
            break
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hash6(value):
    result = 5381
    for char in str(value):
        result = ((result << 5) + result + ord(char)) & 0xFFFFFFFF
    return format(result, "x").rjust(6, "0")[-6:]


def _timeline_item_id(program_id, fid, occurrence):
    # Must match ledger_r0.py and editContractClient.ts exactly.
    return f"ITEM_{_hash6(program_id)}_{fid}_{occurrence}"


def _tables_ready(con):
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
    ).fetchone()
    return row is not None


def _story_ui(con, program_id):
    row = con.execute(
        "SELECT ui_state FROM programs WHERE program_id=?", (program_id,)
    ).fetchone()
    if row is None:
        raise SoundRoleError("program_not_found", "Project not found.", 404)
    ui = _as_json(row["ui_state"])
    return ui if isinstance(ui, dict) else {}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _story_items(con, program_id):
    ui = _story_ui(con, program_id)
    _mode, fids, source = resolve_sequence(con, program_id)
    story = ui.get("story") if isinstance(ui.get("story"), dict) else {}
    anchors = story.get("fidAnchors") if isinstance(story.get("fidAnchors"), dict) else {}

    snapshot = {}
    for item in ui.get("storyFragments") or []:
        if not isinstance(item, dict):
            continue
        fid = item.get("fragment_id") or item.get("fid") or item.get("uid")
        if fid:
            snapshot[str(fid)] = item

    semantic = {}
    if fids:
        placeholders = ",".join("?" for _ in fids)
        for row in con.execute(
            f'SELECT fragment_id, source_id, start, "end", structural_json '
            f'FROM semantic_fragments WHERE fragment_id IN ({placeholders})',
            list(fids),
        ):
            semantic[str(row["fragment_id"])] = row

    seen = {}
    items = []
    for ordinal, raw_fid in enumerate(fids):
        fid = str(raw_fid)
        occurrence = seen.get(fid, 0)
        seen[fid] = occurrence + 1
        source_id = None
        start_ms = end_ms = None
        coord_source = None

        anchor = anchors.get(fid)
        if isinstance(anchor, dict):
            source_id = anchor.get("source_id")
            start_ms = anchor.get("anchor_start_ms")
            end_ms = anchor.get("anchor_end_ms")
            if isinstance(start_ms, int) and isinstance(end_ms, int) and end_ms > start_ms:
                coord_source = "story_anchor"
            else:
                start_ms = end_ms = None

        row = semantic.get(fid)
        if start_ms is None and row is not None:
            source_id = row["source_id"]
            try:
                start_ms, end_ms = to_ms(float(row["start"])), to_ms(float(row["end"]))
                coord_source = "semantic_fragment"
            except (TypeError, ValueError):
                start_ms = end_ms = None

        snap = snapshot.get(fid)
        if start_ms is None and isinstance(snap, dict):
            source_id = snap.get("source_id") or snap.get("sourceId")
            start = snap.get("start") if snap.get("start") is not None else snap.get("start_time")
            end = snap.get("end") if snap.get("end") is not None else snap.get("end_time")
            try:
                start_ms, end_ms = to_ms(float(start)), to_ms(float(end))
                coord_source = "story_snapshot"
            except (TypeError, ValueError):
                start_ms = end_ms = None

        items.append({
            "ordinal": ordinal,
            "fragment_id": fid,
            "timeline_item_id": _timeline_item_id(program_id, fid, occurrence),
            "source_id": str(source_id) if source_id else None,
            "anchor_start_ms": start_ms,
            "anchor_end_ms": end_ms,
            "coord_source": coord_source,
            "structural_json": row["structural_json"] if row is not None else None,
        })
    return source, items


def _source_material(con, source_id):
    transcript_available = False
    segments = []
    for row in con.execute(
        "SELECT segments FROM subtitles WHERE source_id=?", (source_id,)
    ):
        parsed = _as_json(row["segments"])
        if isinstance(parsed, list):
            transcript_available = True
            segments.extend(item for item in parsed if isinstance(item, dict))

    evidence = []
    for row in con.execute(
        'SELECT start, "end", audio_energy, silence FROM evidence_board '
        'WHERE source_id=? ORDER BY start',
        (source_id,),
    ):
        evidence.append(dict(row))
    return {
        "transcript_available": transcript_available,
        "segments": segments,
        "evidence": evidence,
    }


def _overlaps(start, end, window_start, window_end):
    try:
        return float(end) > window_start and float(start) < window_end
    except (TypeError, ValueError):
        return False


def _silence_value(raw):
    value = _as_json(raw)
    if value is None:
        return False, False
    if isinstance(value, bool):
        return True, value
    if isinstance(value, list):
        return True, bool(value)
    if isinstance(value, dict):
        for key in ("is_silence", "silence", "detected"):
            if isinstance(value.get(key), bool):
                return True, value[key]
        for key in ("ranges", "segments", "intervals"):
            if isinstance(value.get(key), list):
                return True, bool(value[key])
        return True, False
    if isinstance(value, str):
        return True, value.strip().lower() in {"silence", "silent", "true"}
    return True, False


def _classify_item(item, material):
    start_ms, end_ms = item["anchor_start_ms"], item["anchor_end_ms"]
    if start_ms is None or end_ms is None or not item.get("source_id"):
        return "unknown", "missing_coordinates", {
            "transcript": {"available": False, "word_count": None, "segment_count": None},
            "silero": {"available": False, "speech_ratio": None},
            "audio_energy": {"available": False, "value": None},
            "silence": {"available": False, "detected": False},
        }

    start_sec, end_sec = ms_to_seconds(start_ms), ms_to_seconds(end_ms)
    word_count = 0
    text_segment_count = 0
    probabilities = []
    for segment in material["segments"]:
        if not _overlaps(segment.get("start"), segment.get("end"), start_sec, end_sec):
            continue
        if str(segment.get("text") or "").strip():
            text_segment_count += 1
        for word in segment.get("words") or []:
            if not isinstance(word, dict):
                continue
            if _overlaps(word.get("start"), word.get("end"), start_sec, end_sec):
                word_count += 1
                probability = _number(word.get("probability"))
                if probability is not None:
                    probabilities.append(probability)

    structural = _as_json(item.get("structural_json"))
    if not isinstance(structural, dict):
        structural = {}
    speech_ratio = _number(
        (((structural.get("sensor_evidence") or {}).get("silero_vad") or {})
         .get("values") or {}).get("speech_ratio")
    )

    energies = []
    silence_available = False
    silence_detected = False
    for row in material["evidence"]:
        if not _overlaps(row.get("start"), row.get("end"), start_sec, end_sec):
            continue
        energy = _number(row.get("audio_energy"))
        if energy is not None:
            energies.append(energy)
        available, detected = _silence_value(row.get("silence"))
        silence_available = silence_available or available
        silence_detected = silence_detected or detected

    energy_value = round(sum(energies) / len(energies), 6) if energies else None
    avg_probability = (
        round(sum(probabilities) / len(probabilities), 6) if probabilities else None
    )
    evidence = {
        "transcript": {
            "available": material["transcript_available"],
            "word_count": word_count if material["transcript_available"] else None,
            "segment_count": text_segment_count if material["transcript_available"] else None,
            "average_word_probability": avg_probability,
        },
        "silero": {"available": speech_ratio is not None, "speech_ratio": speech_ratio},
        "audio_energy": {"available": energy_value is not None, "value": energy_value},
        "silence": {"available": silence_available, "detected": silence_detected},
    }

    if word_count > 0 or text_segment_count > 0:
        return "dialogue", "transcript", evidence
    if speech_ratio is not None and speech_ratio > 0:
        return "dialogue", "silero_speech", evidence
    if silence_detected:
        return "silence", "silence_sensor", evidence
    if energy_value is not None:
        return "background", "audio_energy", evidence
    return "unknown", "no_material", evidence


def _override_rows(con, program_id):
    if not _tables_ready(con):
        return {}
    rows = con.execute(
        f"SELECT * FROM {TABLE} WHERE program_id=?", (program_id,)
    ).fetchall()
    return {row["timeline_item_id"]: row for row in rows}


def _build_roles(con, program_id):
    sequence_source, items = _story_items(con, program_id)
    source_cache = {}
    overrides = _override_rows(con, program_id)
    roles = []
    for item in items:
        source_id = item.get("source_id")
        if source_id and source_id not in source_cache:
            source_cache[source_id] = _source_material(con, source_id)
        material = source_cache.get(source_id, {
            "transcript_available": False, "segments": [], "evidence": [],
        })
        detected, reason, evidence = _classify_item(item, material)
        override = overrides.get(item["timeline_item_id"])
        effective = override["sound_role"] if override is not None else detected
        roles.append({
            **{key: item[key] for key in (
                "ordinal", "timeline_item_id", "fragment_id", "source_id",
                "anchor_start_ms", "anchor_end_ms", "coord_source",
            )},
            "detected_role": detected,
            "effective_role": effective,
            "reason": reason,
            "evidence": evidence,
            "overridden": override is not None,
            "revision": override["revision"] if override is not None else None,
            "editable": item["anchor_start_ms"] is not None and bool(item.get("source_id")),
        })
    return sequence_source, roles


def list_sound_roles(program_id, *, db_path=None):
    con = _connect(db_path)
    try:
        sequence_source, roles = _build_roles(con, program_id)
        detected_counts = {role: 0 for role in ALLOWED_ROLES}
        effective_counts = {role: 0 for role in ALLOWED_ROLES}
        for item in roles:
            detected_counts[item["detected_role"]] += 1
            effective_counts[item["effective_role"]] += 1
        return {
            "ok": True,
            "program_id": program_id,
            "sequence_source": sequence_source,
            "item_count": len(roles),
            "storage_ready": _tables_ready(con),
            "material_missing_count": detected_counts["unknown"],
            "detected_counts": detected_counts,
            "effective_counts": effective_counts,
            "items": roles,
        }
    finally:
        con.close()


def set_sound_role_override(program_id, *, timeline_item_id, fragment_id,
                            role, expected_revision=None, db_path=None):
    if role not in ALLOWED_ROLES:
        raise SoundRoleError(
            "invalid_role", "Unsupported sound handling value.", 400,
            allowed=list(ALLOWED_ROLES),
        )
    con = _connect(db_path)
    try:
        if not _tables_ready(con):
            raise SoundRoleError("table_missing", "Sound corrections are unavailable.", 503)
        if expected_revision is not None:
            try:
                expected_revision = int(expected_revision)
            except (TypeError, ValueError):
                raise SoundRoleError(
                    "revision_conflict", "Correction changed. Reload first.", 409
                )

        # Membership validation and the revision write are one decision. A story
        # save or another correction cannot slip between these two reads.
        con.execute("BEGIN IMMEDIATE")
        _source, roles = _build_roles(con, program_id)
        target = next((item for item in roles
                       if item["timeline_item_id"] == timeline_item_id), None)
        if target is None or target["fragment_id"] != fragment_id:
            raise SoundRoleError(
                "item_not_in_current_story",
                "The fragment is not in the current story.",
                409,
            )
        if not target["editable"]:
            raise SoundRoleError("item_unresolved", "Fragment coordinates are unavailable.", 409)

        current = con.execute(
            f"SELECT revision FROM {TABLE} WHERE program_id=? AND timeline_item_id=?",
            (program_id, timeline_item_id),
        ).fetchone()
        now = _now()
        if current is None:
            if expected_revision not in (None, 0):
                raise SoundRoleError("revision_conflict", "Correction changed. Reload first.", 409)
            revision = 1
            con.execute(
                f"INSERT INTO {TABLE} "
                "(program_id, timeline_item_id, fragment_id, source_id, "
                "anchor_start_ms, anchor_end_ms, sound_role, schema_version, "
                "revision, actor, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (program_id, timeline_item_id, fragment_id, target["source_id"],
                 target["anchor_start_ms"], target["anchor_end_ms"], role,
                 SCHEMA_VERSION, revision, "user", now, now),
            )
        else:
            if expected_revision is None or expected_revision != int(current["revision"]):
                raise SoundRoleError("revision_conflict", "Correction changed. Reload first.", 409)
            revision = int(current["revision"]) + 1
            con.execute(
                f"UPDATE {TABLE} SET fragment_id=?, source_id=?, anchor_start_ms=?, "
                "anchor_end_ms=?, sound_role=?, schema_version=?, revision=?, actor=?, "
                "updated_at=? WHERE program_id=? AND timeline_item_id=?",
                (fragment_id, target["source_id"], target["anchor_start_ms"],
                 target["anchor_end_ms"], role, SCHEMA_VERSION, revision, "user", now,
                 program_id, timeline_item_id),
            )
        con.commit()
        print(
            f"[SOUND-ROLE][CORRECTION] program={program_id} item={timeline_item_id} "
            f"detected={target['detected_role']} selected={role} revision={revision}"
        )
        return {
            "ok": True,
            "program_id": program_id,
            "timeline_item_id": timeline_item_id,
            "fragment_id": fragment_id,
            "detected_role": target["detected_role"],
            "effective_role": role,
            "overridden": True,
            "revision": revision,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
