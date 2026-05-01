# Index Decomposition Plan (STEP 10-I.4)

## 1. Overview
`Index.tsx` currently exceeds 900 lines and manages multiple unrelated responsibilities, including layout resizing, analysis polling, proposal state management, and fragment workspace logic. This complexity makes it difficult to maintain and test.

The goal of this decomposition is to extract these responsibilities into dedicated custom hooks, leaving `Index.tsx` as a clean orchestrator.

## 2. Responsibility Audit
Currently, `Index.tsx` handles:
- **UI/Layout**: Navigation state, panel width, drag-to-resize logic.
- **Analysis Pipeline**: Video upload, fragment generation, status polling, and semantic data fetching.
- **Proposal Control**: Selection, commitment, and reproposal (refinement) of editing drafts.
- **Fragment Workspace**: Managing the movement and state of fragments across Edit, Reserved, and Trash boards.

## 3. Target Hooks & Interface Design

### 3.1. `useWorkspaceLayout`
**Responsibility**: UI-specific states that don't affect business logic.
- **State**: `activeNavItem`, `navCollapsed`, `centerWidth`, `isDragging`, `projects`.
- **Logic**: Panel resizing handlers (`mousemove`, `mouseup`).
- **Input**: None.
- **Output**: Layout states and resize handlers.

### 3.2. `useAnalysisPipeline`
**Responsibility**: Managing the lifecycle of a video analysis session.
- **State**: `appState`, `analyzeProgress`, `analyzeMessage`, `quickScanData`, `semanticFragments`, `sourceEntries`, `currentSourceId`, `currentVideoUrl`.
- **Logic**: `handleStartAnalysis`, `resetAnalysisState`, polling backend, mapping fragments.
- **Input**: `toFullUrl` (utility), `setSourceFragments`, `setEditFragments`, `setProposals`, `setDirectionSnapshot`.
- **Output**: Analysis states and `handleStartAnalysis` function.

### 3.3. `useProposalState`
**Responsibility**: Managing AI editing proposals and their lifecycle.
- **State**: `proposals`, `directionSnapshot`, `selectedProposalId`, `committedProposalId`.
- **Logic**: `handleProposalPreview`, `handleProposalCommit`, `handleReproposal`.
- **Input**: `sourceFragments`, `logProposalPair`.
- **Output**: Proposal states and action handlers.

### 3.4. `useFragmentWorkspace`
**Responsibility**: Core editing logic involving fragment manipulation.
- **State**: `editFragments`, `reservedFragments`, `deletedFragments`, `selectedFragment`, `highlightedPanoramaFrag`, `expandedFragment`, `holdPositions`.
- **Logic**: Reordering, moving to hold, restoring from trash, adding from source.
- **Input**: `committedProposalId`, `proposals`, `setProposals`.
- **Output**: Workspace states and manipulation handlers.

## 4. Execution Strategy (Phased Migration)

### Phase 1: Infrastructure (Safe)
- Create `ccut_frontend/src/hooks/` directory.
- Create empty files for the 4 target hooks.
- No changes to `Index.tsx`.

### Phase 2: Atomic Extraction (Sequential)
1. **Extraction of `useWorkspaceLayout`**: [COMPLETED] Simplest logic, low risk.
2. **Extraction of `useProposalState`**: Well-defined state transitions.

3. **Extraction of `useFragmentWorkspace`**: Complex interactions with `proposals`.
4. **Extraction of `useAnalysisPipeline`**: Heaviest logic, requires careful state wiring.

### Phase 3: Integration & Cleanup
- Replace local states in `Index.tsx` with hook calls.
- Clean up unused imports and types.
- Final build check.

## 5. Constraints & Safety
- **Zero Behavior Change**: Logic must remain identical.
- **No Export/Render Modification**: `resolvedFragments` and `physicalClips` logic remains in `Index.tsx` or as simple useMemos.
- **Manual Verification**: Test video upload and proposal selection after each step.
- **Build Pass**: `npm run build` must succeed at every commit.
