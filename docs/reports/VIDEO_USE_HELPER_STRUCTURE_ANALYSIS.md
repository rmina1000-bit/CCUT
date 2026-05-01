# Analysis: video-use Helper Structure & Data Flow

## 1. Core Helpers in video-use

| Helper | Primary Responsibility | Key Feature |
| :--- | :--- | :--- |
| `pack_transcripts.py` | Markdown EDL Generation | Merges multiple source transcripts into a single formatted MD file for the AI editor. |
| `render.py` | Range-based Rendering | Processes JSON EDL and handles multi-stage FFmpeg (extract -> concat). |
| `timeline_view.py` | Frame-accurate Verification | Generates grid views of frames around specific timestamps for boundary validation. |
| `transcribe.py` | ASR & Metadata Extraction | Converts audio to text with precise millisecond timestamps. |

## 2. Data Flow (Transcript → EDL → Render)

1.  **Inventory Stage**: Gathering metadata (`ffprobe`) and transcripts.
2.  **Packing Stage**: Creating a Single Source of Truth (SSOT) Markdown file where each sentence is prefixed with its source and timestamp (e.g., `[00:05.12]`).
3.  **Editing Stage**: The AI Editor agent consumes the Markdown and outputs a **Time Range based JSON EDL**.
    ```json
    {
      "ranges": [
        {"source": "A.mp4", "start": 5.12, "end": 8.45},
        {"source": "B.mp4", "start": 12.0, "end": 15.5}
      ]
    }
    ```
4.  **Rendering Stage**:
    - **Extraction**: Each range is extracted to a temporary clip (`seg_00.mp4`, `seg_01.mp4`).
    - **Concatenation**: Temporary clips are merged using the `concat demuxer` for lossless joining.
    - **Post-processing**: Subtitles and overlays are added to the final merged file.

## 3. Analysis of Key Questions

- **Intermediate IDs (Proposal ID)?**: **No.** `video-use` bypasses abstract IDs during export, relying entirely on **Source Name + Time Range**.
- **Clip Identification?**: Uses **Time Ranges** directly.
- **Duplicate Key Prevention?**: UI issues are avoided because the "Edit List" is just an ordered array. Render-side collisions are avoided by using **sequential index numbering** (`seg_00`, `seg_01`) for intermediate files.
- **Session Memory?**: Managed via `project.md` which stores the state of the timeline and editor decisions.

## 4. Recommendations for CCUT

### What to Adopt (Heuristics)
- **Positional Key Rule**: Adopt the `proposalId + index + fragment_uid` pattern (already implemented in STEP 10-I.2) to prevent React key collisions.
- **Range-based ExportInput**: Transition the `ExportInput` format to be strictly **Time Range + Source Path** centric, reducing dependence on transient `fragment_id`s at the point of rendering.
- **Segmented Rendering**: Consider extracting individual clips before merging. This prevents "audio pops" (by allowing per-clip fades) and ensures better handling of varying source codecs.

### What to Avoid
- **Total ID Removal**: CCUT's DB depends on `fragment_id` for intelligence (hook scores, roles). Do not discard IDs in the database, but **de-couple** them from the final render instruction.
- **Markdown-only EDL**: CCUT's GUI requires a structured JSON object for state management; do not move to a pure text-based EDL.

## 5. Insight for STEP 10-I.2 Resolver/Export Issues

The current "clips missing" or "duplicate key" issues in CCUT stem from a mismatch between the **logical fragment** (managed by ID) and the **physical clip** (on the timeline). 

**Recommendation**:
1.  Use the `stable_key` (positional) for all UI rendering.
2.  In `export_engine.py`, convert the matched fragments into a **Physical EDL** (source_path, start, end) immediately. This ensures that even if fragments are renamed or re-fragmented in the future, the render instructions remain immutable and based on absolute time.
