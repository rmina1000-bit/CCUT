import json
import urllib.request
import urllib.error
import time
from typing import List, Dict, Any, Optional

class OllamaProbeResult:
    OLLAMA_NOT_RUNNING = "OLLAMA_NOT_RUNNING"
    NO_MODEL_AVAILABLE = "NO_MODEL_AVAILABLE"
    MODEL_CALL_FAILED = "MODEL_CALL_FAILED"
    JSON_PARSE_FAILED = "JSON_PARSE_FAILED"
    PROBE_PASS = "PROBE_PASS"

def check_ollama_server(base_url: str = "http://127.0.0.1:11434") -> bool:
    """Check if Ollama server is running by calling the version endpoint."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, ConnectionRefusedError):
        return False

def list_ollama_models(base_url: str = "http://127.0.0.1:11434") -> List[str]:
    """Retrieve list of model names currently available in Ollama."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as response:
            data = json.loads(response.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except:
        return []

def call_ollama_generate_if_available(model: str, user_message: str, base_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    """Perform a limited generation call to verify the model is working."""
    url = f"{base_url}/api/generate"
    prompt = f"Please analyze this user request and return a JSON patch for narrative intent. User message: '{user_message}'"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return {"error": str(e)}

def parse_story_intent_candidate(response_text: str) -> Optional[Dict[str, Any]]:
    """Try to parse the response text as a StoryIntentPatch-like object."""
    try:
        return json.loads(response_text)
    except:
        return None
