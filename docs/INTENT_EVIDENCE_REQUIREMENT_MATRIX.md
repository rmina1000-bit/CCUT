# Intent & Evidence Requirement Matrix

This document provides a matrix mapping user editing intents to their necessary metadata signals, current database feasibility, and implementation status.

---

## Intent Feasibility Matrix

| User Intent | Required Evidence Signals | Feasibility Status | Limitation & Evaluation |
| :--- | :--- | :---: | :--- |
| **더 빠르게 (fast_pace)** | Scene change cuts, Candidate duration boundaries, Audio energy peaks. | **POSSIBLE** | Can be calculated using micro candidate duration and scene change points. Confirmed to reduce clip lengths. |
| **여러 영상 골고루 (balanced_sources)** | Source ID mapping, Parent block ID, temporal offsets. | **POSSIBLE** | Runs dynamic penalties against parent/source frequency. Project-level multi-source solver is operational. |
| **말/대화 중심 (speech_human)** | ASR transcripts, Word-level timestamps, Voice Activity Detection (VAD). | **PARTIAL** | Only functions on sources with non-empty Whisper segments. Currently, only 4 out of 28 database sources contain text. |
| **사람 중심 visual (visual_human)** | YOLO person detection bounding boxes, FaceNet facial boxes, speaker identities. | **DATA_INSUFFICIENT** | Missing database columns and detection results. Handled as an exception due to lack of visual data. |
| **풍경 줄임 (reduce_scenery)** | YOLO nature/outdoor class tags, Scenery CNN classification. | **WEAK_EFFECT** | Inferred weakly through the absence of speech and motion, yielding poor scenery filtering. |
| **하이라이트 / motion** | Optical flow intensity vectors, Audio peak levels, visual transition peaks. | **HOLD** | Blocked due to database-wide collapsed `motion_score` (all values are `0.0000`). |

---

## Key Matrix Conclusion

Due to collapsed motion scores and absent visual object logs, any intent that relies on visual character tracking or motion highlight rendering is placed on **HOLD**. The system will report `DATA_INSUFFICIENT` or `WEAK_EFFECT` for these intents until the visual worker pipelines are integrated.
