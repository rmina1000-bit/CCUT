import json
import unittest
from unittest.mock import patch

from rough_cut.contracts import RoughCutAct, RoughCutStoryDraft, RoughCutStoryPhase
from rough_cut.story_builder import (
    RoughCutBuildStatus,
    RoughCutStoryBuilder,
    chunk_transcript_spans,
)
from rough_cut.contracts import TranscriptSpan
from rough_cut.validator import validate_story_draft


def _spans(count: int):
    return [
        TranscriptSpan(
            span_id=f"TSPAN_{index:03d}",
            source_id="SRC_A",
            start_ms=index * 1000,
            end_ms=(index + 1) * 1000,
            text=f"공통 이야기 문장 {index}",
            segment_order=index,
        )
        for index in range(count)
    ]


def _story_output(span_ids):
    groups = [span_ids[index::4] for index in range(4)]
    phases = ["gi", "seung", "jeon", "gyeol"]
    return {
        "premise": "공통 이야기",
        "acts": [
            {
                "phase": phase,
                "summary": "공통 이야기 문장",
                "span_ids": group,
            }
            for phase, group in zip(phases, groups)
        ],
        "ordered_span_ids": span_ids,
    }


class RoughCutValidatorTest(unittest.TestCase):
    def test_step3_distribution_is_rejected_as_not_shortened_and_weak_turn(self):
        spans = _spans(16)
        acts = (
            RoughCutAct(RoughCutStoryPhase.GI, "공통 이야기", ("TSPAN_000",)),
            RoughCutAct(
                RoughCutStoryPhase.SEUNG,
                "공통 이야기",
                tuple(f"TSPAN_{index:03d}" for index in range(1, 14)),
            ),
            RoughCutAct(RoughCutStoryPhase.JEON, "공통 이야기", ("TSPAN_014",)),
            RoughCutAct(RoughCutStoryPhase.GYEOL, "공통 이야기", ("TSPAN_015",)),
        )
        draft = RoughCutStoryDraft(
            project_id="proj_test",
            premise="공통 이야기",
            acts=acts,
            ordered_span_ids=tuple(span.span_id for span in spans),
        )

        result = validate_story_draft(
            draft,
            spans,
            total_transcript_span_count=16,
        )

        self.assertFalse(result.accepted)
        self.assertIn("not_shortened", result.codes)
        self.assertIn("weak_turn", result.codes)

    def test_enforces_five_integrity_rejection_rules(self):
        spans = _spans(4)
        draft = RoughCutStoryDraft(
            project_id="proj_test",
            premise="외계 우주 전쟁",
            acts=(
                RoughCutAct(
                    RoughCutStoryPhase.GI,
                    "",
                    ("TSPAN_000", "UNKNOWN"),
                ),
                RoughCutAct(
                    RoughCutStoryPhase.SEUNG,
                    "외계 우주 전쟁",
                    ("TSPAN_000", "TSPAN_001"),
                ),
                RoughCutAct(
                    RoughCutStoryPhase.JEON,
                    "외계 우주 전쟁",
                    ("TSPAN_002",),
                ),
                RoughCutAct(
                    RoughCutStoryPhase.GYEOL,
                    "외계 우주 전쟁",
                    ("TSPAN_003",),
                ),
            ),
            ordered_span_ids=(
                "TSPAN_000",
                "UNKNOWN",
                "TSPAN_000",
                "TSPAN_001",
                "TSPAN_002",
                "TSPAN_003",
            ),
        )

        result = validate_story_draft(
            draft,
            spans,
            total_transcript_span_count=4,
        )

        for code in (
            "unknown_id",
            "duplicate_id",
            "empty_text",
            "not_shortened",
            "ungrounded_text",
        ):
            self.assertIn(code, result.codes)


class RoughCutStoryBuilderTest(unittest.TestCase):
    def test_chunker_keeps_whole_spans_and_splits_120_items(self):
        spans = _spans(120)

        chunks = chunk_transcript_spans(spans, max_spans=48)

        self.assertEqual([len(chunk) for chunk in chunks], [48, 48, 24])
        self.assertEqual(
            [span.span_id for chunk in chunks for span in chunk],
            [span.span_id for span in spans],
        )

    @patch("engine.hub._ollama_json")
    def test_120_spans_run_three_chunks_then_one_arrangement(self, call_hub):
        def model_response(prompt, **_kwargs):
            payload = json.loads(prompt.split("INPUT_JSON=", 1)[1])
            input_spans = payload["transcript_spans"]
            if "selection_limit" in payload:
                selected = input_spans[:8]
                return {
                    "summary": selected[0]["text"],
                    "selected_span_ids": [
                        span["span_id"] for span in selected
                    ],
                }
            return _story_output(
                [span["span_id"] for span in input_spans]
            )

        call_hub.side_effect = model_response

        result = RoughCutStoryBuilder().build("proj_test", _spans(120))

        self.assertEqual(result.status, RoughCutBuildStatus.OK)
        self.assertEqual(result.chunk_count, 3)
        self.assertEqual(result.model_call_count, 4)
        self.assertEqual(
            [attempt.stage for attempt in result.attempts],
            ["chunk", "chunk", "chunk", "arrangement"],
        )

    @patch("engine.hub._ollama_json")
    def test_same_rejection_twice_stops_before_third_attempt(self, call_hub):
        def no_reduction(prompt, **_kwargs):
            payload = json.loads(prompt.split("INPUT_JSON=", 1)[1])
            input_spans = payload["transcript_spans"]
            if "selection_limit" not in payload:
                return _story_output(
                    [span["span_id"] for span in input_spans]
                )
            return {
                "summary": input_spans[0]["text"],
                "selected_span_ids": [
                    span["span_id"] for span in input_spans
                ],
            }

        call_hub.side_effect = no_reduction

        result = RoughCutStoryBuilder().build("proj_test", _spans(16))

        self.assertEqual(
            result.status,
            RoughCutBuildStatus.ARRANGEMENT_EXHAUSTED,
        )
        self.assertEqual(result.model_call_count, 3)
        self.assertEqual(
            [
                attempt.rejection_codes
                for attempt in result.attempts
                if attempt.stage == "arrangement"
            ],
            [("not_shortened",), ("not_shortened",)],
        )

    @patch("engine.hub._ollama_json")
    def test_different_failures_never_exceed_three_attempts(self, call_hub):
        call_hub.side_effect = [
            {},
            {
                "summary": "공통 이야기",
                "selected_span_ids": ["UNKNOWN"],
            },
            {
                "summary": "공통 이야기",
                "selected_span_ids": ["TSPAN_000", "TSPAN_000"],
            },
        ]

        result = RoughCutStoryBuilder().build("proj_test", _spans(16))

        self.assertEqual(result.status, RoughCutBuildStatus.CHUNK_EXHAUSTED)
        self.assertEqual(result.model_call_count, 3)
        self.assertEqual(call_hub.call_count, 3)

    @patch("engine.hub._ollama_json")
    def test_final_validation_failure_clears_stale_adapter_error(self, call_hub):
        selected_ids = [f"TSPAN_{index:03d}" for index in range(4)]
        ungrounded = _story_output(selected_ids)
        ungrounded["premise"] = "외계 우주 전쟁"
        call_hub.side_effect = [
            {
                "summary": "공통 이야기 문장",
                "selected_span_ids": selected_ids,
            },
            {},
            ungrounded,
            ungrounded,
        ]

        result = RoughCutStoryBuilder().build("proj_test", _spans(16))

        self.assertEqual(
            result.status,
            RoughCutBuildStatus.ARRANGEMENT_EXHAUSTED,
        )
        self.assertIsNone(result.error_message)
        self.assertIn(
            "ungrounded_text",
            [issue.code.value for issue in result.failure_issues],
        )


if __name__ == "__main__":
    unittest.main()
