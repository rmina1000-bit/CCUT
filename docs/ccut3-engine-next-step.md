# 📦 CCUT3_CODEX_MASTER_PACK

(복붙 가능한 블록 단위 / 파일별 구분 / 바로 사용 가능)

---

## PART 1 – SYSTEM CONTEXT & GLOBAL RULES

===== FILE: SYSTEM_OVERVIEW.md =====

```md
# CCUT3 System Overview

CCUT3 is a decision-centric video editing architecture.

It is NOT:
- a timeline editor
- an auto-edit AI
- a generative video tool

It IS:
- a decision logging system
- an event-sourced state machine
- a deterministic replay-based architecture
- a lazy rendering contract engine

Core Principles:
1. Decision Sovereignty (user commit only)
2. Event Truth Model (DECISION_COMMIT is truth)
3. Replay Determinism
4. Lazy Execution
5. Fail-Silent
6. Optional Cognitive Modules (never core-bound)

Input Methods:
- Natural language chat
- Pointer selection

No:
- Auto commit
- Balloon UI
- Distributed GPU nodes (Phase 1–2 local only)
```

---

## PART 2 – DIRECTORY STRUCTURE

===== FILE: DIRECTORY_STRUCTURE.txt =====

```txt
ccut_core/
 ├── main.py
 ├── config.py
 ├── infrastructure/
 │    ├── gpu_manager.py
 │    ├── model_loader.py
 │    └── cleanup.py
 │
 ├── archive/
 │    ├── aoid.py
 │    ├── archive_manager.py
 │    └── hash_utils.py
 │
 ├── ingestion/
 │    └── upload_handler.py
 │
 ├── segmentation/
 │    └── segment_engine.py
 │
 ├── engine3/
 │    ├── decision_log.py
 │    ├── event_types.py
 │    ├── replay.py
 │    ├── draft_manager.py
 │    └── state_machine.py
 │
 ├── proposal/
 │    └── dual_proposal.py
 │
 ├── render/
 │    ├── contract.py
 │    └── render_engine.py
 │
 └── optional/
      └── emotion2/
           ├── emotion_api.py
           ├── emotion_engine.py
           └── emotion_worker.py
```

---

## PART 3 – DECISION EVENT SCHEMA

===== FILE: EVENT_SCHEMA.json =====

```json
{
  "event_id": "uuid",
  "timestamp": "ISO8601",
  "aoid": "uuid",
  "event_type": "ENUM",
  "payload": {},
  "previous_hash": "sha256",
  "event_hash": "sha256"
}
```

===== FILE: EVENT_TYPES.md =====

```md
# Decision Event Types

USER_UTTERANCE
POINTER_SELECTION
UI_ACTION
DECISION_COMMIT
UNDO
REDO
```

===== FILE: SAMPLE_DECISION_LOG.json =====

```json
[
  {
    "event_id": "e1",
    "timestamp": "2026-02-01T10:00:00Z",
    "aoid": "aoid-123",
    "event_type": "USER_UTTERANCE",
    "payload": {
      "text": "Cut the intro shorter"
    },
    "previous_hash": "",
    "event_hash": "hash1"
  },
  {
    "event_id": "e2",
    "timestamp": "2026-02-01T10:01:00Z",
    "aoid": "aoid-123",
    "event_type": "DECISION_COMMIT",
    "payload": {
      "segments": [
        {"start": 0.0, "end": 5.2}
      ],
      "version": "v1"
    },
    "previous_hash": "hash1",
    "event_hash": "hash2"
  }
]
```

---

## PART 4 – UPLOAD FLOW SPEC

===== FILE: UPLOAD_FLOW.md =====

```md
# Upload Flow

Steps:
1. Receive file
2. Generate AOID
3. Compute source_video_hash
4. Create archive directory
5. Create initial draft
6. Initialize decision_log.json

Constraints:
- Do NOT call Emotion module
- Do NOT call Proposal module
- No auto segmentation
- Return aoid in response
```

---

## PART 5 – AOID & HASH

===== FILE: AOID_SPEC.md =====

```md
AOID:
- UUID v4
- Immutable
- Bound to source_video_hash

Storage:
storage/archive/{aoid}/
storage/decisions/{aoid}/
storage/drafts/{aoid}/
```

---

## PART 6 – REPLAY SPEC

===== FILE: REPLAY_SPEC.md =====

```md
Replay Procedure:

1. Load decision_log.json
2. Sort events by timestamp
3. Apply sequentially
4. Reconstruct state
5. Verify hash chain integrity
6. Compare final state hash

If mismatch:
- Raise error
- Invalidate state
```

---

## PART 7 – EMOTION2 ISOLATION RULES

===== FILE: EMOTION_ISOLATION.md =====

```md
Emotion2 Module Rules:

- Must not be imported in main.py
- Must not be called in upload flow
- Must not block core execution
- Runs only via /optional/emotion/{aoid}

Failure policy:
- Silent fail
- No state corruption
```

---

## PART 8 – RENDER CONTRACT SPEC

===== FILE: RENDER_CONTRACT.json =====

```json
{
  "aoid": "uuid",
  "decision_hash": "sha256",
  "source_video_hash": "sha256",
  "render_params": {
    "resolution": "1080p",
    "codec": "h264"
  }
}
```

---

## PART 9 – REQUIREMENTS

===== FILE: REQUIREMENTS.txt =====

```txt
fastapi
uvicorn
pydantic
python-multipart
hashlib
uuid
```

---

## PART 10 – CODEX INSTRUCTION BLOCK

===== FILE: CODEX_INSTRUCTION.txt =====

```txt
Using the provided architecture specs and schema files:

Generate:
1. engine3 core modules
2. decision_log implementation
3. event_types enum
4. replay engine
5. draft manager
6. upload handler
7. render contract module
8. emotion2 isolated module

Requirements:
- Follow event sourcing strictly
- Implement hash chain validation
- No auto commit
- No emotion binding in core
- Provide unit tests

Output code only.
```

---

## 사용 방법
1. 위 블록들을 파일로 저장하거나
2. 한 번에 Codex에 붙여넣거나
3. 여러 번 나눠 넣어도 됨

Codex는 이 패키지를 기준으로 완전한 엔진 코드베이스를 생성할 수 있습니다.
