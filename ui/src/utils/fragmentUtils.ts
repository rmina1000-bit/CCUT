import { refreshFragmentThumbnailIfNeeded } from '../services/thumbnailService';
import type {
  Fragment,
  HoldPosition,
  PrecisionEditorScopeResult,
  PrecisionEntryHandle,
  PrecisionOverlayState,
  StableBoardState,
  StructuralItem,
  SyntheticCollapsedSeam,
  UndoActionType,
  UndoBoundaryOperation,
  UndoEntry,
  UndoOperation,
  UndoReplaceFragmentOperation
} from '../types/boundaryTypes';

export const MIN_FRAGMENT_DURATION = 15;
export const MAX_UNDO_DEPTH = 50;
export const CENTER_WIDTH_STORAGE_KEY = 'ccut-center-width';

export function cloneFragment(fragment: Fragment): Fragment {
  return {
    ...fragment,
    thumbnail: fragment.thumbnail ? { ...fragment.thumbnail } : undefined,
    intelligence: fragment.intelligence ? { ...fragment.intelligence } : undefined
  };
}

export function cloneFragments(fragments: Fragment[]) {
  return fragments.map(cloneFragment);
}

export function cloneHoldPositions(positions: Record<string, HoldPosition>) {
  return Object.fromEntries(
    Object.entries(positions).map(([key, value]) => [key, { ...value }])
  );
}

export function createUndoEntry(
  type: UndoActionType,
  label: string,
  state: StableBoardState,
  op?: UndoOperation
): UndoEntry {
  return {
    type,
    timestamp: Date.now(),
    label,
    prevEditFragments: cloneFragments(state.editFragments),
    prevReservedFragments: cloneFragments(state.reservedFragments),
    prevHoldAreaPositions: cloneHoldPositions(state.holdAreaPositions),
    op
  };
}

export function buildStableBoardState(
  editFragments: Fragment[],
  reservedFragments: Fragment[],
  holdAreaPositions: Record<string, HoldPosition>
): StableBoardState {
  return {
    editFragments: cloneFragments(editFragments),
    reservedFragments: cloneFragments(reservedFragments),
    holdAreaPositions: cloneHoldPositions(holdAreaPositions)
  };
}

export function formatDuration(duration: number, fps = 24) {
  const seconds = duration / fps;
  if (seconds < 10) {
    return `${seconds.toFixed(1)}s`;
  }
  return `${Math.round(seconds)}s`;
}

export function getVisibleFragments(editFragments: Fragment[]) {
  return editFragments.filter((fragment) => !fragment.excluded);
}

export function buildStructuralItems(editFragments: Fragment[]): StructuralItem[] {
  const visibleRefs = editFragments
    .map((fragment, realIndex) => ({ fragment, realIndex }))
    .filter(({ fragment }) => !fragment.excluded);

  const items: StructuralItem[] = [];

  visibleRefs.forEach(({ fragment, realIndex }, visibleIndex) => {
    items.push({
      type: 'fragment',
      fragment,
      realIndex,
      visibleIndex
    });

    const next = visibleRefs[visibleIndex + 1];
    if (!next) {
      return;
    }

    if (next.realIndex === realIndex + 1) {
      items.push({
        type: 'boundary',
        leftFragment: fragment,
        rightFragment: next.fragment,
        leftRealIndex: realIndex,
        rightRealIndex: next.realIndex
      });
      return;
    }

    const hidden = editFragments.slice(realIndex + 1, next.realIndex);
    const hiddenExcludedFragmentIds = hidden
      .filter((candidate) => candidate.excluded)
      .map((candidate) => candidate.fragment_id);

    if (hiddenExcludedFragmentIds.length) {
      const chain = editFragments.slice(realIndex, next.realIndex + 1);
      const internalBoundaries = chain.slice(0, -1).map((candidate, index) => ({
        id: `${candidate.fragment_id}-${chain[index + 1].fragment_id}`,
        leftRealIndex: realIndex + index,
        rightRealIndex: realIndex + index + 1,
        leftFragmentId: candidate.fragment_id,
        rightFragmentId: chain[index + 1].fragment_id
      }));

      items.push({
        type: 'seam',
        seam: {
          leftVisibleFragmentId: fragment.fragment_id,
          rightVisibleFragmentId: next.fragment.fragment_id,
          hiddenExcludedFragmentIds,
          internalBoundaries,
          leftRealIndex: realIndex,
          rightRealIndex: next.realIndex
        }
      });
    }
  });

  return items;
}

export function reorderVisibleFragment(
  editFragments: Fragment[],
  draggedId: string,
  targetVisibleIndex: number
) {
  const next = cloneFragments(editFragments);
  const dragIndex = next.findIndex((fragment) => fragment.fragment_id === draggedId);

  if (dragIndex === -1) {
    return next;
  }

  const [dragged] = next.splice(dragIndex, 1);
  const visibleAfterRemoval = next
    .map((fragment, realIndex) => ({ fragment, realIndex }))
    .filter(({ fragment }) => !fragment.excluded);

  let insertAt = next.length;
  if (targetVisibleIndex <= 0 && visibleAfterRemoval.length) {
    insertAt = visibleAfterRemoval[0].realIndex;
  } else if (targetVisibleIndex < visibleAfterRemoval.length) {
    insertAt = visibleAfterRemoval[targetVisibleIndex].realIndex;
  }

  next.splice(insertAt, 0, dragged);
  return next;
}

export function applySharedBoundary(
  fragments: Fragment[],
  leftRealIndex: number,
  deltaFrames: number
) {
  const next = cloneFragments(fragments);
  const left = next[leftRealIndex];
  const right = next[leftRealIndex + 1];

  if (!left || !right) {
    return next;
  }

  const clampedDelta = Math.max(
    -(left.duration - MIN_FRAGMENT_DURATION),
    Math.min(deltaFrames, right.duration - MIN_FRAGMENT_DURATION)
  );

  const updatedLeft = refreshFragmentThumbnailIfNeeded(
    {
      ...left,
      end_frame: left.end_frame + clampedDelta,
      duration: left.duration + clampedDelta
    },
    left
  );

  const updatedRight = refreshFragmentThumbnailIfNeeded(
    {
      ...right,
      start_frame: right.start_frame + clampedDelta,
      duration: right.duration - clampedDelta
    },
    right
  );

  next[leftRealIndex] = updatedLeft;
  next[leftRealIndex + 1] = updatedRight;
  return next;
}

export function resolveSeamChain(seam: SyntheticCollapsedSeam, editFragments: Fragment[]) {
  const chain = editFragments.slice(seam.leftRealIndex, seam.rightRealIndex + 1);
  if (!chain.length || chain[0].fragment_id !== seam.leftVisibleFragmentId) {
    return null;
  }
  return cloneFragments(chain);
}

function dedupeFragmentIds(fragmentIds: string[]) {
  return Array.from(new Set(fragmentIds));
}

function findFragmentIndex(editFragments: Fragment[], fragmentId: string) {
  return editFragments.findIndex((fragment) => fragment.fragment_id === fragmentId);
}

function findNextStructuralSameSource(editFragments: Fragment[], fragment: Fragment) {
  return editFragments
    .filter(
      (candidate) =>
        candidate.source_video === fragment.source_video &&
        candidate.start_frame > fragment.start_frame
    )
    .sort((left, right) => left.start_frame - right.start_frame)[0] || null;
}

function findPreviousStructuralSameSource(editFragments: Fragment[], fragment: Fragment) {
  return editFragments
    .filter(
      (candidate) =>
        candidate.source_video === fragment.source_video &&
        candidate.start_frame < fragment.start_frame
    )
    .sort((left, right) => right.start_frame - left.start_frame)[0] || null;
}

export function resolvePrecisionScope(
  handle: PrecisionEntryHandle,
  editFragments: Fragment[]
): PrecisionEditorScopeResult {
  if (handle.type === 'synthetic-seam') {
    const leftIndex = findFragmentIndex(editFragments, handle.leftVisibleFragmentId);
    const rightIndex = findFragmentIndex(editFragments, handle.rightVisibleFragmentId);
    if (leftIndex === -1 || rightIndex === -1 || leftIndex >= rightIndex) {
      return { ok: false, reason: 'invalid-handle' };
    }

    const fragmentIds = editFragments
      .slice(leftIndex, rightIndex + 1)
      .map((fragment) => fragment.fragment_id);
    const hiddenIds = fragmentIds.slice(1, -1);
    const expectedHidden = [...handle.hiddenFragmentIds].sort().join('|');
    const actualHidden = hiddenIds.filter((fragmentId) => handle.hiddenFragmentIds.includes(fragmentId)).sort().join('|');

    if (expectedHidden !== actualHidden) {
      return { ok: false, reason: 'invalid-handle' };
    }

    if (fragmentIds.length > 4) {
      return { ok: false, reason: 'too-many-fragments' };
    }

    return {
      ok: true,
      mode: 'same-source',
      fragmentIds
    };
  }

  const leftFragment = editFragments.find((fragment) => fragment.fragment_id === handle.leftFragmentId);
  const rightFragment = editFragments.find((fragment) => fragment.fragment_id === handle.rightFragmentId);
  if (!leftFragment || !rightFragment) {
    return { ok: false, reason: 'invalid-handle' };
  }

  if (handle.type === 'same-source-boundary') {
    if (leftFragment.source_video !== rightFragment.source_video) {
      return { ok: false, reason: 'invalid-handle' };
    }

    const leftIndex = findFragmentIndex(editFragments, leftFragment.fragment_id);
    const rightIndex = findFragmentIndex(editFragments, rightFragment.fragment_id);
    if (leftIndex === -1 || rightIndex === -1 || leftIndex >= rightIndex) {
      return { ok: false, reason: 'invalid-handle' };
    }

    const fragmentIds = editFragments
      .slice(leftIndex, rightIndex + 1)
      .map((fragment) => fragment.fragment_id);

    if (fragmentIds.length > 4) {
      return { ok: false, reason: 'too-many-fragments' };
    }

    return {
      ok: true,
      mode: 'same-source',
      fragmentIds
    };
  }

  if (leftFragment.source_video === rightFragment.source_video) {
    return { ok: false, reason: 'invalid-handle' };
  }

  const fragmentIds = dedupeFragmentIds([
    leftFragment.fragment_id,
    findNextStructuralSameSource(editFragments, leftFragment)?.fragment_id || '',
    findPreviousStructuralSameSource(editFragments, rightFragment)?.fragment_id || '',
    rightFragment.fragment_id
  ].filter(Boolean));

  if (fragmentIds.length < 2) {
    return { ok: false, reason: 'not-local-refinement' };
  }

  if (fragmentIds.length > 4) {
    return { ok: false, reason: 'too-many-fragments' };
  }

  return {
    ok: true,
    mode: 'cross-source',
    fragmentIds
  };
}

export function buildOverlayState(
  entryType: PrecisionOverlayState['entryType'],
  mode: 'same-source' | 'cross-source',
  fragmentIds: string[],
  editFragments: Fragment[],
  anchorRect: DOMRect
): PrecisionOverlayState {
  const chainRealIndices = fragmentIds
    .map((fragmentId) => findFragmentIndex(editFragments, fragmentId))
    .filter((index) => index >= 0);

  return {
    entryType,
    mode,
    fragmentIds,
    chainRealIndices,
    anchorRect,
    activeBoundaryId: null
  };
}

export function unionSourceFragments(editFragments: Fragment[], reservedFragments: Fragment[]) {
  const map = new Map<string, Fragment>();

  [...editFragments, ...reservedFragments].forEach((fragment) => {
    if (!map.has(fragment.fragment_id)) {
      map.set(fragment.fragment_id, cloneFragment(fragment));
    }
  });

  return Array.from(map.values()).sort((left, right) => {
    if (left.source_video === right.source_video) {
      return left.start_frame - right.start_frame;
    }
    return left.source_video.localeCompare(right.source_video);
  });
}

export function buildFragmentOverrideMap(fragments: Fragment[]) {
  return new Map(fragments.map((fragment) => [fragment.fragment_id, fragment.duration]));
}

export function getVisibleFragmentIndex(editFragments: Fragment[], fragmentId: string) {
  return getVisibleFragments(editFragments).findIndex((fragment) => fragment.fragment_id === fragmentId);
}

function resolveBoundaryLeftIndex(
  editFragments: Fragment[],
  leftFragmentId: string,
  rightFragmentId: string
) {
  return editFragments.findIndex(
    (fragment, index) =>
      fragment.fragment_id === leftFragmentId &&
      editFragments[index + 1]?.fragment_id === rightFragmentId
  );
}

function applyReplaceOperation(
  state: StableBoardState,
  operation: UndoReplaceFragmentOperation,
  direction: 'undo' | 'redo'
) {
  const nextEditFragments = cloneFragments(state.editFragments);
  const nextReservedFragments = cloneFragments(state.reservedFragments);
  const nextHoldAreaPositions = cloneHoldPositions(state.holdAreaPositions);

  const incomingFragmentId =
    direction === 'undo' ? operation.targetFragmentId : operation.sourceFragmentId;
  const outgoingFragmentId =
    direction === 'undo' ? operation.sourceFragmentId : operation.targetFragmentId;

  let editIndex = operation.editIndex;
  if (nextEditFragments[editIndex]?.fragment_id !== outgoingFragmentId) {
    editIndex = nextEditFragments.findIndex(
      (fragment) => fragment.fragment_id === outgoingFragmentId
    );
  }

  const reservedIndex = nextReservedFragments.findIndex(
    (fragment) => fragment.fragment_id === incomingFragmentId
  );

  if (editIndex === -1 || reservedIndex === -1) {
    return null;
  }

  const outgoingFragment = nextEditFragments[editIndex];
  const incomingFragment = nextReservedFragments[reservedIndex];
  nextEditFragments[editIndex] = { ...incomingFragment, excluded: false };
  nextReservedFragments.splice(reservedIndex, 1);

  const insertReservedIndex =
    direction === 'undo'
      ? operation.sourceReservedIndexBefore
      : operation.targetReservedIndexAfter;
  const clampedReservedIndex = Math.max(0, Math.min(insertReservedIndex, nextReservedFragments.length));
  nextReservedFragments.splice(clampedReservedIndex, 0, { ...outgoingFragment, excluded: false });

  const incomingPosition = nextHoldAreaPositions[incomingFragmentId] || { x: 18, y: 18 };
  delete nextHoldAreaPositions[incomingFragmentId];
  nextHoldAreaPositions[outgoingFragmentId] = incomingPosition;

  return buildStableBoardState(nextEditFragments, nextReservedFragments, nextHoldAreaPositions);
}

function applyUndoOperation(
  state: StableBoardState,
  operation: UndoOperation,
  direction: 'undo' | 'redo'
) {
  if (operation.kind === 'reorder') {
    const targetVisibleIndex =
      direction === 'undo' ? operation.fromVisibleIndex : operation.toVisibleIndex;
    const nextEditFragments = reorderVisibleFragment(
      state.editFragments,
      operation.fragmentId,
      targetVisibleIndex
    );
    return buildStableBoardState(
      nextEditFragments,
      state.reservedFragments,
      state.holdAreaPositions
    );
  }

  if (operation.kind === 'replace-fragment') {
    return applyReplaceOperation(state, operation, direction);
  }

  const leftRealIndex = resolveBoundaryLeftIndex(
    state.editFragments,
    operation.leftFragmentId,
    operation.rightFragmentId
  );

  if (leftRealIndex === -1) {
    return null;
  }

  const deltaFrames = direction === 'undo' ? -operation.deltaFrames : operation.deltaFrames;
  const nextEditFragments = applySharedBoundary(state.editFragments, leftRealIndex, deltaFrames);
  return buildStableBoardState(nextEditFragments, state.reservedFragments, state.holdAreaPositions);
}

export function deriveBoundaryUndoOperation(
  kind: UndoBoundaryOperation['kind'],
  previousFragments: Fragment[],
  nextFragments: Fragment[]
) {
  for (let index = 0; index < Math.min(previousFragments.length, nextFragments.length) - 1; index += 1) {
    const previousLeft = previousFragments[index];
    const previousRight = previousFragments[index + 1];
    const nextLeft = nextFragments[index];
    const nextRight = nextFragments[index + 1];

    if (
      previousLeft.fragment_id !== nextLeft.fragment_id ||
      previousRight.fragment_id !== nextRight.fragment_id
    ) {
      continue;
    }

    const leftDelta = nextLeft.duration - previousLeft.duration;
    const rightDelta = nextRight.duration - previousRight.duration;

    if (leftDelta !== 0 && leftDelta === -rightDelta) {
      return {
        kind,
        leftFragmentId: previousLeft.fragment_id,
        rightFragmentId: previousRight.fragment_id,
        deltaFrames: leftDelta
      } satisfies UndoBoundaryOperation;
    }
  }

  return undefined;
}

export function restoreFromUndo(
  entry: UndoEntry,
  currentState?: StableBoardState,
  direction: 'undo' | 'redo' = 'undo'
) {
  if (entry.op && currentState) {
    const restoredFromOperation = applyUndoOperation(currentState, entry.op, direction);
    if (restoredFromOperation) {
      return {
        ...restoredFromOperation,
        restoreMode: 'op' as const
      };
    }
  }

  return {
    editFragments: cloneFragments(entry.prevEditFragments),
    reservedFragments: cloneFragments(entry.prevReservedFragments),
    holdAreaPositions: cloneHoldPositions(entry.prevHoldAreaPositions),
    restoreMode: 'snapshot' as const
  };
}
