# Micro Candidate Layer Specification

This document defines the structural specifications for the **Micro Candidate Layer** in CCUT, detailing the split-level clip design, schema models, and caching strategies.

---

## 1. Limits of Coarse Semantic Fragments

In the current CCUT pipeline, the video is partitioned into coarse **Semantic Fragments** (typically 20 seconds). While this size is appropriate for visual timeline display and user comprehension in the UI, it presents severe limitations for AI proposal engines:
- **Mixed Content Context**: A single 20-second fragment often contains a mix of speech, silent gaps, panning scenic background, and highlight motion.
- **Binary Decision Bottleneck**: If the `ProposalEngine` attempts to prioritize "speech-only" or "motion-only" clips, it is forced to select or exclude the entire 20-second chunk. This binary logic leads to proposals that barely change in response to different user intents.

---

## 2. Visible vs Internal Candidate Separation Principle

To maintain a responsive UI while ensuring highly precise, intent-driven editing, CCUT splits the editing representations into two distinct layers:
1. **Visible Layer (Semantic Fragment)**: Placed on the Evidence Board and timeline for the user. These represent semantic topics and long-form narrative arcs.
2. **Internal Layer (Micro Candidate)**: Hidden from the user interface, these represent **2 to 6-second clips** parsed within the boundaries of the parent fragment. The ProposalEngine uses this micro layer to score, select, and combine clips dynamically.

---

## 3. Micro Candidate Data Schema

Each micro candidate is modeled using the following metadata fields:

| Field Name | Type | Description |
| :--- | :---: | :--- |
| `micro_candidate_id` | String | Unique identifier (e.g., `MC_SF_ABC123_001`). |
| `parent_semantic_fragment_id`| String | References the parent Semantic Fragment ID. |
| `source_id` | String | References the raw video source ID. |
| `start` | Float | Start time offset relative to raw video source (seconds). |
| `end` | Float | End time offset relative to raw video source (seconds). |
| `duration` | Float | Clip length (between 2.0 and 6.0 seconds). |
| `tags` | Array | Category tags representing detected scene features (e.g. `["Active Speech"]`). |
| `scores` | Object | Normalized intent evaluation scores mapping speech, scenery, motion, weak human voice, highlight, and filler coefficients. |
| `evidence_refs` | Array | References to the source `evidence_board` indices. |
| `confidence` | Float | Overall extraction quality coefficient. |

---

## 4. Cache & Re-scoring Strategy

To ensure sub-millisecond page responsiveness during clip regeneration:
- **No Repeated Analysis**: Micro candidates must be generated **exactly once** during the initial video ingestion and parsing phase. Running heavy analysis workers (Whisper, object detectors, optical flow) during intent regeneration is strictly forbidden.
- **Ingest-Time Caching**: The generated candidate boundaries and raw data signals are serialized and stored as cached arrays in the database (or JSON files).
- **Runtime Re-Scoring**: When the user requests a proposal update (e.g., "reduce scenery"), the ProposalEngine queries the cached micro candidates and runs a lightweight math-based scoring formula. 
- **Time Profiling**: Simulation tests confirm that runtime re-scoring and greedy solver loops on 48 candidates take less than **0.0004 seconds**, guaranteeing zero performance bottlenecks.

---

## 5. Integration Status

> [!IMPORTANT]
> The Micro Candidate Layer is currently under **HOLD** status. The ProposalEngine, database schema, and frontend systems have **not** been modified to integrate this architecture. Full integration is blocked pending visual/motion evidence ingestion.
