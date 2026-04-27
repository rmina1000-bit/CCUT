# CCUT — Developer Handoff Specification

> **Purpose**: Build-oriented UI specification for Codex implementation.
> **Generated from**: Working React/TypeScript prototype (Vite + Tailwind + framer-motion).
> **This is NOT a design summary. This is a build spec.**

---

## 1. LAYOUT SPECIFICATION

### 1.1 Screen Structure

```
┌──────┬─────────────────┬───┬────────────────────────────────────────┐
│      │                 │   │                                        │
│ Left │   Center        │ S │   Right Workspace                      │
│ Nav  │   Panel         │ p │                                        │
│      │                 │ l │  ┌──────────────────────────────────┐  │
│ 56px │  Resizable      │ i │  │ Original Panorama                │  │
│      │  min: 260px     │ t │  │ (source strip + tabs)            │  │
│      │  default: 340px │ t │  └──────────────────────────────────┘  │
│      │                 │ e │  ┌──────────────────────────────────┐  │
│      │                 │ r │  │ Fragment Map / Edit Structure    │  │
│      │                 │   │  │ (multi-row wrapping board)       │  │
│      │                 │ 6 │  │ flex-1, overflow-y: auto         │  │
│      │                 │ p │  └──────────────────────────────────┘  │
│      │                 │ x │  ┌──────────────────────────────────┐  │
│      │                 │   │  │ Hold Area                        │  │
│      │                 │   │  │ (freeform absolute positioned)   │  │
│      │                 │   │  │ min-h: 120px                     │  │
│      │                 │   │  └──────────────────────────────────┘  │
└──────┴─────────────────┴───┴────────────────────────────────────────┘
```

### 1.2 Column Definitions

| Region | Type | Width | Constraints |
|--------|------|-------|-------------|
| Left Nav | Fixed | 56px | `flex-shrink: 0` |
| Center Panel | Resizable | min 260px, default 340px | `flex-shrink: 0`, width set by inline style |
| Splitter | Fixed | 6px | `cursor: col-resize`, drag to resize |
| Right Workspace | Flexible | `flex: 1`, min 400px | `overflow: hidden`, `min-width: 0` |

### 1.3 Splitter Behavior

- Draggable vertical divider between Center and Right.
- On drag: `document.body.style.cursor = "col-resize"`, `userSelect = "none"`.
- Center width persisted to `localStorage` key `"ccut-center-width"`.
- Constraints: `max(260, min(totalWidth - leftNav - 400, mouseX - leftNav))`.
- Visual: 2px rounded pill, `bg-border/40` idle → `bg-primary/40` hover → `bg-primary/60` active. Pill height animates from 40px → 56px on hover → 64px active.

### 1.4 Right Workspace Internal Layout

```
flex flex-col gap-2 p-2 overflow-hidden min-w-0
```

Three sections stacked vertically:
1. **Original Panorama** — fixed height (~100px including header)
2. **Fragment Map** — `flex: 1`, `overflow-y: auto`
3. **Hold Area** — fixed min-height 120px

### 1.5 Elements That Must NOT Exist

- No traditional timeline ruler or scrubber
- No full-screen modals for editing
- No sequence minimap in the center column
- No text-based sequence list
- No pagination in the fragment board
- No dark mode toggle (entire app is dark-only)

---

## 2. COMPONENT MAP

### 2.1 Full Component Tree

```
Index (page root — src/pages/Index.tsx)
├── LeftNav
│   └── NavButton × N (inline, not extracted)
├── CenterPanel
│   ├── SourceSummaryCards (inline chips)
│   ├── SelectedFragmentDetail (conditional)
│   │   ├── FragmentThumbnailPreview
│   │   ├── MetadataGrid
│   │   ├── StructureContextText
│   │   └── IntelligenceMetrics (bar chart)
│   ├── RenderPreviewPlaceholder
│   └── ChatBar
├── VerticalSplitter (inline div)
└── RightWorkspace (inline div)
    ├── OriginalPanorama
    │   ├── SourceTabs (A–G buttons)
    │   ├── IntelligenceToggle
    │   └── PanoramaStrip (horizontal scroll)
    │       └── FragmentTile × N (variant="panorama")
    ├── FragmentMap
    │   ├── FragmentTile × N (variant="edit")
    │   ├── BoundaryHandle × N (between adjacent visible fragments)
    │   ├── SyntheticCollapsedSeam × N (between visible fragments with hidden excluded)
    │   ├── BoundaryRuler (frame offsets)
    │   └── BoundaryPrecisionOverlay (conditional, fixed-position portal)
    │       ├── OverlayFragmentCell × N (including excluded)
    │       ├── InternalBoundaryHandle × N
    │       └── OverlayFrameRuler
    └── ReservedFragments (Hold Area)
        └── FragmentTile × N (variant="reserved", absolutely positioned)
```

### 2.2 Component Details

| Component | File | Reusable | Interactive |
|-----------|------|----------|-------------|
| `Index` | `src/pages/Index.tsx` | No | Root state owner |
| `LeftNav` | `src/components/LeftNav.tsx` | No | Click nav items |
| `CenterPanel` | `src/components/CenterPanel.tsx` | No | Chat input, source chip click |
| `OriginalPanorama` | `src/components/OriginalPanorama.tsx` | No | Tab switch, fragment click, scroll |
| `FragmentMap` | `src/components/FragmentMap.tsx` | No | Drag reorder, boundary drag, seam click |
| `FragmentTile` | `src/components/FragmentTile.tsx` | **Yes** | Click, double-click, hover, play |
| `BoundaryPrecisionOverlay` | `src/components/BoundaryPrecisionOverlay.tsx` | No | Boundary drag, outside click close |
| `ReservedFragments` | `src/components/ReservedFragments.tsx` | No | Freeform drag, click, restore |
| `NavLink` | `src/components/NavLink.tsx` | **Yes** | Router link wrapper |

### 2.3 Reusable `FragmentTile` Variants

| Variant | Height | widthScale | Behavior |
|---------|--------|------------|----------|
| `"panorama"` | 64px | 0.6 | Click to select, highlight ring, intelligence dots |
| `"edit"` | 72px | 0.7 | Click/double-click, play, exclude button, focus-zoom |
| `"reserved"` | 56px | 0.5 | Click to select, play allowed, no editing commands, no hover scale |

Width formula: `max(minW, fragment.duration × widthScale)` where `minW` = 60 (panorama), 48 (edit/reserved).

---

## 3. STATE AND INTERACTION SPECIFICATION

### 3.1 Global State (owned by `Index`)

| State | Type | Default | Purpose |
|-------|------|---------|---------|
| `activeNavItem` | `string` | `"projects"` | Left nav selection |
| `activeSource` | `string` | `"A"` | Which source video tab is active in Panorama |
| `selectedFragment` | `Fragment \| null` | `null` | Currently focused fragment (any region) |
| `focusExpandedId` | `string \| null` | `null` | Fragment in focus-expand state (single click) |
| `timeLensId` | `string \| null` | `null` | Fragment in Time Lens state (double click) |
| `highlightedPanoramaFrag` | `string \| null` | `null` | Fragment ID highlighted in Panorama |
| `playingFragmentId` | `string \| null` | `null` | Fragment currently playing (independent of selection) |
| `intelligenceOn` | `boolean` | `false` | Intelligence overlay visibility |
| `editFragments` | `Fragment[]` | `initialEditFragments` | Full edit structure (includes excluded) |
| `reservedFragments` | `Fragment[]` | `initialReservedFragments` | Hold Area fragments |
| `holdAreaPositions` | `Record<string, {x,y}>` | `{}` | Hold Area fragment positions (included in undo) |
| `boundaryHighlightIds` | `string[]` | `[]` | Fragment IDs highlighted during boundary drag |
| `fragmentOverrides` | `Map<string, Fragment>` | `new Map()` | Temporary duration overrides for Panorama during drag |
| `centerWidth` | `number` | 340 | Persisted splitter position |
| `undoStack` | `UndoEntry[]` | `[]` | Undo history (see §8) |
| `redoStack` | `UndoEntry[]` | `[]` | Redo history (see §8) |
| `precisionOverlay` | `PrecisionOverlayState \| null` | `null` | Active precision overlay (see §3.9) |

### 3.1.1 Fragment Interaction State Machine

The fragment interaction system is a finite state machine. At any moment, exactly one of these states is active:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     FRAGMENT INTERACTION STATES                        │
├───────────────────────┬─────────────────────────────────────────────────┤
│ State                 │ Description                                     │
├───────────────────────┼─────────────────────────────────────────────────┤
│ IDLE                  │ No fragment selected. Board at rest.            │
│ FOCUS_EXPANDED        │ Single fragment focused. Neighbors recede.     │
│ PLAYING               │ Fragment playing (can coexist with FOCUS).     │
│ TIME_LENS             │ Deep inspection mode. Fragment doubled width.  │
│ BOUNDARY_DRAGGING     │ Normal boundary drag in progress.              │
│ SEAM_HOVERED          │ Mouse over synthetic collapsed seam.           │
│ PRECISION_OVERLAY     │ Precision overlay open, idle inside.           │
│ PRECISION_DRAGGING    │ Boundary drag inside precision overlay.        │
│ HOLD_DRAGGING         │ Fragment being repositioned in Hold Area.      │
└───────────────────────┴─────────────────────────────────────────────────┘
```

**State Transition Diagram**:

```
                        ┌──────────────────────────────────────────────────────────────┐
                        │                                                              │
                        ▼                                                              │
                   ┌─────────┐                                                         │
          ┌───────│  IDLE    │◄──────────────────────────────────────┐                  │
          │       └────┬─────┘                                      │                  │
          │            │                                             │                  │
          │  single    │  double     boundary    seam      hold-area │                  │
          │  click     │  click     mousedown   hover     mousedown  │                  │
          │            │                                             │                  │
          ▼            ▼            ▼            ▼            ▼      │                  │
   ┌──────────┐  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│                  │
   │ FOCUS    │  │ TIME     │ │ BOUNDARY │ │ SEAM     │ │ HOLD     ││                  │
   │ EXPANDED │  │ LENS     │ │ DRAGGING │ │ HOVERED  │ │ DRAGGING ││                  │
   └──┬───┬──┘  └──┬───┬──┘ └──┬───────┘ └──┬───┬──┘ └──┬───────┘│                  │
      │   │        │   │        │             │   │        │        │                  │
      │   │        │   │        │ mouseup     │   │        │mouseup │                  │
      │   │        │   │        ├────────────►│   │        ├───────►│                  │
      │   │        │   │        │             │   │        │        │                  │
      │   │ same   │   │same    │ Escape      │   │mouseleave      │                  │
      │   │ click  │   │click   ├────────────►│   ├───────►│        │                  │
      │   ├───────►│   ├───────►│             │   │        │        │                  │
      │   │  IDLE  │   │ IDLE   │             │   │        │        │                  │
      │   │        │   │        │             │   │ seam   │        │                  │
      │   │outside │   │outside │             │   │ click  │        │                  │
      │   │click   │   │click   │             │   │        │        │                  │
      │   ├───────►│   ├───────►│             │   ▼        │        │                  │
      │   │  IDLE  │   │ IDLE   │      ┌──────────────┐    │        │                  │
      │   │        │   │        │      │ PRECISION    │    │        │                  │
      │   │Escape  │   │Escape  │      │ OVERLAY      │    │        │                  │
      │   ├───────►│   ├───────►│      └──┬───┬───┬──┘    │        │                  │
      │      IDLE  │      IDLE  │         │   │   │        │        │                  │
      │            │            │  boundary│   │   │outside │        │                  │
      │  play btn  │  play btn  │ mousedown│   │   │click   │        │                  │
      │  click     │  click     │         │   │   ├───────►│        │                  │
      │            │            │         │   │   │  IDLE  │        │                  │
      ▼            ▼            │         │   │   │        │        │                  │
   ┌──────────┐                 │         │   │   │Escape  │        │                  │
   │ PLAYING  │ (parallel)      │         │   │   ├───────►│        │                  │
   │          │ coexists with   │         ▼   │      IDLE  │        │                  │
   │ auto-    │ FOCUS_EXPANDED  │  ┌──────────────┐        │        │                  │
   │ stops at │ or IDLE         │  │ PRECISION    │        │        │                  │
   │ 100%     │                 │  │ DRAGGING     │        │        │                  │
   └──────────┘                 │  └──┬──────────┘        │        │                  │
                                │     │ mouseup            │        │                  │
                                │     ├───► PRECISION      │        │                  │
                                │     │     OVERLAY        │        │                  │
                                │     │                    │        │                  │
                                │     │ Escape             │        │                  │
                                │     ├───────────────────►│        │                  │
                                │          IDLE            │        │                  │
                                └──────────────────────────┘────────┘
```

**Transition table** (definitive reference):

| From | Trigger | To | Side Effects |
|------|---------|----|-------------|
| IDLE | single click on fragment | FOCUS_EXPANDED | Set `selectedFragment`, `focusExpandedId`, switch source tab, highlight panorama |
| IDLE | double click on fragment | TIME_LENS | Set `selectedFragment`, `timeLensId`, switch source tab |
| IDLE | play button click | PLAYING | Set `playingFragmentId`. No selection change. |
| IDLE | boundary mousedown | BOUNDARY_DRAGGING | Record start position, fire source recall |
| IDLE | seam mouseenter | SEAM_HOVERED | Show amber dots, tooltip |
| IDLE | hold-area mousedown | HOLD_DRAGGING | Record drag offset |
| FOCUS_EXPANDED | same fragment click | IDLE | Clear `selectedFragment`, `focusExpandedId`, highlights |
| FOCUS_EXPANDED | different fragment click | FOCUS_EXPANDED | Update `selectedFragment`, `focusExpandedId` to new target |
| FOCUS_EXPANDED | outside click | IDLE | Clear all selection state |
| FOCUS_EXPANDED | Escape | IDLE | Clear all selection state |
| FOCUS_EXPANDED | double click (same) | TIME_LENS | Set `timeLensId`, clear `focusExpandedId` |
| FOCUS_EXPANDED | play button click | FOCUS_EXPANDED + PLAYING | Start playback (parallel state) |
| TIME_LENS | same fragment click | IDLE | Clear `timeLensId`, `selectedFragment` |
| TIME_LENS | different fragment click | FOCUS_EXPANDED | Switch to new fragment's focus-expand |
| TIME_LENS | outside click | IDLE | Clear all |
| TIME_LENS | Escape | IDLE | Clear all |
| TIME_LENS | play button click | TIME_LENS + PLAYING | Start playback (parallel state) |
| PLAYING | playback reaches 100% | (previous state) | Clear `playingFragmentId`, auto-reset |
| PLAYING | play button click (pause) | (previous state) | Clear `playingFragmentId` |
| PLAYING | fragment deselected | IDLE | Stop playback, clear `playingFragmentId` |
| BOUNDARY_DRAGGING | mousemove | BOUNDARY_DRAGGING | Update durations via RAF, source recall active |
| BOUNDARY_DRAGGING | mouseup | IDLE | Commit boundary change, clear drag state, push undo |
| BOUNDARY_DRAGGING | Escape | IDLE | Revert to pre-drag durations, clear drag state |
| SEAM_HOVERED | mouseleave | IDLE | Remove amber highlight |
| SEAM_HOVERED | seam click | PRECISION_OVERLAY | Open overlay anchored to seam rect |
| PRECISION_OVERLAY | boundary mousedown (inside) | PRECISION_DRAGGING | Begin local-state drag |
| PRECISION_OVERLAY | outside click | IDLE | Close overlay, no commit |
| PRECISION_OVERLAY | Escape | IDLE | Discard local overrides, close overlay |
| PRECISION_DRAGGING | mousemove | PRECISION_DRAGGING | Update local `displayFragments` only |
| PRECISION_DRAGGING | mouseup | PRECISION_OVERLAY | Commit delta to `editFragments`, push undo, stay open |
| PRECISION_DRAGGING | Escape | IDLE | Discard local overrides, close overlay |
| HOLD_DRAGGING | mousemove | HOLD_DRAGGING | Update fragment position |
| HOLD_DRAGGING | mouseup (< 4px movement) | FOCUS_EXPANDED or IDLE | Treat as click: toggle selection |
| HOLD_DRAGGING | mouseup (≥ 4px movement) | IDLE | Reposition committed, no selection change, push undo for position change |

**Parallel state note**: PLAYING is a parallel state that can coexist with IDLE, FOCUS_EXPANDED, or TIME_LENS. It does not block other transitions. When the parent state transitions to IDLE via outside-click or Escape, PLAYING is also terminated.

### 3.2 Click Interactions — Exact Rules

#### Single Click on Fragment (Edit Structure)
1. If same fragment already selected → **deselect all** (`selectedFragment = null`, `highlightedPanoramaFrag = null`, `expandedFragment = null`). This is the "focus-expand toggle."
2. If different fragment → select it, set `activeSource` to fragment's source, highlight in Panorama, clear expanded.

#### Double Click on Fragment (Edit Structure)
1. Select the fragment.
2. Switch source tab.
3. Enter `expandedFragment` (Time Lens mode: fragment width doubles, shows internal frame strip).

#### Clicking Outside (Global Click-to-Dismiss)
- Clicking any empty space (not `.fragment-tile`, not inside a precision overlay, not on a boundary handle) → deselects all, clears highlights, clears expansion.
- Implemented on root `div` via `onClick` with `.closest(".fragment-tile")` guard.
- Does **NOT** fire when the click target is inside an active precision overlay.

#### Single Click on Fragment (Panorama)
1. Toggle selection only (no source switch, no highlight sync).

#### Single Click on Fragment (Hold Area)
1. Toggle selection, switch source tab and highlight in Panorama if selecting.

#### Click/Double-Click Disambiguation
- Implemented via 220ms timer in `FragmentTile`.
- First click starts timer; if second click arrives before timeout → double-click.
- If timeout fires → single click.

#### Play Button Click
- Play button is an independent click target (top-right of tile on hover).
- Clicking play does **NOT** trigger fragment selection or deselection.
- Play does **NOT** interfere with focus-expand state.
- Play state auto-stops if fragment is deselected via other means.
- Play is available in **edit** and **reserved** variants. Not in panorama.

### 3.3 Hover Interactions

| Target | Behavior |
|--------|----------|
| `FragmentTile` (edit/panorama) | Sweeping gradient animation (`preview-sweep` keyframe, 1.5s infinite). Play button appears (top-right, 16×16px circle). Subtle scale to `max(focusScale, 1.01)`. |
| `FragmentTile` (reserved) | No hover scale (scale stays 1). Play button appears on hover. |
| `BoundaryHandle` | Color: `hsl(228 5% 22%)` → `hsl(211 55% 58%)`. Width: 3px → 4px. |
| `SyntheticCollapsedSeam` | Dots turn amber (`--ccut-amber`). Background tints `hsl(var(--ccut-amber) / 0.06)`. Tooltip appears: "{N} hidden". |

### 3.4 Focus-Zoom (Selection Visual Effect)

When a fragment is selected:
- Selected fragment scales up: `1.08` (edit), `1.05` (panorama), `1.04` (reserved)
- All other fragments in the same region scale down: `0.94` (edit), `0.96` (panorama), `0.97` (reserved)
- All other fragments reduce opacity to `0.55`
- Selected fragment gets `z-index: 30`
- Animated via framer-motion `animate` prop, `tween 0.15s easeOut`

### 3.5 Play State

- Triggered by clicking play button (visible on hover, top-right of tile).
- Available in **edit** and **reserved** variants.
- `setInterval` at 50ms, incrementing progress by 2% per tick.
- Visual: colored gradient fill from left + vertical playhead line (`w-0.5 bg-primary`).
- Bottom progress bar: `h-0.5 bg-primary/70`.
- Auto-stops at 100%, resets to 0.
- Stops when fragment is deselected.
- **Provisional prototype behavior**: No real video playback. Simulated progress only.

### 3.6 Exclude / Restore

| Action | Trigger | Effect |
|--------|---------|--------|
| Exclude from render | Click `EyeOff` button on selected fragment | Sets `fragment.excluded = true`. Fragment disappears from visible board. Appears inside synthetic seams. Structure preserved. |
| Restore to render | (Currently not directly exposed on board — only via Hold Area restore or precision overlay) | Sets `fragment.excluded = false`. Fragment reappears on board. |
| Move to Hold Area | `onMoveToHold` callback | Removes from `editFragments`, adds to `reservedFragments` with `excluded = false`. Fragment is fully detached from the Edit Structure. |
| Restore from Hold Area | Click restore button (bottom-right of Hold Area) when fragment selected | Removes from `reservedFragments`, appends to end of `editFragments`. |

**Critical distinction**: "Excluded from render" ≠ "Removed from structure." Excluded fragments remain in `editFragments[]` at their structural index. They participate in boundary math and seam detection. They are simply skipped during render output. Moving to Hold Area is a full structural removal.

### 3.7 Boundary Drag (Normal — Between Directly Adjacent Visible Fragments)

1. **mousedown** on boundary handle: Record start X, original left/right durations. Fire `onBoundaryDragChange(left, right)` for source recall.
2. **mousemove**: Throttled via `requestAnimationFrame`. Delta = `round((clientX - startX) / 0.7)` frames. Clamp: both sides ≥ `MIN_FRAGMENT_DURATION` (15 frames). Mutate `editFragments` on every RAF tick.
3. **mouseup**: Clear drag state. Fire `onBoundaryDragChange(null, null)`.
4. **Source Recall**: On drag start, `activeSource` switches to the left fragment's source. `boundaryHighlightIds` set to `[left.id, right.id]`. Panorama scrolls to highlighted fragment and shows ring highlight.

### 3.8 Synthetic Collapsed Seam — Philosophy and Rules

**Core philosophy**: A synthetic collapsed seam is **NOT a true boundary**. It is a visual artifact that appears when one or more structurally present but render-excluded fragments sit between two visible fragments. The real boundaries are the internal structural boundaries between each adjacent pair in the chain.

**Detection** (`detectSyntheticSeams`): Scan `fragments[]` left-to-right. Whenever a non-excluded fragment is followed by one or more excluded fragments and then another non-excluded fragment, create a `SyntheticCollapsedSeam`.

**Board Rendering**: The board renders only `visibleFragments` (non-excluded). Between two visible fragments, if a seam exists, render the dotted seam indicator instead of a normal boundary handle. If no seam and fragments are directly adjacent (`realIndex + 1 === nextRealIndex`), render a normal boundary handle.

**Seam Click** → Opens `BoundaryPrecisionOverlay`.

**A seam is never directly draggable.** The user must open the precision overlay to access the real internal boundaries.

### 3.9 Precision Overlay

**Trigger**: Click on synthetic collapsed seam.

**Content**: Reveals full chain from `leftRealIndex` to `rightRealIndex` inclusive (left visible + all excluded + right visible).

**Position**: `position: fixed`, centered horizontally on the clicked seam's `getBoundingClientRect()`, 88px above the seam's top.

**Drag behavior** (COMMIT PREVIEW RULE):
1. During drag: Only local `displayFragments` state updates (via `localOverrides` Map). The main board does NOT re-render.
2. On mouseup: Commits final delta via `onBoundaryCommit(leftRealIdx, rightRealIdx, deltaFrames)` — single board mutation.
3. Source recall fires on drag start (`onSourceRecall`) and clears on mouseup.

**Boundary drag inside overlay**: Operates on **real internal structural boundaries** only. Dragging redistributes frame ownership between two structurally adjacent fragments. Only the explicitly reclaimed frame portion becomes active. All remaining excluded portions stay excluded as residual structure. Excluded fragments do NOT automatically fully return — only the frames moved across a boundary become part of the adjacent fragment.

**Exit conditions**:
- mouseup after drag → commit + stay open
- Click outside overlay → close without commit
- Escape key → discard local overrides + close

**Frame precision**: 1 frame per ~1.2px of mouse movement.

### 3.10 Drag-and-Drop Reorder (Edit Structure)

- HTML5 native drag (`draggable`, `onDragStart`, `onDragOver`, `onDrop`)
- Drop indicator: 2px primary-colored vertical line
- Dragged fragment: `opacity: 0.4`
- Disabled during boundary drag (`boundaryDragIndex !== null`)
- Operates on full `fragments[]` array (preserves excluded fragment positions)

### 3.11 Hold Area (Freeform Board) — Rules

- **Playback allowed**: Fragments in the Hold Area can be played (simulated progress bar).
- **No editing commands**: Boundary drag, exclude/restore, reorder — none of these apply inside the Hold Area.
- **No magnetic behavior**: No snapping, no grid alignment, no auto-layout.
- **No auto-alignment**: Fragments stay exactly where dropped.
- **Overlap allowed**: Multiple fragments may occupy the same visual space.
- **Keep exact dropped position**: Position is stored as `{x, y}` in local state. No adjustment after drop.
- Absolute positioning, no grid/snap/auto-layout.
- Default positions: `x: 12 + (index % 5) × 80`, `y: 8 + floor(index / 5) × 68`.
- Custom positions stored in local `positions` state (not persisted).
- Mouse drag to reposition (not HTML5 drag — manual `mousedown/move/up`).
- Dragged fragment: `cursor: grabbing`, `z-index: 50`, no CSS transition.
- Restore button: Fixed bottom-right, `RotateCcw` icon, restores selected fragment to edit structure.
- Fragments in the Hold Area do **NOT** participate in boundary math or seam detection.

### 3.12 Commit Preview Rule (Precision Overlay)

During boundary drag inside the precision overlay:
- Show live preview of the resulting structural allocation inside the overlay only.
- The main board remains visually stable — no re-render during drag.
- Only the local overlay updates continuously at frame precision.
- On mouse release: commit the final structural change to the main `editFragments` state as a single mutation.
- Source Recall (Panorama highlight) may update during drag for visual context.

---

## 4. INTERACTION PRIORITY MATRIX

When multiple interaction intents could fire simultaneously, use the following precedence rules.

### 4.1 Click Disambiguation

| Conflict | Resolution |
|----------|------------|
| Single click vs. double click | 220ms timer. First click waits; second click within window → double-click fires, single click cancelled. Timeout → single click fires. |
| Play button click vs. fragment click | Play button has its own click handler with `e.stopPropagation()`. Fragment click does NOT fire. Play state is independent of selection. |
| Fragment click vs. outside click | `.closest(".fragment-tile")` guard. If click lands on a fragment → fragment click. If not → outside click (dismiss). |
| Outside click vs. overlay open | If precision overlay is open, clicks inside the overlay are consumed by the overlay. Clicks outside both the overlay and fragments close the overlay first, then dismiss selection. |

### 4.2 Drag Disambiguation

| Conflict | Resolution |
|----------|------------|
| Boundary drag vs. reorder drag | Boundary drag activates on `mousedown` on a boundary handle (3–4px zone). Reorder drag activates on `dragstart` on the fragment tile body. These targets do not overlap. If `boundaryDragIndex !== null`, HTML5 drag is disabled (`draggable={false}`). |
| Synthetic seam click vs. normal boundary click | Seam indicator and boundary handle are mutually exclusive DOM elements. A seam exists only where excluded fragments hide between visible fragments. Where no excluded fragments exist, a normal boundary handle renders instead. Never both. |
| Hold Area drag vs. select | `mousedown` initiates drag tracking. If `mouseup` occurs without significant movement (< 4px total delta), treat as click (select/deselect). If movement exceeds threshold → reposition only, no selection change. |

### 4.3 Keyboard vs. Mouse

| Conflict | Resolution |
|----------|------------|
| Escape during boundary drag | Cancel drag, discard changes, revert to pre-drag state. |
| Escape during precision overlay | Discard local overrides, close overlay. |
| Escape with no overlay or drag | Deselect all (same as outside click). |

### 4.4 Priority Stack (highest to lowest)

1. Active boundary drag (mouse captured — all other interactions blocked)
2. Active precision overlay (captures clicks within, Escape closes)
3. Hold Area drag (mouse captured within Hold Area)
4. Fragment click/double-click (220ms disambiguation)
5. Outside click dismiss
6. Hover effects (lowest priority, purely visual)

---

## 5. STYLING TOKENS

### 5.1 Colors (HSL Values — `:root` CSS Custom Properties)

| Token | HSL | Usage |
|-------|-----|-------|
| `--background` | `228 12% 10%` | Page background |
| `--foreground` | `220 10% 88%` | Primary text |
| `--card` | `228 10% 13%` | Panel backgrounds |
| `--primary` | `211 55% 58%` | Interactive accents, selection, links |
| `--primary-foreground` | `0 0% 100%` | Text on primary |
| `--secondary` | `228 8% 17%` | Chip/tag backgrounds, input backgrounds |
| `--muted` | `228 6% 21%` | Subtle backgrounds |
| `--muted-foreground` | `220 6% 50%` | Secondary text, labels |
| `--destructive` | `0 50% 55%` | Delete/exclude hover |
| `--border` | `228 6% 18%` | Borders, dividers |
| `--input` | `228 6% 22%` | Input field backgrounds |
| `--ring` | `211 55% 58%` | Focus rings |
| `--ccut-bg-deep` | `228 12% 10%` | Deepest background |
| `--ccut-bg-panel` | `228 10% 13%` | Panel surface |
| `--ccut-bg-elevated` | `228 8% 16%` | Elevated surface |
| `--ccut-amber` | `30 50% 55%` | Precision/seam indicator |
| `--ccut-indigo` | `220 35% 52%` | Intelligence gradient start |
| `--ccut-stroke` | `228 5% 20%` | Subtle strokes |

### 5.2 Source Video Hue Map

Used for per-source tinting (hover sweep, playback gradient):

| Source | Hue |
|--------|-----|
| A | 30 |
| B | 200 |
| C | 120 |
| D | 0 |
| E | 280 |
| F | 50 |
| G | 320 |

### 5.3 Typography

| Usage | Size | Weight | Color | Tracking |
|-------|------|--------|-------|----------|
| Section headers | 12px (text-xs) | 600 (font-semibold) | `foreground` | `tracking-wide` |
| Counts, hints | 10px (text-[10px]) | 400 | `muted-foreground` | — |
| Fragment ID (tile) | 10px | 600 | `foreground/90` | — |
| Fragment duration (tile) | 9px (text-[9px]) | 400 | `foreground/50` | — |
| Overlay labels | 8px (text-[8px]) | 600 | `foreground/85` | — |
| Frame ruler | 7px (text-[7px]) | 400 | `muted-foreground/40` | — |
| Overlay ruler | 6px (text-[6px]) | 400 | `muted-foreground/35` | — |
| Precision header | 8px | 500 | `muted-foreground/50` | `tracking-widest` |
| Intelligence labels | 12px (text-xs) | 400 | `muted-foreground` | — |
| Chat input | 14px (text-sm) | 400 | `foreground` | — |

**Font family**: `'Inter', system-ui, sans-serif` — loaded via Google Fonts (weights: 300–800).

### 5.4 Spacing

| Context | Value |
|---------|-------|
| Panel padding | `px-3 py-2` (12px × 8px) |
| Section gap (right workspace) | `gap-2` (8px) |
| Fragment board padding | `px-2 py-2` |
| Between fragments in board | `gap-0` (fragments touch, separated only by boundary handles) |
| Boundary handle width | 3px idle, 4px hover/active |
| Synthetic seam width | 10px |
| Precision overlay padding | `p-1.5` (6px) |
| Precision boundary hit area | 14px |

### 5.5 Border Radius

| Element | Radius |
|---------|--------|
| Panels (`bg-card/50`) | `rounded-lg` (8px, `var(--radius)`) |
| Fragment tiles | `rounded-md` (6px) |
| Precision overlay card | `rounded-md` |
| Buttons | `rounded-md` or `rounded-full` |
| Nav buttons | `rounded-md` |
| Source chips | `rounded` (4px) |
| Scrollbar thumb | 3px |
| `--radius` base | `0.5rem` (8px) |

### 5.6 Shadows

| Element | Shadow |
|---------|--------|
| Fragment glow (selected) | `0 0 6px 1px hsl(211 55% 58% / 0.18), inset 0 0 4px hsl(211 55% 58% / 0.04)` |
| Precision overlay | `0 6px 24px -6px hsl(var(--background) / 0.6), 0 1px 4px -1px hsl(var(--primary) / 0.06)` |
| Exclude button | `shadow-sm` (Tailwind default) |

### 5.7 Borders

| Context | Style |
|---------|-------|
| Fragment tile default | `border border-border/30` |
| Fragment tile selected | `border-primary/60` |
| Fragment tile highlighted | `border-primary/30` |
| Panel dividers | `h-px bg-border/30` or `border-border/20` |
| Precision overlay card | `border border-border/30` |
| Boundary highlight ring (Panorama) | `ring-1 ring-primary/60` |

### 5.8 Transitions & Animation

| Interaction | Duration | Easing | Engine |
|-------------|----------|--------|--------|
| Fragment focus-zoom (scale/opacity) | 150ms | `easeOut` | framer-motion `tween` |
| Fragment tile border/shadow/opacity | 120ms | `ease-out` | CSS transition |
| Boundary handle color/width | 150ms | default | CSS transition |
| Synthetic seam background | 100ms | `ease-out` | CSS transition |
| Precision overlay enter | 100ms | `easeOut` | framer-motion tween, `y: 4→0`, `opacity: 0→1` |
| Precision overlay exit | 100ms | `easeOut` | framer-motion tween, `y: 0→3`, `opacity: 1→0` |
| Hover preview sweep | 1500ms | `ease-in-out` | CSS `@keyframes preview-sweep`, infinite |
| Splitter pill height | 150ms | default | CSS `transition-all` |
| Excluded fragment opacity/filter | 200ms | default | CSS transition |

**Critical motion rule**: No spring physics. No bounce. All transitions are short `tween`s with `easeOut`. Motion must feel calm, anchored, structurally stable.

---

## 6. DATA MODEL

### 6.1 Core Types

```typescript
interface Fragment {
  fragment_id: string;          // e.g. "A1", "B3"
  source_video: string;         // e.g. "A", "B"
  start_frame: number;
  end_frame: number;
  duration: number;             // end_frame - start_frame
  thumbnail_hue: number;        // fallback color hue
  thumbnail?: {
    thumbnail_url?: string;
    thumbnail_time?: number;
    extraction_version?: number;
    last_updated?: number;
  };
  excluded?: boolean;           // excluded from render, still in structure
  intelligence?: {
    narrative: number;    // 0–1
    emotional: number;
    action: number;
    dialogue: number;
    hook: number;
    callback: number;
    confidence: number;  // 0.5–1.0
  };
}

interface SourceVideo {
  id: string;
  label: string;
  totalFrames: number;
  fps: number;
  description: string;
}
```

### 6.2 Boundary System Types

```typescript
interface SyntheticCollapsedSeam {
  leftVisibleFragmentId: string;
  rightVisibleFragmentId: string;
  hiddenExcludedFragmentIds: string[];
  internalBoundaries: InternalBoundary[];
  leftRealIndex: number;   // index in full fragments[]
  rightRealIndex: number;
}

interface InternalBoundary {
  id: string;                    // "A1-B2"
  leftRealIndex: number;
  rightRealIndex: number;
  leftFragmentId: string;
  rightFragmentId: string;
}

interface PrecisionOverlayState {
  seam: SyntheticCollapsedSeam;
  chainRealIndices: number[];
  anchorRect: DOMRect;
}
```

### 6.3 Undo/Redo Types

```typescript
type UndoActionType =
  | "reorder"
  | "boundary-resize"
  | "replace-fragment"
  | "exclude"
  | "restore"
  | "move-to-hold"
  | "restore-from-hold"
  | "precision-boundary"
  | "hold-area-reposition";

interface UndoEntry {
  type: UndoActionType;
  timestamp: number;
  /** Snapshot of editFragments before this action */
  prevEditFragments: Fragment[];
  /** Snapshot of reservedFragments before this action */
  prevReservedFragments: Fragment[];
  /** Snapshot of Hold Area positions before this action */
  prevHoldAreaPositions: Record<string, { x: number; y: number }>;
  /** Human-readable label for debugging */
  label: string;
}
```

### 6.4 Boundary Math Rules

- Adjacent fragments share boundaries: `fragmentN.end_frame === fragmentN+1.start_frame` (conceptual — not enforced in current data model since fragments may come from different sources)
- Dragging redistributes: `left.duration += delta`, `right.duration -= delta`
- Both durations clamped to `≥ MIN_FRAGMENT_DURATION` (15 frames)
- Excluded fragments participate in boundary math — exclusion only affects render, not structure
- Frame conversion: `seconds = frames / fps` (default fps = 30)
- Only explicitly reclaimed frame portions become active — residual excluded portions stay excluded

---

## 7. BOUNDARY PHILOSOPHY

This section codifies the structural rules that underpin all boundary and fragment editing.

### 7.1 Excluded ≠ Removed

- A fragment with `excluded = true` remains in `editFragments[]` at its structural index.
- It participates in synthetic seam detection, boundary math, and chain resolution.
- It is simply omitted from the rendered output.
- Moving to Hold Area is a true structural removal — the fragment leaves `editFragments[]` entirely.

### 7.2 Synthetic Collapsed Seam ≠ True Boundary

- A seam is a visual indicator, not a draggable boundary.
- It appears only where one or more excluded fragments sit between two visible fragments.
- The seam cannot be directly dragged. Clicking it opens the precision overlay.
- Inside the precision overlay, the user accesses the **real internal structural boundaries**.

### 7.3 Frame Reclamation Rule

When dragging a real internal boundary inside the precision overlay:
- Frame ownership is redistributed between two structurally adjacent fragments.
- If the drag moves frames from an excluded fragment into a visible fragment, only those specific frames are reclaimed.
- The excluded fragment does **NOT** automatically become fully visible.
- The remaining frame range of the excluded fragment stays excluded as residual structure.
- If an excluded fragment is reduced to `0` frames (`duration ≤ 0`), it is removed from the structure entirely.

### 7.4 Boundary Drag Scope

- Normal boundary drag (between two directly adjacent visible fragments): operates on `editFragments[]` directly, mutates on every RAF tick.
- Precision overlay boundary drag (between chain members including excluded): operates on local overlay state, commits once on mouseup.
- Hold Area: no boundary drag exists. Fragments are independent.

---

## 8. UNDO / REDO SPECIFICATION

### 8.1 Architecture

- Two stacks: `undoStack: UndoEntry[]` and `redoStack: UndoEntry[]`.
- Before any mutating action, push a snapshot of `{editFragments, reservedFragments, holdAreaPositions}` to `undoStack` and clear `redoStack`.
- Undo: pop from `undoStack`, push current state to `redoStack`, restore popped state (all three: edit, reserved, positions).
- Redo: pop from `redoStack`, push current state to `undoStack`, restore popped state (all three).
- Maximum stack depth: 50 entries (drop oldest on overflow).

### 8.2 Covered Actions

| Action | When to snapshot |
|--------|-----------------|
| Reorder (drag-and-drop) | On `onDrop` — before applying new order |
| Boundary resize (normal) | On `mouseup` — before committing final delta |
| Replace fragment | Before replacing fragment data |
| Exclude fragment | Before setting `excluded = true` |
| Restore fragment | Before setting `excluded = false` |
| Move to Hold Area | Before transferring between arrays |
| Restore from Hold Area | Before transferring between arrays |
| Precision overlay boundary edit | On overlay commit (`mouseup`) — before applying to `editFragments` |
| Hold Area reposition | On mouseup after ≥ 4px drag — before updating `holdAreaPositions` |

### 8.3 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + Z` | Undo |
| `Cmd/Ctrl + Shift + Z` | Redo |

### 8.4 Edge Cases

- If `undoStack` is empty, undo is a no-op.
- If `redoStack` is empty, redo is a no-op.
- Any new mutating action clears `redoStack` (standard undo tree behavior).
- Undo/redo restores `editFragments`, `reservedFragments`, and `holdAreaPositions` atomically.
- Hold Area repositioning (drag with ≥ 4px movement) is an undoable action.

---

## 9. ACCESSIBILITY SPECIFICATION

### 9.1 Keyboard Navigation

| Key | Context | Action |
|-----|---------|--------|
| `Tab` | Global | Move focus through focusable elements in DOM order: nav items → center panel → source tabs → panorama fragments → edit fragments → boundary handles → hold area fragments |
| `Shift+Tab` | Global | Reverse tab order |
| `Enter` / `Space` | Focused fragment | Equivalent to single click (select/deselect toggle) |
| `Enter` (double press within 220ms) | Focused fragment | Equivalent to double click (Time Lens) |
| `Arrow Left` / `Arrow Right` | Fragment Map with a selected fragment | Move selection to previous/next visible fragment |
| `Arrow Left` / `Arrow Right` | Focused boundary handle | Nudge boundary by 1 frame in that direction |
| `Shift + Arrow Left/Right` | Focused boundary handle | Nudge boundary by 5 frames |
| `Escape` | Precision overlay open | Close overlay, discard uncommitted changes |
| `Escape` | No overlay, fragment selected | Deselect all |
| `Escape` | During boundary drag | Cancel drag, revert to pre-drag state |
| `Delete` / `Backspace` | Selected fragment in Edit Structure | Exclude from render (`excluded = true`) |
| `Cmd/Ctrl + Z` | Global | Undo |
| `Cmd/Ctrl + Shift + Z` | Global | Redo |

### 9.2 Focus Indicators

- All interactive elements must have a visible focus ring: `ring-2 ring-ring ring-offset-2 ring-offset-background`.
- Focus ring uses `--ring` token (`211 55% 58%`).
- Focus ring only visible on keyboard navigation (`:focus-visible`), not on mouse click.

### 9.3 ARIA Attributes

| Element | ARIA |
|---------|------|
| Fragment tile | `role="button"`, `aria-label="{fragment_id} — {duration} frames from source {source}"`, `aria-selected={isSelected}`, `aria-expanded={isExpanded}` (Time Lens) |
| Boundary handle | `role="separator"`, `aria-orientation="vertical"`, `aria-label="Boundary between {leftId} and {rightId}"`, `aria-valuenow={leftDuration}`, `aria-valuemin={MIN_FRAGMENT_DURATION}`, `aria-valuemax={leftDuration + rightDuration - MIN_FRAGMENT_DURATION}` |
| Synthetic seam | `role="button"`, `aria-label="Collapsed seam: {N} hidden fragments between {leftId} and {rightId}"`, `aria-haspopup="dialog"` |
| Precision overlay | `role="dialog"`, `aria-label="Precision boundary editor"`, `aria-modal="false"` (non-modal, board stays visible) |
| Hold Area | `role="region"`, `aria-label="Hold Area — {N} fragments"` |
| Fragment Map | `role="region"`, `aria-label="Edit Structure — {N} visible fragments"` |
| Original Panorama | `role="region"`, `aria-label="Source {activeSource} panorama"` |
| Source tabs | `role="tablist"`, each tab: `role="tab"`, `aria-selected` |
| Splitter | `role="separator"`, `aria-orientation="vertical"`, `aria-valuenow={centerWidth}`, `aria-valuemin={260}`, `aria-valuemax={maxWidth}` |
| Nav buttons | `role="button"`, `aria-label="{label}"`, `aria-current="page"` if active |
| Play button | `aria-label="Play {fragment_id}"` / `aria-label="Pause {fragment_id}"` |
| Exclude button | `aria-label="Exclude {fragment_id} from render"` |
| Restore button (Hold Area) | `aria-label="Restore selected fragment to Edit Structure"` |

### 9.4 Screen Reader Announcements

- On fragment select: announce `"{fragment_id} selected"` via `aria-live="polite"` region.
- On boundary drag commit: announce `"{leftId} now {leftDuration} frames, {rightId} now {rightDuration} frames"`.
- On exclude: announce `"{fragment_id} excluded from render"`.
- On restore: announce `"{fragment_id} restored to render"`.
- On precision overlay open: announce `"Precision editor opened: {N} fragments in chain"`.
- On precision overlay close: announce `"Precision editor closed"`.

### 9.5 Reduced Motion

- Respect `prefers-reduced-motion: reduce` media query.
- When active: disable `preview-sweep` animation, set all framer-motion transitions to `duration: 0`, disable focus-zoom scale animations (keep opacity changes only).

---

## 10. IMPLEMENTATION NOTES FOR CODEX

### 10.1 What Is Real Interactive State (Must Implement Fully)

| Feature | Notes |
|---------|-------|
| Fragment selection/deselection | Full click-to-select/dismiss system across all three regions |
| Boundary drag redistribution | Core structural editing — real frame math, shared boundaries |
| Synthetic seam detection | `detectSyntheticSeams()` must run on every `editFragments` change |
| Precision overlay with local preview | Commit-on-release pattern: local state during drag, single mutation on mouseup |
| Source recall during drag | Switch source tab + highlight + scroll-into-view |
| Exclude/restore fragment | Toggle `excluded` boolean on fragment in edit structure |
| Move to / restore from Hold Area | Transfer between `editFragments` and `reservedFragments` |
| Drag-to-reorder fragments | HTML5 DnD on the full `fragments[]` array |
| Hold Area freeform positioning | Absolute position drag (not HTML5 DnD), play allowed, no editing |
| Splitter resize with persistence | `localStorage` persistence, min/max constraints |
| Focus-zoom (scale + opacity) | When any fragment is selected, all siblings scale/fade |
| Global click-to-dismiss | Background click clears all selection/expansion |
| Click/double-click disambiguation | 220ms timer-based separation |
| Undo/redo | Full snapshot stack for all mutating operations |
| Keyboard navigation | Tab order, arrow key selection, Escape handling |

### 10.2 What Is Visual Only (Render But Not Functional)

| Feature | Notes |
|---------|-------|
| Intelligence metrics (AI Signals) | Rendered as bars in CenterPanel. Data is random. No real AI backend. |
| Intelligence dots on tiles | Conditional dots when `intelligenceOn`. Random data. |
| Play/playback simulation | `setInterval` progress bar. No real video. No audio. |
| Hover preview sweep | CSS animation simulating a scan. No real frame extraction. |
| Chat bar | Text input renders but does not submit. No AI backend. |
| Render preview placeholder | Dashed box with "Request render" text. Non-functional. |
| Source summary cards (Center) | Static chips showing source labels. Clickable but only set visual state. |
| Time Lens (double-click expansion) | Shows placeholder colored blocks. No real sub-frame data. |
| Left nav items | Clickable but only change `activeNavItem` string. No routing. |

### 10.3 What Is Provisional Prototype Behavior (Replace in Production)

| Feature | Prototype | Production |
|---------|-----------|------------|
| Fragment data | `makeFragments()` generates random data | Load from backend/database |
| Thumbnails | Static JPGs per source (`source-a.jpg` etc.) | Extract from real video via `thumbnailService.ts` |
| Intelligence scores | `Math.random()` | AI inference results |
| Fragment IDs | `"A1"`, `"B3"` etc. | UUIDs or backend-assigned IDs |
| Duration format | Frame-based with `formatDuration()` | Timecode (HH:MM:SS:FF) |
| Hold Area positions | In-memory only | Persist to backend |
| Edit structure | In-memory `useState` | Persist to backend, undo/redo stack |
| Boundary drag sensitivity | `0.7px per frame` (normal), `1.2px per frame` (precision) | Configurable, zoom-dependent |

### 10.4 Thumbnail Service (Ready for Production)

`src/services/thumbnailService.ts` is fully implemented and production-ready:
- Canvas-based frame extraction from `<video>` elements
- Quality validation (rejects black/white/blank frames)
- Fallback position cascade: 50% → 45% → 55% → 35% → 65% → 25% → 75%
- Blob URL caching with cleanup
- Boundary change detection for regeneration triggers
- Batch extraction for full source videos

### 10.5 Performance Considerations

| Area | Approach |
|------|----------|
| Boundary drag | `requestAnimationFrame` throttling, `pendingDelta` ref pattern |
| Synthetic seam detection | `useMemo` on `fragments` array reference |
| Visible fragment filtering | `useMemo` on `fragments` array reference |
| Seam-to-fragment mapping | `useMemo` producing `Map<string, SyntheticCollapsedSeam>` |
| Precision overlay drag | Local state only, no parent re-render until commit |
| Fragment tile renders | framer-motion `animate` prop (not `layout`) — avoids layout thrashing |
| Scrollbar styling | Pure CSS (`::-webkit-scrollbar`), no JS scroll listeners |

### 10.6 Z-Index Stack

| Layer | z-index |
|-------|---------|
| Fragment tile (default) | 1 |
| Fragment tile (selected) | 30 |
| Exclude button | 30 |
| Hold Area dragged fragment | 50 |
| Precision overlay | 100 (fixed position) |
| Left nav tooltips | 50 |

### 10.7 Dependencies

| Package | Usage |
|---------|-------|
| `react`, `react-dom` | Core |
| `framer-motion` | Fragment tile animation (scale, opacity), overlay enter/exit |
| `lucide-react` | Icons: `Play`, `Pause`, `EyeOff`, `Eye`, `RotateCcw`, `Plus`, `Send`, `ChevronRight`, `Archive`, `Film`, `Upload`, `Folder`, `Settings`, `User`, `Layers` |
| `tailwindcss` + `tailwindcss-animate` | Styling |
| `@radix-ui/*` | shadcn/ui primitives (tooltip, popover, hover-card — available but minimally used) |

### 10.8 File Structure Summary

```
src/
├── pages/
│   └── Index.tsx              ← Root page, all global state
├── components/
│   ├── LeftNav.tsx            ← Fixed 56px nav
│   ├── CenterPanel.tsx        ← Analysis + chat column
│   ├── OriginalPanorama.tsx   ← Source strip with tabs
│   ├── FragmentMap.tsx        ← Edit structure board + seams + overlay
│   ├── FragmentTile.tsx       ← Reusable tile (3 variants)
│   ├── BoundaryPrecisionOverlay.tsx ← Floating precision editor
│   ├── ReservedFragments.tsx  ← Hold Area freeform board
│   └── NavLink.tsx            ← Router link wrapper
├── types/
│   └── boundaryTypes.ts       ← SyntheticCollapsedSeam, InternalBoundary, etc.
├── data/
│   ├── fragmentData.ts        ← Fragment/SourceVideo types, sample data
│   └── thumbnailMap.ts        ← Source thumbnail imports + getter
├── services/
│   └── thumbnailService.ts    ← Production thumbnail extraction
└── index.css                  ← Design tokens, custom CSS classes
```

---

*End of handoff specification.*
