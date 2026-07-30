import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from rough_cut.contracts import TextReadinessState, TranscriptSpan
from rough_cut.readiness import assess_text_readiness, decode_subtitle_segments
from rough_cut.transcript_reader import (
    detect_repetition_hallucination,
    read_project_transcript,
)


class TranscriptSpanContractTest(unittest.TestCase):
    def test_accepts_grounded_text_span(self):
        span = TranscriptSpan(
            span_id="TSPAN_SRC_A_1000_2400",
            source_id="SRC_A",
            start_ms=1000,
            end_ms=2400,
            text="A grounded transcript sentence.",
        )

        self.assertEqual(span.to_dict()["start_ms"], 1000)

    def test_rejects_empty_text_or_invalid_time(self):
        with self.assertRaises(ValueError):
            TranscriptSpan("T1", "SRC_A", 1000, 1000, "text")
        with self.assertRaises(ValueError):
            TranscriptSpan("T2", "SRC_A", 1000, 2000, " ")


class TextReadinessContractTest(unittest.TestCase):
    def test_decodes_legacy_double_encoded_segments(self):
        segments = [{"start": 0.0, "end": 1.0, "text": "hello"}]
        encoded = json.dumps(json.dumps(segments))

        self.assertEqual(decode_subtitle_segments(encoded), segments)

    def test_ready_requires_persisted_nonempty_text(self):
        ready = assess_text_readiness(
            "SRC_A",
            [{"start": 0.0, "end": 1.0, "text": "hello"}],
            persisted=True,
        )
        empty = assess_text_readiness(
            "SRC_B",
            [{"start": 0.0, "end": 1.0, "text": " "}],
            persisted=True,
        )

        self.assertEqual(ready.state, TextReadinessState.READY)
        self.assertTrue(ready.ready)
        self.assertEqual(empty.state, TextReadinessState.INSUFFICIENT_TEXT)
        self.assertFalse(empty.ready)

    def test_invalid_or_missing_persistence_is_not_ready(self):
        invalid = assess_text_readiness("SRC_A", "{bad", persisted=True)
        pending = assess_text_readiness("SRC_B", None, persisted=False)

        self.assertEqual(invalid.state, TextReadinessState.FAILED)
        self.assertEqual(pending.state, TextReadinessState.PENDING)


class TranscriptReaderTest(unittest.TestCase):
    def test_filters_repeated_token_and_phrase_but_keeps_normal_repetition(self):
        repeated_token = "노을이 " * 12
        repeated_phrase = "뇌살이 두 개 썼는데 " * 4
        normal = (
            "포켓 LM 뭐 이런 게 있다고 합니다. LM Studio 모바일이 있네요. "
            "LM Studio 모바일 한번 해볼까요. LM Studio 모바일."
        )

        self.assertIsNotNone(detect_repetition_hallucination(repeated_token))
        self.assertIsNotNone(detect_repetition_hallucination(repeated_phrase))
        self.assertIsNone(detect_repetition_hallucination(normal))

    def test_reads_project_order_and_reports_exclusions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "reader.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE project_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    display_order INTEGER
                );
                CREATE TABLE subtitles (
                    subtitle_id TEXT PRIMARY KEY,
                    source_id TEXT,
                    segments TEXT,
                    status TEXT,
                    created_at TEXT
                );
                """
            )
            connection.executemany(
                "INSERT INTO project_sources(program_id, source_id, display_order) "
                "VALUES (?, ?, ?)",
                [
                    ("proj_test", "SRC_B", 1),
                    ("proj_test", "SRC_A", 0),
                ],
            )
            source_a = [
                {"start": 0.0, "end": 1.0, "text": "첫 번째 문장"},
                {"start": 1.0, "end": 2.0, "text": " "},
                {"start": 2.0, "end": 3.0, "text": "노을이 " * 12},
            ]
            source_b = [
                {"start": 0.0, "end": 1.5, "text": "두 번째 소스 문장"},
            ]
            connection.executemany(
                "INSERT INTO subtitles VALUES (?, ?, ?, ?, ?)",
                [
                    ("SUB_A", "SRC_A", json.dumps(json.dumps(source_a)), "COMPLETE", "2"),
                    ("SUB_B", "SRC_B", json.dumps(source_b), "COMPLETE", "1"),
                ],
            )
            connection.commit()
            connection.close()

            result = read_project_transcript("proj_test", db_path=db_path)

        self.assertEqual(result.source_ids, ("SRC_A", "SRC_B"))
        self.assertEqual([span.source_id for span in result.spans], ["SRC_A", "SRC_B"])
        self.assertEqual(
            [item.reason for item in result.exclusions],
            ["empty_text", "repetition_loop"],
        )
        self.assertEqual(result.exclusions[1].repeat_unit, "노을이")
        self.assertEqual(result.exclusions[1].repeat_count, 12)


if __name__ == "__main__":
    unittest.main()
