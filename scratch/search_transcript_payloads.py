import json

path = "C:/Users/rmina/.gemini/antigravity/brain/6e43bff5-efdc-4c1e-9554-03b6df10a09a/.system_generated/logs/transcript.jsonl"

with open(path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        try:
            data = json.loads(line)
            # Check if this step has tool calls
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                args_str = tc.get("args", {}).get("CommandLine", "")
                if "proposals/project" in args_str or "source_ids" in args_str:
                    print(f"Step {data.get('step_index')}: {args_str[:300]}")
            
            # Check content for source_ids or proposals/project
            content = data.get("content", "")
            if "proposals/project" in content and "source_ids" in content:
                print(f"Step {data.get('step_index')} (Content): {content[:300]}")
        except Exception as e:
            pass
