# CCUT Engine Development Constitution v1.0

---

## Preamble

CCUT (Creative Cut) is a deterministic, append-only video fragment editing system.
Every decision made by the user is recorded, replayable, and auditable.
This document defines the absolute rules governing all engine and UI development.
All future work directives must comply with this constitution.

---

## Part I — Core Principles

### 1. Append-Only Log

- `storage/decision_log.jsonl` is the single source of truth for all user editing decisions.
- Existing entries must never be modified, deleted, truncated, or overwritten.
- All writes use `open("a")` mode exclusively.
- Every entry carries a monotone `seq` integer that persists across server restarts.
- Thread safety is enforced via a module-level lock on all write operations.

### 2. Deterministic Replay

- Given the same `decision_log.jsonl`, `replay()` and `replay_until(seq)` must always produce the same result.
- No randomness, no timestamps, no external state may influence replay output.
- Replay must never raise; all malformed entries are silently skipped.
- `replay_until(seq)` uses the nearest snapshot as a base, then applies delta events only.

### 3. Engine / UI Separation

- Engine code lives in `ccut_core/`.
- UI code lives in `ui/`.
- Engine and UI must never be modified in the same commit (development guideline).
- The following engine-core files are protected from casual modification:
  - `ccut_core/decision_log.py`
  - `ccut_core/verify_engine.py`

### 4. No AI Usage in Deterministic Paths

- All fragment generation, proposal scoring, and replay logic must be deterministic.
- AI / ML model calls are forbidden in any path that affects `decision_log.jsonl` content.
- Scoring functions use explicit, inspectable arithmetic only (e.g. `duration + positional_bias`).

### 5. Single State Update on Drop

- During any drag interaction (boundary drag, fragment reorder), React state must not be updated.
- Direct DOM manipulation (`style.transform`, `style.left`, etc.) is the only permitted technique during drag.
- A single `setFragments()` call is issued on `mouseup`/drop.
- HTML5 Drag API is forbidden in all interactive components.

---

## Part II — Engine Architecture

### 2.1 Decision Log Schema

Each entry in `decision_log.jsonl` is a single-line JSON object:

```json
{
  "seq":       1,
  "type":      "FRAGMENTS_GENERATED",
  "timestamp": 1741010000.0,
  "payload":   { "count": 12 }
}
```

Fields:
- `seq`       — monotone integer, 1-indexed, never reused
- `type`      — one of the registered event type constants
- `timestamp` — Unix epoch float (informational only, not used in replay)
- `payload`   — event-specific data dict

### 2.2 Registered Event Types

| Type | Trigger |
|------|---------|
| `FRAGMENTS_GENERATED` | Backend fragment generation complete |
| `BOUNDARY_ADJUSTED`   | User drags a fragment boundary (mouseup) |
| `FRAGMENTS_REORDERED` | User drag-drops a fragment to a new position |
| `PROPOSAL_GENERATED`  | Backend A/B proposal generation complete |
| `PROPOSAL_SELECTED`   | User selects Proposal A or Proposal B |

New event types may only be added; existing types must not be renamed or removed.

### 2.3 Replay Engine

```
edit_log/replay_engine.py
  replay()          — full replay from seq 1 to end
  replay_until(N)   — snapshot-accelerated replay to seq N
  read_log_from(N)  — generator yielding entries with seq >= N
  summarize()       — aggregate statistics (read-only)
```

Internal state format (private to replay_engine):
```python
{
  "fragments":      list,
  "order":          list[str],
  "events_count":   int,
  "last_event_seq": int | None,
  "_frag_map":      dict[str, dict]  # stripped before public return
}
```

### 2.4 Snapshot Store

- Snapshots are written to `storage/snapshots/snapshot_seq_{N}.json`.
- A snapshot is written when `seq % SNAPSHOT_INTERVAL == 0` (default: 200).
- Existing snapshots are never overwritten.
- Write is atomic: write to `.tmp` then `os.replace`.
- Snapshots include `_frag_map` for O(1) boundary updates on load.

### 2.5 Undo Engine

```
edit_log/undo_engine.py
  UndoEngine.undo()               → replay_until(active_seq - 1)
  UndoEngine.redo()               → replay_until(active_seq + 1)
  UndoEngine.commit_hook(seq, state)  → reset cursor, trigger snapshot
  get_undo_engine()               → process-level singleton
```

Undo / redo modifies `active_seq` in memory only. The log is never mutated.
When a new event arrives while `active_seq < current_seq`, the redo branch is
discarded in memory; the log remains untouched.

### 2.6 Proposal Engine

```
proposal_engine/proposal_engine.py
  generate_proposals(fragments) → {"A": [id, ...], "B": [id, ...]}
```

- Always returns exactly 2 proposals.
- Proposal A: original order, fragments ≤ 3.0 s removed.
- Proposal B: duration-weighted interleave (top 50% ↔ bottom 50%).
- A ≠ B guaranteed when input is non-trivial (last two swapped if identical).
- Previous proposals are never stored; each call is fully stateless.

---

## Part III — UI Architecture

### 3.1 Fragment Data Model

```typescript
interface Fragment {
  id:        string;
  start:     number;   // seconds
  end:       number;   // seconds
  duration:  number;   // seconds (= end - start)
  editStack: any[];    // preserved across all reorder operations
  src?:      string;   // object URL, set after video upload
}
```

Fragment `start`, `end`, and `editStack` must never be modified during reorder.
Only the array order is changed on drop.

### 3.2 Hover Playback Engine

- Lives in `ui/context/VideoContext.js`.
- Exposes `hoverPlay`, `hoverStop`, `setHoverEnabled`, `hoverEnabledRef`.
- Must be disabled (`setHoverEnabled(false)`) at the start of any drag interaction.
- Must be re-enabled (`setHoverEnabled(true)`) in the `mouseup` / drop handler.
- No direct calls to `hoverPlay` during drag.

### 3.3 Drag Interaction Rules

**Fragment Boundary Drag (OriginalPanorama):**
- `mousedown` on a `BoundaryHandle` → capture rect, disable hover, attach window listeners.
- `mousemove` → direct DOM style updates only (`style.left`, `style.width`).
- `mouseup` → compute new boundary time, clamp to `MIN_GAP = 0.8 s`, call `onFragmentsChange` once, log `BOUNDARY_ADJUSTED`, restore hover.
- No React state updates during drag.

**Fragment Reorder Drag (EditStructureBox):**
- `mousedown` on a fragment row → record rects (single pass, no layout thrash).
- `mousemove` (threshold ≥ 4 px) → create ghost clone (`position: fixed`, `z-index: 9999`), apply `translateY` to siblings.
- `mouseup` → remove ghost, restore transforms, compute drop index, splice array, call `setFragments` once, log `FRAGMENTS_REORDERED`, restore hover.
- HTML5 drag API is forbidden.
- Ghost element uses `will-change: transform` for GPU compositing.

### 3.4 Proposal Panel

- `[⚡ Generate A/B]` button: discards existing proposals unconditionally, calls `POST /generate-proposals`, renders A and B cards.
- `[✓ Select X]` button: reorders fragments by proposal ID list, calls `onFragmentsChange` once, logs `PROPOSAL_SELECTED`, clears proposal state.
- No more than 2 proposals may be displayed at any time.
- No partial reuse of previous proposals.

### 3.5 Event Logging (UI → Backend)

All UI events are fire-and-forget via `ui/utils/logEvent.js`:
```javascript
logEvent(type, payload)  // POST /append-event, catch(() => {})
```
UI must never block on log writes. UI must never crash if the backend is unreachable.

---

## Part IV — API Contract

### 4.1 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate-fragments` | Upload video, return fragment list |
| POST | `/generate-proposals` | Return A/B proposals for given fragments |
| POST | `/append-event`       | Append one event to decision log (202) |
| GET  | `/decision-log`       | Return recent log entries |
| GET  | `/decision-replay`    | Return reconstructed current state |
| GET  | `/decision-summary`   | Return aggregate statistics |

### 4.2 CORS

Allowed origins: `localhost:3000`, `localhost:3001`, `127.0.0.1:3000`, `127.0.0.1:3001`.

### 4.3 Response Stability

- `POST /append-event` returns `202 Accepted` immediately; processing is synchronous server-side but the response must never block the UI.
- `GET /decision-replay` and `GET /decision-summary` are read-only and never mutate state.

---

## Part V — Forbidden Patterns

The following patterns are absolutely forbidden in all CCUT code:

1. **Overwrite / truncate** any line in `decision_log.jsonl`.
2. **Modify** `fragment.start`, `fragment.end`, or `fragment.editStack` during a reorder operation.
3. **Continuous React state updates** during drag (re-renders per mousemove tick).
4. **HTML5 Drag API** (`draggable`, `ondragstart`, `ondragover`, `ondrop`).
5. **AI / ML model calls** in deterministic engine paths.
6. **Polling** the backend from UI components on a timer.
7. **More than 2 proposals** generated or displayed simultaneously.
8. **Reuse of previous proposals** (each generate call is independent).
9. **Layout thrashing** (interleaved reads and writes to DOM geometry during drag).
10. **Synchronous blocking** of the UI thread on log writes or API calls.

---

## Part VI — File Structure

```
d:\CCUT 1.0.1\
├── ccut_core\
│   ├── api\
│   │   ├── __init__.py
│   │   └── fragment_api.py
│   ├── edit_log\
│   │   ├── __init__.py
│   │   ├── edit_log.py
│   │   ├── replay_engine.py
│   │   ├── snapshot_store.py
│   │   ├── undo_engine.py
│   │   └── verify_edit_log.py
│   ├── proposal_engine\
│   │   ├── __init__.py
│   │   ├── proposal_engine.py
│   │   └── proposal_api.py
│   ├── storage\
│   │   ├── decision_log.jsonl      ← append-only
│   │   └── snapshots\
│   │       └── snapshot_seq_*.json
│   ├── decision_log.py             ← ENGINE PROTECTED
│   └── verify_engine.py            ← ENGINE PROTECTED
├── ccut_ui\
│   └── app\
│       └── server.py
├── ui\
│   ├── App.jsx
│   ├── context\
│   │   └── VideoContext.js
│   ├── layout\
│   │   └── MainLayout.jsx
│   ├── right\
│   │   ├── RightPanel.jsx
│   │   ├── OriginalPanorama.jsx
│   │   ├── EditStructureBox.jsx
│   │   └── right.css
│   ├── components\
│   │   ├── VideoUploader.jsx
│   │   ├── ProposalPanel.jsx
│   │   └── DecisionSummary.jsx
│   └── utils\
│       └── logEvent.js
└── docs\
    └── constitution\
        ├── CCUT_ENGINE_CONSTITUTION_v1.0.md   ← this file
        └── CCUT_TASK_TEMPLATE.md
```

---

## Part VII — Development Mode Declaration

- **L2 Governance Pre-Commit Guard**: DISABLED (development mode)
- **Manual Verify**: ACTIVE — run `python -m ccut_core.edit_log.verify_edit_log` as needed
- **Append-Only Principle**: ALWAYS ACTIVE regardless of governance mode

---

## Ratification

Version: 1.0
Status: LOCKED
Date: 2026-03-05

> "CCUT is not just an editor. It is a decision recording system."
> Every fragment cut is a decision. Every decision is preserved.
