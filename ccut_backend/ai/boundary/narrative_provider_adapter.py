import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from .narrative_provider_contract import (
    NarrativeLLMStatus,
    StoryIntentPatch,
    NarrativeLLMResult,
    validate_narrative_contract
)

class NarrativeProviderAdapter:
    def __init__(self, model: str = "qwen3:4b", base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url
        self.timeout = 60
        self.keep_alive = "10m"

    def get_story_intent_patch(self, user_message: str) -> NarrativeLLMResult:
        url = f"{self.base_url}/api/generate"
        
        system_prompt = (
            "You are a professional video editor and narrative consultant.\n"
            "Analyze the user message and provide a StoryIntentPatch JSON.\n"
            "Rules:\n"
            "1. Must return ONLY valid JSON.\n"
            "2. patch_type must be 'story_intent_patch'.\n"
            "3. tone should be one of [natural, fast, slow, emotional].\n"
            "4. target_length should be one of [short, medium, long].\n"
            "5. must_keep and avoid are lists of fragment IDs or descriptions (leave empty if not specified).\n"
            "6. coverage should be one of [default, balanced_sources]. Set to 'balanced_sources' when the user wants to balance sources, use various/all videos, or distribute clips evenly.\n"
        )
        
        prompt = f"{system_prompt}\nUser message: '{user_message}'\n\nJSON:"
        
        # JSON Schema from CASE 10
        schema = {
            "type": "object",
            "properties": {
                "patch_type": { "type": "string" },
                "tone": { "type": "string" },
                "target_length": { "type": "string" },
                "must_keep": { "type": "array", "items": { "type": "string" } },
                "avoid": { "type": "array", "items": { "type": "string" } },
                "coverage": { "type": "string" },
                "reason": { "type": "string" }
            },
            "required": ["patch_type", "tone", "target_length", "must_keep", "avoid", "coverage", "reason"]
        }

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": schema,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0,
                "num_predict": 256
            }
        }

        start_time = time.time()
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                resp_data = json.loads(response.read().decode())
                latency = int((time.time() - start_time) * 1000)
                
                raw_res = resp_data.get("response", "")
                thinking = resp_data.get("thinking", "")

                if validate_narrative_contract(raw_res):
                    # Production OK: Valid JSON in response field
                    data = json.loads(self._clean_json(raw_res))
                    return NarrativeLLMResult(
                        status=NarrativeLLMStatus.OK,
                        patch=StoryIntentPatch.from_dict(data),
                        latency_ms=latency,
                        raw_response=raw_res,
                        thinking=thinking
                    )
                elif validate_narrative_contract(thinking):
                    # Reject thinking-only JSON for production consistency
                    return NarrativeLLMResult(
                        status=NarrativeLLMStatus.THINKING_JSON_ONLY,
                        latency_ms=latency,
                        raw_response=raw_res,
                        thinking=thinking,
                        error_message="JSON found in thinking field, but response is empty."
                    )
                else:
                    return NarrativeLLMResult(
                        status=NarrativeLLMStatus.JSON_PARSE_FAILED,
                        latency_ms=latency,
                        raw_response=raw_res,
                        thinking=thinking,
                        error_message="Could not parse valid StoryIntentPatch from LLM output."
                    )

        except urllib.error.URLError as e:
            if "timed out" in str(e).lower():
                return NarrativeLLMResult(status=NarrativeLLMStatus.MODEL_CALL_TIMEOUT, error_message=str(e))
            return NarrativeLLMResult(status=NarrativeLLMStatus.OLLAMA_NOT_RUNNING, error_message=str(e))
        except Exception as e:
            return NarrativeLLMResult(status=NarrativeLLMStatus.MODEL_CALL_FAILED, error_message=str(e))

    def _clean_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text.split("```json")[1].split("```")[0].strip()
        elif text.startswith("```"):
            text = text.split("```")[1].split("```")[0].strip()
        return text
