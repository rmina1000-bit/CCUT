# Learning Data & Privacy Policy Spec

This document details the boundaries of data storage and transmissions applied to the CCUT learning loop to secure user media assets.

---

## 1. Local Storage Guarantee
* **Video Files**: All original video files (`.mp4`, `.mov`, etc.) and extracted panorama frames remain strictly on the local workspace (`D:/CCUT1.0.4/ccut_backend/storage`). No raw media is transmitted.
* **Database Records**: User edit decisions, PBE adjustment lists, and preference scores are persisted locally in `ccut_app.db`.

---

## 2. External AI (Teacher AI) API Transmission Rules

To ensure privacy, the `TeacherAIEvaluator` acts as a privacy filter. Only non-personally identifiable metadata can be transmitted to external API providers:

### Allowed Payloads (Allowed ✅)
1. Condensed fragment transcripts (dialogue text only, free of names/IDs).
2. Segment duration tables and sequence order templates.
3. Human Reality Score metrics (e.g., visual comfort ratios).

### Restricted Payloads (Strictly Forbidden ❌)
1. Raw audio recordings or audio waveforms.
2. Raw video files, clip snippets, or thumbnail JPEG images.
3. User registration info, IP addresses, or project names containing private info.
