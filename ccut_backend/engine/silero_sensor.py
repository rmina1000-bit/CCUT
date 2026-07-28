"""Gate-controlled Silero VAD evidence producer.

This module only writes its own record under
semantic_fragments.structural_json.sensor_evidence.silero_vad.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
DB_PATH = BACKEND_DIR / "ccut_app.db"
MODEL_PATH = REPO_DIR / "runtime" / "vad" / "silero_vad.onnx"
MODEL_SHA256 = "1A153A22F4509E292A94E67D6F9B85E8DEB25B4988682B7E174C65279D8788E3"
SENSOR_ID = "silero_vad"
SENSOR_VERSION = "6.2.1_onnx"
SAMPLE_RATE = 16000
THRESHOLD = 0.5


def is_enabled() -> bool:
    return os.getenv("CCUT_SENSOR_SILERO", "OFF").strip().upper() == "ON"


def _model_ready() -> tuple[bool, str | None]:
    if not MODEL_PATH.is_file():
        return False, "MODEL_MISSING"
    digest = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest().upper()
    if digest != MODEL_SHA256:
        return False, "MODEL_HASH_MISMATCH"
    return True, None


def _new_session() -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    return ort.InferenceSession(
        str(MODEL_PATH),
        providers=["CPUExecutionProvider"],
        sess_options=options,
    )


def _read_source_audio(path: str) -> np.ndarray:
    completed = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", path, "-vn",
            "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-f", "s16le", "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    pcm = np.frombuffer(completed.stdout, dtype="<i2")
    return pcm.astype(np.float32) / 32768.0


def _speech_probabilities(
    session: ort.InferenceSession,
    audio: np.ndarray,
) -> list[float]:
    state = np.zeros((2, 1, 128), dtype=np.float32)
    context = np.zeros((1, 64), dtype=np.float32)
    probabilities = []
    for offset in range(0, len(audio), 512):
        block = audio[offset:offset + 512]
        if len(block) < 512:
            block = np.pad(block, (0, 512 - len(block)))
        model_input = np.concatenate(
            [context, block.reshape(1, -1)], axis=1
        ).astype(np.float32)
        output, state = session.run(
            None,
            {
                "input": model_input,
                "state": state,
                "sr": np.array(SAMPLE_RATE, dtype=np.int64),
            },
        )
        context = model_input[:, -64:]
        probabilities.append(float(output.item()))
    return probabilities


def _speech_spans(
    probabilities: list[float],
    sample_count: int,
) -> list[tuple[int, int]]:
    min_speech = SAMPLE_RATE * 0.250
    min_silence = SAMPLE_RATE * 0.100
    speech_pad = SAMPLE_RATE * 0.030
    negative_threshold = max(THRESHOLD - 0.15, 0.01)
    triggered = False
    temporary_end = 0
    current = {}
    spans = []

    for index, probability in enumerate(probabilities):
        current_sample = 512 * index
        if probability >= THRESHOLD and temporary_end:
            temporary_end = 0
        if probability >= THRESHOLD and not triggered:
            triggered = True
            current = {"start": current_sample}
            continue
        if probability < negative_threshold and triggered:
            if not temporary_end:
                temporary_end = current_sample
            if current_sample - temporary_end < min_silence:
                continue
            current["end"] = temporary_end
            if current["end"] - current["start"] > min_speech:
                spans.append(current)
            current = {}
            temporary_end = 0
            triggered = False

    if current and sample_count - current["start"] > min_speech:
        current["end"] = sample_count
        spans.append(current)

    for index, span in enumerate(spans):
        if index == 0:
            span["start"] = int(max(0, span["start"] - speech_pad))
        if index != len(spans) - 1:
            silence = spans[index + 1]["start"] - span["end"]
            if silence < 2 * speech_pad:
                span["end"] += int(silence // 2)
                spans[index + 1]["start"] = int(
                    max(0, spans[index + 1]["start"] - silence // 2)
                )
            else:
                span["end"] = int(min(sample_count, span["end"] + speech_pad))
                spans[index + 1]["start"] = int(
                    max(0, spans[index + 1]["start"] - speech_pad)
                )
        else:
            span["end"] = int(min(sample_count, span["end"] + speech_pad))
    return [(item["start"], item["end"]) for item in spans]


def _unknown_record(fragment, reason: str) -> dict:
    return {
        "sensor": SENSOR_ID,
        "version": SENSOR_VERSION,
        "fragment_id": fragment["fragment_id"],
        "span": {
            "start_ms": round(float(fragment["start"]) * 1000),
            "end_ms": round(float(fragment["end"]) * 1000),
        },
        "values": {
            "speech_ratio": "UNKNOWN",
            "speech_spans": [],
        },
        "confidence": "UNKNOWN",
        "unknown_reason": reason,
    }


def _measure_fragment(
    session: ort.InferenceSession,
    source_audio: np.ndarray,
    fragment,
) -> dict:
    start_sample = max(0, round(float(fragment["start"]) * SAMPLE_RATE))
    end_sample = min(
        len(source_audio),
        round(float(fragment["end"]) * SAMPLE_RATE),
    )
    if end_sample <= start_sample:
        return _unknown_record(fragment, "EMPTY_SPAN")
    audio = source_audio[start_sample:end_sample]
    probabilities = _speech_probabilities(session, audio)
    spans = _speech_spans(probabilities, len(audio))
    speech_samples = sum(end - start for start, end in spans)
    absolute_spans = [
        {
            "start_ms": round((start_sample + start) * 1000 / SAMPLE_RATE),
            "end_ms": round((start_sample + end) * 1000 / SAMPLE_RATE),
        }
        for start, end in spans
    ]
    certainty = (
        max(abs(probability - THRESHOLD) * 2 for probability in probabilities)
        if probabilities else 0.0
    )
    return {
        "sensor": SENSOR_ID,
        "version": SENSOR_VERSION,
        "fragment_id": fragment["fragment_id"],
        "span": {
            "start_ms": round(float(fragment["start"]) * 1000),
            "end_ms": round(float(fragment["end"]) * 1000),
        },
        "values": {
            "speech_ratio": round(speech_samples / len(audio), 6),
            "speech_spans": absolute_spans,
        },
        "confidence": round(min(1.0, certainty), 6),
        "unknown_reason": None,
    }


def _merge_record(structural_json, record: dict) -> str:
    structural = json.loads(structural_json or "{}")
    sensor_evidence = structural.get("sensor_evidence")
    if not isinstance(sensor_evidence, dict):
        sensor_evidence = {}
    sensor_evidence[SENSOR_ID] = record
    structural["sensor_evidence"] = sensor_evidence
    return json.dumps(structural, ensure_ascii=False)


def run_source(
    source_id: str,
    *,
    connection: sqlite3.Connection | None = None,
    session: ort.InferenceSession | None = None,
) -> dict:
    if not is_enabled():
        return {"source_id": source_id, "status": "GATE_OFF", "updated": 0}
    ready, reason = _model_ready()
    if not ready:
        return {
            "source_id": source_id,
            "status": reason,
            "updated": 0,
        }

    owns_connection = connection is None
    con = connection or sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    fragments = con.execute(
        'SELECT fragment_id, source_id, start, "end", structural_json '
        "FROM semantic_fragments WHERE source_id=? ORDER BY start",
        (source_id,),
    ).fetchall()
    if not fragments:
        if owns_connection:
            con.close()
        return {"source_id": source_id, "status": "NO_FRAGMENTS", "updated": 0}

    source = con.execute(
        "SELECT file_path FROM sources WHERE source_id=?",
        (source_id,),
    ).fetchone()
    source_path = source["file_path"] if source else None
    started = time.perf_counter()
    records = []
    if not source_path or not Path(source_path).is_file():
        records = [
            _unknown_record(fragment, "SOURCE_MISSING")
            for fragment in fragments
        ]
        status = "SOURCE_MISSING"
    else:
        try:
            source_audio = _read_source_audio(source_path)
            model = session or _new_session()
            records = [
                _measure_fragment(model, source_audio, fragment)
                for fragment in fragments
            ]
            status = "OK"
        except Exception as error:
            records = [
                _unknown_record(
                    fragment,
                    f"INFERENCE_ERROR:{type(error).__name__}",
                )
                for fragment in fragments
            ]
            status = "INFERENCE_ERROR"

    for fragment, record in zip(fragments, records):
        con.execute(
            "UPDATE semantic_fragments SET structural_json=? "
            "WHERE fragment_id=?",
            (_merge_record(fragment["structural_json"], record),
             fragment["fragment_id"]),
        )
    con.commit()
    if owns_connection:
        con.close()
    unknown = sum(
        record["values"]["speech_ratio"] == "UNKNOWN" for record in records
    )
    return {
        "source_id": source_id,
        "status": status,
        "updated": len(records),
        "unknown": unknown,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def backfill_all(db_path: Path = DB_PATH) -> dict:
    started = time.perf_counter()
    if not is_enabled():
        return {"status": "GATE_OFF", "updated": 0, "sources": []}
    ready, reason = _model_ready()
    if not ready:
        return {"status": reason, "updated": 0, "sources": []}

    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    source_ids = [
        row["source_id"] for row in con.execute(
            "SELECT DISTINCT source_id FROM semantic_fragments ORDER BY source_id"
        )
    ]
    session = _new_session()
    rows = [
        run_source(source_id, connection=con, session=session)
        for source_id in source_ids
    ]
    con.close()
    updated = sum(row.get("updated", 0) for row in rows)
    unknown = sum(row.get("unknown", 0) for row in rows)
    failed = sum(row.get("status") != "OK" for row in rows)
    return {
        "status": "OK" if failed == 0 else "PARTIAL",
        "updated": updated,
        "unknown": unknown,
        "failed_sources": failed,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "sources": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true")
    args = parser.parse_args()
    result = backfill_all() if args.backfill else {
        "enabled": is_enabled(),
        "model": _model_ready(),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") not in {"PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
