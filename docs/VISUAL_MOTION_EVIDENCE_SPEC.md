# Visual & Motion Evidence Specification

This document details the architectural specifications for visual object tracking, human face tracking, and motion analysis metadata schemas in the CCUT local system.

---

## 1. Database Signal Bottlenecks

A comprehensive audit of the local database (`ccut_app.db`) exposes severe data insufficiency on visual and motion signals:
- **No Visual Evidence**: There is no object detection data, YOLO bounding box list, or face recognition metadata in the evidence log.
- **Motion Score Collapse**: The `motion_score` column in the `evidence_board` table evaluates to `0.0000` for every segment, indicating the optical flow engine was either not run or failed to save.
- **Sparse ASR Transcripts**: Whisper ASR transcripts are missing (`0` words) for 24 out of 28 source videos because they were flagged as silent or empty.
- **Scenery Weak Inference**: Currently, scenery detection is weakly inferred by calculating `1.0 - speech_score - motion_score`. Due to missing signals, scenery classification accuracy is very poor.

---

## 2. Proposed Metadata Evidence Schemas

To address these bottlenecks, the CCUT ingest pipeline must be enhanced to compute and write the following signals:

### A. Visual Objects (`visual_objects`)
Captures object classes and screen coordinates to isolate subjects from background elements.
- `class`: String name of object.
- `confidence`: Prediction probability.
- `box`: `[x_min, y_min, x_max, y_max]` relative bounding coordinates.

### B. Human & Face Presence (`human_presence` & `face_presence`)
Measures human visibility and face focus weights.
- `human_detected`: Boolean.
- `human_count`: Integer count.
- `human_ratio`: Percentage of screen area covered by human shapes.
- `face_detected`: Boolean.
- `faces`: Array of facial bounding boxes, expressions, and confidence scores.

### C. Motion & Audio Signals (`motion_intensity` & `audio_peak_db` & `scenery_score`)
- `motion_intensity`: Average frame-to-frame pixel displacements (Optical Flow vector magnitude).
- `audio_peak_db`: Maximum decibel energy spikes to isolate key audio highlights.
- `scenery_score`: Classifier probability score representing scenic content (outdoors, buildings, sky).
- `highlight_signal`: Compound metric combining `motion_intensity` and `audio_peak_db`.

---

## 3. Data Integration Pipeline Flow

The ingestion pipeline will process media through the following stages:

```
  Evidence Board (Raw worker metadata written per frame/segment)
  → Semantic Fragment (Averages signals over 20-second blocks for UI display)
  → Micro Candidate (Constructs 2-6s clips snapped to scene changes)
  → Visual/Speech/Motion score mapping (Lightweight scoring formulas)
  → Proposal (ProposalEngine selects candidates using intent weights)
```

---

## 4. Work Scope Warning

> [!WARNING]
> - Implementing backend YOLO, Face detectors, Optical Flow calculators, and Audio Peak analyzers is **strictly prohibited** in this phase.
> - These workers are scheduled for future design and implementation phases.
> - The database schema changes must **not** be written to the active database.
