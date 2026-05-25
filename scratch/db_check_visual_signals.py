import sqlite3
import json

db_path = "ccut_backend/ccut_app.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Examine metadata_json in evidence_board
cursor.execute("SELECT source_id, metadata_json, worker_sources, text, speaker FROM evidence_board;")
rows = cursor.fetchall()

print("Checking evidence_board for visual tags...")
metadata_keys = set()
worker_keys = set()
speakers = set()
non_empty_metadata_samples = []

for sid, meta_str, worker_str, text, spk in rows:
    if spk:
        speakers.add(spk)
    meta = json.loads(meta_str) if meta_str else {}
    worker = json.loads(worker_str) if worker_str else {}
    
    for k in meta.keys():
        metadata_keys.add(k)
    for k in worker.keys():
        worker_keys.add(k)
        
    # Check if there are keys containing human, face, person, yolo, visual, objects
    for k in meta.keys():
        if any(x in k.lower() for x in ["face", "person", "human", "yolo", "visual", "object", "detect"]):
            non_empty_metadata_samples.append((sid, k, meta[k]))
            
    # Check inside meta nested structures
    for k, v in meta.items():
        if isinstance(v, dict):
            for nk in v.keys():
                if any(x in nk.lower() for x in ["face", "person", "human", "yolo", "visual", "object", "detect"]):
                    non_empty_metadata_samples.append((sid, f"{k}.{nk}", v[nk]))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    for nk in item.keys():
                        if any(x in nk.lower() for x in ["face", "person", "human", "yolo", "visual", "object", "detect"]):
                            non_empty_metadata_samples.append((sid, f"{k}[].{nk}", item[nk]))

print(f"Distinct speakers found: {speakers}")
print(f"Evidence board metadata top-level keys: {metadata_keys}")
print(f"Worker sources keys: {worker_keys}")
print(f"Visual-related metadata sample matches: {len(non_empty_metadata_samples)}")
for sample in non_empty_metadata_samples[:10]:
    print(f"  Source: {sample[0]} | Key: {sample[1]} | Value: {str(sample[2])[:150]}")

# Also check fragments intelligence keys
cursor.execute("SELECT source_id, intelligence FROM fragments;")
frag_rows = cursor.fetchall()
intel_keys = set()
for sid, intel_str in frag_rows:
    intel = json.loads(intel_str) if intel_str else {}
    for k in intel.keys():
        intel_keys.add(k)
        
print(f"\nFragments intelligence keys: {intel_keys}")

conn.close()
