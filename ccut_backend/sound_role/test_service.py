import json
import os
import sqlite3
import tempfile
import unittest

from sound_role.models import DDL_SQL, INDEX_SQL, TABLE, self_check
from sound_role.service import (
    SoundRoleError,
    list_sound_roles,
    set_sound_role_override,
)


PROGRAM = "proj_sound_test"


class SoundRoleServiceTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        con = sqlite3.connect(self.db_path)
        try:
            con.executescript("""
                CREATE TABLE programs (program_id TEXT PRIMARY KEY, ui_state TEXT);
                CREATE TABLE project_sources (
                    id INTEGER PRIMARY KEY, program_id TEXT, source_id TEXT,
                    display_order INTEGER
                );
                CREATE TABLE semantic_fragments (
                    fragment_id TEXT, source_id TEXT, start REAL, end REAL,
                    structural_json TEXT
                );
                CREATE TABLE subtitles (
                    subtitle_id TEXT, source_id TEXT, segments TEXT, status TEXT
                );
                CREATE TABLE evidence_board (
                    fragment_id TEXT, source_id TEXT, start REAL, end REAL,
                    audio_energy REAL, silence TEXT
                );
            """)
            fids = ["F_TRANSCRIPT", "F_SILERO", "F_ENERGY", "F_SILENCE", "F_UNKNOWN"]
            anchors = {
                fid: {
                    "source_id": "SRC_TEST",
                    "anchor_start_ms": idx * 10000,
                    "anchor_end_ms": (idx + 1) * 10000,
                }
                for idx, fid in enumerate(fids)
            }
            ui = {"story": {"fids": fids, "fidAnchors": anchors}}
            con.execute("INSERT INTO programs VALUES (?,?)", (PROGRAM, json.dumps(ui)))
            con.execute(
                "INSERT INTO project_sources VALUES (1,?,?,0)", (PROGRAM, "SRC_TEST")
            )
            for idx, fid in enumerate(fids):
                structural = {}
                if fid == "F_SILERO":
                    structural = {
                        "sensor_evidence": {
                            "silero_vad": {"values": {"speech_ratio": 0.8}}
                        }
                    }
                con.execute(
                    "INSERT INTO semantic_fragments VALUES (?,?,?,?,?)",
                    (fid, "SRC_TEST", idx * 10.0, (idx + 1) * 10.0,
                     json.dumps(structural)),
                )
            segments = [{
                "start": 1.0,
                "end": 2.0,
                "text": "spoken words",
                "words": [{"start": 1.0, "end": 1.5, "word": "spoken", "probability": 0.9}],
            }]
            con.execute(
                "INSERT INTO subtitles VALUES (?,?,?,?)",
                ("SUB_TEST", "SRC_TEST", json.dumps(segments), "COMPLETE"),
            )
            con.execute(
                "INSERT INTO evidence_board VALUES (?,?,?,?,?,?)",
                ("EV_ENERGY", "SRC_TEST", 20.0, 30.0, 0.4, None),
            )
            con.execute(
                "INSERT INTO evidence_board VALUES (?,?,?,?,?,?)",
                ("EV_SILENCE", "SRC_TEST", 30.0, 40.0, None, json.dumps(True)),
            )
            con.execute(DDL_SQL)
            for sql in INDEX_SQL:
                con.execute(sql)
            con.commit()
        finally:
            con.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_sensor_precedence_and_no_material(self):
        result = list_sound_roles(PROGRAM, db_path=self.db_path)
        self.assertEqual(result["sequence_source"], "ui_state")
        self.assertEqual(result["item_count"], 5)
        self.assertEqual(
            [item["detected_role"] for item in result["items"]],
            ["dialogue", "dialogue", "background", "silence", "unknown"],
        )
        self.assertEqual(result["material_missing_count"], 1)

    def test_user_correction_wins_and_survives_reopen(self):
        before = list_sound_roles(PROGRAM, db_path=self.db_path)
        target = before["items"][2]
        saved = set_sound_role_override(
            PROGRAM,
            timeline_item_id=target["timeline_item_id"],
            fragment_id=target["fragment_id"],
            role="dialogue",
            db_path=self.db_path,
        )
        self.assertEqual(saved["revision"], 1)
        reopened = list_sound_roles(PROGRAM, db_path=self.db_path)
        item = reopened["items"][2]
        self.assertEqual(item["detected_role"], "background")
        self.assertEqual(item["effective_role"], "dialogue")
        self.assertTrue(item["overridden"])

        updated = set_sound_role_override(
            PROGRAM,
            timeline_item_id=target["timeline_item_id"],
            fragment_id=target["fragment_id"],
            role="silence",
            expected_revision=1,
            db_path=self.db_path,
        )
        self.assertEqual(updated["revision"], 2)
        with self.assertRaises(SoundRoleError) as caught:
            set_sound_role_override(
                PROGRAM,
                timeline_item_id=target["timeline_item_id"],
                fragment_id=target["fragment_id"],
                role="unknown",
                expected_revision=1,
                db_path=self.db_path,
            )
        self.assertEqual(caught.exception.code, "revision_conflict")

    def test_schema_is_override_only(self):
        ok, detail = self_check()
        self.assertTrue(ok, detail)
        con = sqlite3.connect(self.db_path)
        try:
            columns = [row[1] for row in con.execute(f"PRAGMA table_info({TABLE})")]
            self.assertNotIn("detected_role", columns)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM programs").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM semantic_fragments").fetchone()[0], 5)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
