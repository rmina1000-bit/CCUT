# YouTube Robot Learner System

This document outlines the architecture, algorithms, and privacy protection guidelines for the CCUT YouTube Robot Learner System.

---

## 1. System Topology

The robot operates as a background learning daemon that analyzes popular videos to refine edit proposal metrics:

```text
[Search Queries]
  ↳ YouTube Search Scraper
      ↳ Target Videos (Views > 100k)
          ↳ Dual-Mode Analyzer
              ├─ Metadata Mode (Subtitles, Pacing)
              └─ Media Mode (yt-dlp, scenedetect)
                  ↳ Scene Cuts & Audio Volumes
                      ↳ Pattern Translation (Success Weight updates in SQLite)
```

---

## 2. Dynamic Edit Analysis

### Visual Scene Cut Extraction (Media Mode)
When a video is downloaded using `yt-dlp` (limiting to a 30s preview), the robot executes `PySceneDetect` to identify cut timestamps:
- **Pacing Index**: $\text{Pacing} = \frac{\text{Preview Duration}}{\text{Scene Cuts Count}}$.
- If average scene length is $< 2.0$ seconds, it is flagged as a high-intensity cut pattern (e.g. tech review/travel vlog).

### Audio Continuity Analysis (RMS Volume)
- Volume spikes (above $0.75$ max) combined with subtitle transcripts containing laughter triggers the `reaction_hold` pattern.
- Long silent pauses (volume $< 0.15$ for $> 1.5$ seconds) trigger `breathing_multiplier` patterns.

---

## 3. Privacy Shield Guidelines

To protect user confidentiality, the robot:
- Never transmits raw local workspace video or project files to YouTube/external APIs.
- Uses general public query keywords ("travel vlog", "cinematic intro") without user session parameters.
- Uses public, non-authenticated scraping/search channels only.
