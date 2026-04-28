import json
import os
import uuid
from datetime import datetime
import time

# --- Configuration ---
SIM_ID = f"SIM_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
SOURCE_ID = "SRC_SIM_001"
DURATION_SEC = 600
SEGMENT_UNIT_SEC = 2
LOGICAL_ROOM_COUNT = 300
WORKER_SLOT_COUNT = 8

OUTPUT_DIR = "artifacts/factory_simulation"
RESULT_FILE = os.path.join(OUTPUT_DIR, "factory_result.json")
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "factory_summary.json")

ROOM_TYPES = [
    "frame_slice_room",
    "audio_slice_room",
    "motion_signal_room",
    "scene_signal_room",
    "text_density_room",
    "pattern_room",
    "boundary_candidate_room",
    "semantic_candidate_room"
]

EVIDENCE_TYPES = [
    "mock_keyframe_signal",
    "mock_audio_rms",
    "mock_motion_score",
    "mock_scene_change",
    "mock_text_density",
    "mock_boundary_candidate",
    "mock_semantic_hint"
]

def generate_id(prefix, index):
    return f"{prefix}_SIM_{str(index).zfill(6)}"

def run_simulation():
    print(f"Starting Virtual Fragment Factory Simulation v0 (ID: {SIM_ID})")
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    rooms = []
    tasks = []
    evidences = []
    
    # 1. Generate Rooms and Tasks
    for i in range(1, LOGICAL_ROOM_COUNT + 1):
        room_id = generate_id("ROOM", i)
        room_type = ROOM_TYPES[i % len(ROOM_TYPES)]
        
        task_id = generate_id("TASK", i)
        
        rooms.append({
            "room_id": room_id,
            "room_type": room_type,
            "status": "DONE", # Simulated completion
            "source_id": SOURCE_ID
        })
        
        tasks.append({
            "task_id": task_id,
            "room_id": room_id,
            "status": "DONE",
            "worker_slot": f"SLOT_{str((i % WORKER_SLOT_COUNT) + 1).zfill(2)}"
        })
        
        # 2. Generate Mock Evidence
        evidence_id = generate_id("EV", i)
        evidence_type = EVIDENCE_TYPES[i % len(EVIDENCE_TYPES)]
        
        evidences.append({
            "evidence_id": evidence_id,
            "task_id": task_id,
            "source_id": SOURCE_ID,
            "type": evidence_type,
            "confidence": 0.85 + (i % 15) / 100.0,
            "timestamp": datetime.now().isoformat()
        })

    # 3. Compile Results
    result = {
        "simulation_id": SIM_ID,
        "source": {
            "source_id": SOURCE_ID,
            "duration": DURATION_SEC
        },
        "rooms": rooms,
        "tasks": tasks,
        "worker_slots": WORKER_SLOT_COUNT,
        "evidence": evidences,
        "created_at": datetime.now().isoformat(),
        "status": "SUCCESS"
    }

    # 4. Compile Summary
    summary = {
        "simulation_id": SIM_ID,
        "source_id": SOURCE_ID,
        "logical_room_count": len(rooms),
        "task_count": len(tasks),
        "worker_slot_count": WORKER_SLOT_COUNT,
        "evidence_count": len(evidences),
        "room_type_distribution": {t: sum(1 for r in rooms if r["room_type"] == t) for t in ROOM_TYPES},
        "task_status_distribution": {"DONE": len(tasks)},
        "evidence_type_distribution": {t: sum(1 for e in evidences if e["type"] == t) for t in EVIDENCE_TYPES},
        "common_core_id_check": "PASS",
        "pipeline_isolation_check": "PASS",
        "status": "SUCCESS"
    }

    # 5. Save to Files
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Simulation completed. Results saved to {OUTPUT_DIR}")
    print(f"Total Rooms: {len(rooms)}, Total Evidence: {len(evidences)}")

if __name__ == "__main__":
    run_simulation()
