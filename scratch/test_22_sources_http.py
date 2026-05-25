import json
import requests
import time

payload = {
    "project_id": "proj_1779591776013",
    "source_ids": [
        'SRC_12C414A7', 'SRC_CB9107CA', 'SRC_B4F09612', 'SRC_0BE783EC',
        'SRC_AA6C87D2', 'SRC_B669588A', 'SRC_2BE80EE2', 'SRC_6F5DEBE2',
        'SRC_634C81D9', 'SRC_9E3E3C7B', 'SRC_B85F1985', 'SRC_EFDBBCFC',
        'SRC_83B87D21', 'SRC_901671A7', 'SRC_563A1B48', 'SRC_F2CFC4DC',
        'SRC_1435727E', 'SRC_E8F4845B', 'SRC_8E415949', 'SRC_616AEFBA',
        'SRC_D5BD47B6', 'SRC_B1A26714'
    ],
    "target_length": 60.0,
    "user_intent": {
        "coverage": "balanced_sources",
        "instruction_text": "골고루",
        "tone": "energetic",
        "target_length": 60.0
    }
}

print("Sending HTTP request to backend /proposals/project...")
try:
    t0 = time.time()
    response = requests.post("http://127.0.0.1:8000/proposals/project", json=payload, timeout=120)
    t1 = time.time()
    print(f"Status Code: {response.status_code} (took {t1-t0:.2f}s)")
    if response.status_code == 200:
        data = response.json()
        with open("scratch/http_22_sources_output.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Success! Response saved to scratch/http_22_sources_output.json")
    else:
        print("Failed:", response.text)
except Exception as e:
    print("Request error:", e)
