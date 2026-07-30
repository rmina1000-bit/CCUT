import unittest
from unittest.mock import patch

from rough_cut.contracts import QwenStoryAdapterStatus, TranscriptSpan
from rough_cut.qwen_story_adapter import QwenStoryAdapter


def _span(span_id: str = "TSPAN_A") -> TranscriptSpan:
    return TranscriptSpan(
        span_id=span_id,
        source_id="SRC_A",
        start_ms=1000,
        end_ms=2000,
        text="테스트 전사 문장",
        confidence=0.97,
    )


def _valid_output():
    return {
        "premise": "핵심 이야기",
        "acts": [
            {"phase": "gi", "summary": "시작", "span_ids": ["UNKNOWN"]},
            {"phase": "seung", "summary": "전개", "span_ids": ["TSPAN_A"]},
            {"phase": "jeon", "summary": "전환", "span_ids": ["TSPAN_A"]},
            {"phase": "gyeol", "summary": "마무리", "span_ids": []},
        ],
        "ordered_span_ids": ["UNKNOWN", "TSPAN_A", "TSPAN_A"],
    }


class QwenStoryAdapterTest(unittest.TestCase):
    @patch("engine.hub._ollama_json")
    def test_uses_hub_once_and_accepts_structural_contract_only(self, call_hub):
        call_hub.return_value = _valid_output()

        result = QwenStoryAdapter().generate("proj_test", [_span()])

        self.assertEqual(result.status, QwenStoryAdapterStatus.OK)
        self.assertEqual(result.draft.ordered_span_ids, ("UNKNOWN", "TSPAN_A", "TSPAN_A"))
        call_hub.assert_called_once()
        prompt = call_hub.call_args.args[0]
        self.assertEqual(call_hub.call_args.kwargs["temperature"], 0)
        self.assertIn('"text":"테스트 전사 문장"', prompt)
        self.assertNotIn("confidence", prompt)
        self.assertNotIn("motion", prompt)
        self.assertNotIn("audio", prompt)

    @patch("engine.hub._ollama_json")
    def test_reports_contract_invalid_without_retry(self, call_hub):
        malformed = _valid_output()
        malformed["acts"] = malformed["acts"][:3]
        call_hub.return_value = malformed

        result = QwenStoryAdapter().generate("proj_test", [_span()])

        self.assertEqual(result.status, QwenStoryAdapterStatus.CONTRACT_INVALID)
        self.assertIn("gi, seung, jeon, gyeol", result.error_message)
        call_hub.assert_called_once()

    @patch("engine.hub._ollama_json")
    def test_reports_model_call_failure_without_retry(self, call_hub):
        call_hub.side_effect = TimeoutError("model timeout")

        result = QwenStoryAdapter().generate("proj_test", [_span()])

        self.assertEqual(result.status, QwenStoryAdapterStatus.MODEL_CALL_FAILED)
        self.assertEqual(result.error_message, "model timeout")
        call_hub.assert_called_once()


if __name__ == "__main__":
    unittest.main()
