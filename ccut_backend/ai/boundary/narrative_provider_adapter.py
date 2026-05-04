import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from .narrative_provider_contract import (
    NarrativeLLMStatus,
    StoryIntentPatch,
    ConversationIntent,
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
            "Analyze the user message and provide a JSON containing both 'classification' and 'patch'.\n"
            "Classification Rules:\n"
            "1. input_type: greeting | system_question | editing_instruction | editing_feedback | confirmation | complaint_or_confusion | proposal_request | unknown\n"
            "2. needs_story_patch: true if the user is giving editing instructions or feedback.\n"
            "3. reply_type: greeting | explain_role | acknowledge | clarify | fallback\n"
            "4. short_reply: A concise response to the user in Korean.\n"
            "Patch Rules:\n"
            "1. Only provide a detailed patch if needs_story_patch is true.\n"
            "2. tone: natural | fast | slow | emotional\n"
            "3. target_length: short | medium | long\n"
        )
        
        prompt = f"{system_prompt}\nUser message: '{user_message}'\n\nJSON:"
        
        # Combined JSON Schema
        schema = {
            "type": "object",
            "properties": {
                "classification": {
                    "type": "object",
                    "properties": {
                        "input_type": { "type": "string" },
                        "confidence": { "type": "number" },
                        "needs_story_patch": { "type": "boolean" },
                        "reply_type": { "type": "string" },
                        "short_reply": { "type": "string" },
                        "reason": { "type": "string" }
                    },
                    "required": ["input_type", "confidence", "needs_story_patch", "reply_type", "short_reply", "reason"]
                },
                "patch": {
                    "type": "object",
                    "properties": {
                        "patch_type": { "type": "string" },
                        "tone": { "type": "string" },
                        "target_length": { "type": "string" },
                        "must_keep": { "type": "array", "items": { "type": "string" } },
                        "avoid": { "type": "array", "items": { "type": "string" } },
                        "reason": { "type": "string" }
                    },
                    "required": ["patch_type", "tone", "target_length", "must_keep", "avoid", "reason"]
                }
            },
            "required": ["classification", "patch"]
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
                "num_predict": 512
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
                    data = json.loads(self._clean_json(raw_res))
                    clf_data = data.get("classification", {})
                    patch_data = data.get("patch", {})
                    
                    return NarrativeLLMResult(
                        status=NarrativeLLMStatus.OK,
                        classification=ConversationIntent.from_dict(clf_data),
                        patch=StoryIntentPatch.from_dict(patch_data) if clf_data.get("needs_story_patch") else None,
                        latency_ms=latency,
                        raw_response=raw_res,
                        thinking=thinking
                    )
                elif validate_narrative_contract(thinking):
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
                        error_message="Could not parse valid Narrative Combined JSON from LLM output."
                    )

        except urllib.error.URLError as e:
            if "timed out" in str(e).lower():
                return NarrativeLLMResult(status=NarrativeLLMStatus.MODEL_CALL_TIMEOUT, error_message=str(e))
            return NarrativeLLMResult(status=NarrativeLLMStatus.OLLAMA_NOT_RUNNING, error_message=str(e))
        except Exception as e:
            return NarrativeLLMResult(status=NarrativeLLMStatus.MODEL_CALL_FAILED, error_message=str(e))

    def get_free_conversation(self, user_message: str) -> Dict[str, Any]:
        """
        Experimental Free Conversation Mode for R10-H-R2 Probe.
        Returns a dict containing natural reply, intent, and optional patch.
        """
        url = f"{self.base_url}/api/generate"
        
        system_prompt = (
            "You are a professional video editor and narrative consultant named CCUT AI.\n"
            "Be conversational, helpful, and natural.\n"
            "Analyze the user message and provide a JSON response.\n"
            "Rules:\n"
            "1. reply: Natural language response in Korean.\n"
            "2. intent_type: greeting | system_question | complaint | editing_instruction | editing_feedback | confirmation | unknown\n"
            "3. needs_story_patch: true if the user is giving editing instructions or feedback.\n"
            "4. story_patch: Provide StoryIntentPatch if needs_story_patch is true. Otherwise empty object.\n"
            "5. requires_user_confirmation: true if the intent is a significant editing change.\n"
        )
        
        schema = {
            "type": "object",
            "properties": {
                "reply": { "type": "string" },
                "intent_type": { "type": "string" },
                "needs_story_patch": { "type": "boolean" },
                "story_patch": {
                    "type": "object",
                    "properties": {
                        "patch_type": { "type": "string" },
                        "tone": { "type": "string" },
                        "target_length": { "type": "string" },
                        "must_keep": { "type": "array", "items": { "type": "string" } },
                        "avoid": { "type": "array", "items": { "type": "string" } },
                        "reason": { "type": "string" }
                    }
                },
                "requires_user_confirmation": { "type": "boolean" },
                "reason": { "type": "string" }
            },
            "required": ["reply", "intent_type", "needs_story_patch", "story_patch", "requires_user_confirmation", "reason"]
        }

        payload = {
            "model": self.model,
            "prompt": f"{system_prompt}\nUser message: '{user_message}'\n\nJSON:",
            "stream": False,
            "think": False,
            "format": schema,
            "options": { "temperature": 0, "num_predict": 512 }
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                resp_data = json.loads(response.read().decode())
                raw_res = resp_data.get("response", "")
                return json.loads(self._clean_json(raw_res))
        except Exception as e:
            return {"error": str(e), "status": "FAILED"}

    def _clean_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text.split("```json")[1].split("```")[0].strip()
        elif text.startswith("```"):
            text = text.split("```")[1].split("```")[0].strip()
        return text
