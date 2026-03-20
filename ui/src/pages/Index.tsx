import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BoundaryPrecisionOverlay } from '../components/BoundaryPrecisionOverlay';
import { CenterPanel } from '../components/CenterPanel';
import { beginGlobalDragLifecycle, FragmentMap } from '../components/FragmentMap';
import { LeftNav } from '../components/LeftNav';
import { OriginalPanorama } from '../components/OriginalPanorama';
import { ReservedFragments } from '../components/ReservedFragments';
import { buildInitialBoardState } from '../data/fragmentData';
import {
  applySharedBoundary,
  buildFragmentOverrideMap,
  buildOverlayState,
  buildStableBoardState,
  CENTER_WIDTH_STORAGE_KEY,
  cloneFragments,
  cloneHoldPositions,
  createUndoEntry,
  deriveBoundaryUndoOperation,
  formatDuration,
  getVisibleFragmentIndex,
  getVisibleFragments,
  MAX_UNDO_DEPTH,
  MIN_FRAGMENT_DURATION,
  reorderVisibleFragment,
  resolvePrecisionScope,
  restoreFromUndo,
  unionSourceFragments
} from '../utils/fragmentUtils';
import { resolvePrecisionChatRequest } from '../utils/precisionEntryChat';
import type {
  Fragment,
  HoldPosition,
  PrecisionEntryHandle,
  PrecisionOverlayState,
  PrimaryInteractionState,
  StableBoardState,
  StructuralBoundaryItem,
  ToastMessage,
  UndoActionType,
  UndoEntry
} from '../types/boundaryTypes';

type PartialBoardState = {
  editFragments?: Fragment[];
  reservedFragments?: Fragment[];
  holdAreaPositions?: Record<string, HoldPosition>;
};

function clampCenterWidth(totalWidth: number, nextX: number) {
  const leftNav = 56;
  const rightMin = 400;
  return Math.max(260, Math.min(totalWidth - leftNav - rightMin, nextX - leftNav));
}

function hasBoundaryChange(nextFragments: Fragment[], prevFragments: Fragment[]) {
  return nextFragments.some((fragment, index) => {
    const previous = prevFragments[index];
    return (
      !previous ||
      previous.start_frame !== fragment.start_frame ||
      previous.end_frame !== fragment.end_frame ||
      previous.duration !== fragment.duration ||
      previous.excluded !== fragment.excluded
    );
  });
}

function validateFragments(fragments: Fragment[]) {
  return fragments.every((fragment) => fragment.duration >= MIN_FRAGMENT_DURATION);
}

export default function Index() {
  const initialBoard = useMemo(() => buildInitialBoardState(), []);
  const appRef = useRef<HTMLDivElement | null>(null);
  const dragFragmentIdRef = useRef<string | null>(null);
  const dragOriginRef = useRef<'edit' | 'reserved' | null>(null);
  const dragTargetVisibleIndexRef = useRef<number | null>(null);
  const boundaryDragAbortRef = useRef<(() => void) | null>(null);
  const holdDragAbortRef = useRef<(() => void) | null>(null);
  const boundaryDragCleanupRef = useRef<(() => void) | null>(null);
  const holdDragCleanupRef = useRef<(() => void) | null>(null);

  const [sourceVideos] = useState(initialBoard.sourceVideos);
  const [activeNavItem, setActiveNavItem] = useState('structure');
  const [activeSource, setActiveSource] = useState(initialBoard.editFragments[0]?.source_video || 'A');
  const [selectedFragmentId, setSelectedFragmentId] = useState<string | null>(null);
  const [precisionPairSelectionIds, setPrecisionPairSelectionIds] = useState<string[]>([]);
  const [highlightedPanoramaFrag, setHighlightedPanoramaFrag] = useState<string | null>(null);
  const [focusExpandedId, setFocusExpandedId] = useState<string | null>(null);
  const [timeLensId, setTimeLensId] = useState<string | null>(null);
  const [playingFragmentId, setPlayingFragmentId] = useState<string | null>(null);
  const [playProgress, setPlayProgress] = useState(0);
  const [intelligenceOn, setIntelligenceOn] = useState(true);
  const [editFragments, setEditFragments] = useState(initialBoard.editFragments);
  const [reservedFragments, setReservedFragments] = useState(initialBoard.reservedFragments);
  const [holdAreaPositions, setHoldAreaPositions] = useState(initialBoard.holdAreaPositions);
  const [boundaryPreviewHighlightIds, setBoundaryPreviewHighlightIds] = useState<string[]>([]);
  const [boundaryPreviewOverrides, setBoundaryPreviewOverrides] = useState<Map<string, number>>(new Map());
  const [precisionPreviewHighlightIds, setPrecisionPreviewHighlightIds] = useState<string[]>([]);
  const [centerWidth, setCenterWidth] = useState(() => {
    if (typeof window === 'undefined') {
      return 340;
    }

    const saved = Number(window.localStorage.getItem(CENTER_WIDTH_STORAGE_KEY));
    return Number.isFinite(saved) && saved >= 260 ? saved : 340;
  });
  const [precisionOverlay, setPrecisionOverlay] = useState<PrecisionOverlayState | null>(null);
  const [undoStack, setUndoStack] = useState<UndoEntry[]>([]);
  const [redoStack, setRedoStack] = useState<UndoEntry[]>([]);
  const [lastRestoreMode, setLastRestoreMode] = useState<'none' | 'op' | 'snapshot'>('none');
  const [lastRestoreDirection, setLastRestoreDirection] = useState<'none' | 'undo' | 'redo'>('none');
  const [interactionMode, setInteractionMode] = useState<PrimaryInteractionState>('IDLE');
  const [dragOrigin, setDragOrigin] = useState<'edit' | 'reserved' | null>(null);
  const [dragTargetVisibleIndex, setDragTargetVisibleIndex] = useState<number | null>(null);
  const [replaceTargetId, setReplaceTargetId] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [chatInput, setChatInput] = useState('');

  const lastStableStateRef = useRef(
    buildStableBoardState(initialBoard.editFragments, initialBoard.reservedFragments, initialBoard.holdAreaPositions)
  );

  const visibleFragments = useMemo(() => getVisibleFragments(editFragments), [editFragments]);
  const sourceFragments = useMemo(
    () => unionSourceFragments(editFragments, reservedFragments),
    [editFragments, reservedFragments]
  );
  const selectedFragment = useMemo(
    () => (selectedFragmentId ? sourceFragments.find((fragment) => fragment.fragment_id === selectedFragmentId) || null : null),
    [sourceFragments, selectedFragmentId]
  );
  const previewHighlightIds = useMemo(
    () => Array.from(new Set([...boundaryPreviewHighlightIds, ...precisionPreviewHighlightIds])),
    [boundaryPreviewHighlightIds, precisionPreviewHighlightIds]
  );

  useEffect(() => {
    lastStableStateRef.current = buildStableBoardState(editFragments, reservedFragments, holdAreaPositions);
  }, [editFragments, reservedFragments, holdAreaPositions]);

  useEffect(() => {
    if (!selectedFragmentId) {
      return;
    }

    const stillExists = sourceFragments.some((fragment) => fragment.fragment_id === selectedFragmentId);
    if (!stillExists) {
      setSelectedFragmentId(null);
    }
  }, [sourceFragments, selectedFragmentId]);

  useEffect(() => {
    setPrecisionPairSelectionIds((current) =>
      current.filter((fragmentId) => editFragments.some((fragment) => fragment.fragment_id === fragmentId))
    );
  }, [editFragments]);

  useEffect(() => {
    window.localStorage.setItem(CENTER_WIDTH_STORAGE_KEY, String(centerWidth));
  }, [centerWidth]);

  useEffect(() => {
    if (!playingFragmentId) {
      setPlayProgress(0);
      return;
    }

    const interval = window.setInterval(() => {
      setPlayProgress((current) => {
        const next = current + 2;
        if (next >= 100) {
          setPlayingFragmentId(null);
          return 0;
        }
        return next;
      });
    }, 50);

    return () => window.clearInterval(interval);
  }, [playingFragmentId]);

  function pushToast(kind: ToastMessage['kind'], message: string) {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setToasts((current) => [...current, { id, kind, message }].slice(-4));
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 2800);
  }

  function announcePolite(message: string) {
    setAnnouncement('');
    window.setTimeout(() => setAnnouncement(message), 20);
  }

  function clearBoundaryPreview() {
    setBoundaryPreviewHighlightIds([]);
    setBoundaryPreviewOverrides(new Map());
  }

  function clearPrecisionPreview() {
    setPrecisionPreviewHighlightIds([]);
  }

  function clearPrecisionPairSelection() {
    setPrecisionPairSelectionIds([]);
  }

  function resetEphemeralState(clearSelection = false) {
    clearBoundaryPreview();
    clearPrecisionPreview();
    setPrecisionOverlay(null);
    setPlayingFragmentId(null);
    setPlayProgress(0);
    setHighlightedPanoramaFrag(null);
    setFocusExpandedId(null);
    setTimeLensId(null);
    setInteractionMode('IDLE');

    if (clearSelection) {
      setSelectedFragmentId(null);
      clearPrecisionPairSelection();
    }
  }

  function syncInteractionMode(nextFocusId: string | null, nextTimeLensId: string | null) {
    if (nextTimeLensId) {
      setInteractionMode('TIME_LENS');
      return;
    }
    if (nextFocusId) {
      setInteractionMode('FOCUS_EXPANDED');
      return;
    }
    setInteractionMode('IDLE');
  }

  function restoreStableState(message: string) {
    const stable = lastStableStateRef.current;
    setEditFragments(stable.editFragments);
    setReservedFragments(stable.reservedFragments);
    setHoldAreaPositions(stable.holdAreaPositions);
    resetEphemeralState(true);
    pushToast('error', message);
  }

  function dismissOverlayPreview() {
    setPrecisionOverlay(null);
    clearPrecisionPreview();
  }

  function commitMutation(
    type: UndoActionType,
    label: string,
    producer: () => PartialBoardState,
    buildOperation?: (
      previousState: StableBoardState,
      nextState: StableBoardState
    ) => UndoEntry['op'] | undefined,
    onCommitSuccess?: (nextState: StableBoardState) => void
  ) {
    try {
      const previousState = lastStableStateRef.current;
      const nextState = producer();
      const nextEditFragments = nextState.editFragments || editFragments;
      const nextReservedFragments = nextState.reservedFragments || reservedFragments;
      const nextHoldAreaPositions = nextState.holdAreaPositions || holdAreaPositions;

      if (!validateFragments(nextEditFragments) || !validateFragments(nextReservedFragments)) {
        throw new Error('Invalid fragment duration');
      }

      const resolvedNextState = buildStableBoardState(
        nextEditFragments,
        nextReservedFragments,
        nextHoldAreaPositions
      );
      const snapshot = createUndoEntry(
        type,
        label,
        previousState,
        buildOperation?.(previousState, resolvedNextState)
      );

      setUndoStack((current) => [...current.slice(-(MAX_UNDO_DEPTH - 1)), snapshot]);
      setRedoStack([]);

      if (nextState.editFragments) {
        setEditFragments(nextState.editFragments);
      }
      if (nextState.reservedFragments) {
        setReservedFragments(nextState.reservedFragments);
      }
      if (nextState.holdAreaPositions) {
        setHoldAreaPositions(nextState.holdAreaPositions);
      }

      onCommitSuccess?.(resolvedNextState);
      announcePolite(label);
    } catch (error) {
      restoreStableState(`${label} failed. Last stable structure restored.`);
    }
  }

  function recallSource(fragmentIds: string[]) {
    const nextTarget = sourceFragments.find((fragment) => fragmentIds.includes(fragment.fragment_id));
    if (!nextTarget) {
      return;
    }
    setActiveSource(nextTarget.source_video);
    setHighlightedPanoramaFrag(nextTarget.fragment_id);
  }

  function handlePrecisionPairSelectionToggle(fragment: Fragment) {
    dismissOverlayPreview();
    setFocusExpandedId(null);
    setTimeLensId(null);
    setInteractionMode('IDLE');
    setSelectedFragmentId(fragment.fragment_id);
    setActiveSource(fragment.source_video);
    setHighlightedPanoramaFrag(fragment.fragment_id);
    setPrecisionPairSelectionIds((current) => {
      const nextSelection = current.includes(fragment.fragment_id)
        ? current.filter((fragmentId) => fragmentId !== fragment.fragment_id)
        : current.length === 2
          ? [current[1], fragment.fragment_id]
          : [...current, fragment.fragment_id];

      announcePolite(
        nextSelection.length
          ? `Precision pair selection: ${nextSelection.join(' / ')}`
          : 'Precision pair selection cleared.'
      );

      return nextSelection;
    });
  }

  function handlePanoramaSelect(fragment: Fragment) {
    if (selectedFragmentId === fragment.fragment_id && !focusExpandedId && !timeLensId) {
      resetEphemeralState(true);
      announcePolite('Panorama selection cleared.');
      return;
    }

    dismissOverlayPreview();
    clearPrecisionPairSelection();
    setSelectedFragmentId(fragment.fragment_id);
    setActiveSource(fragment.source_video);
    setHighlightedPanoramaFrag(fragment.fragment_id);
    setFocusExpandedId(null);
    setTimeLensId(null);
    setInteractionMode('IDLE');
    announcePolite(`${fragment.fragment_id} selected from panorama.`);
  }

  function handleEditFragmentClick(fragment: Fragment) {
    if (focusExpandedId === fragment.fragment_id && !timeLensId) {
      resetEphemeralState(true);
      announcePolite(`${fragment.fragment_id} restored to normal board state.`);
      return;
    }

    dismissOverlayPreview();
    clearPrecisionPairSelection();
    setSelectedFragmentId(fragment.fragment_id);
    setActiveSource(fragment.source_video);
    setHighlightedPanoramaFrag(fragment.fragment_id);
    setFocusExpandedId(fragment.fragment_id);
    setTimeLensId(null);
    setInteractionMode('FOCUS_EXPANDED');
    announcePolite(`${fragment.fragment_id} focus-expanded.`);
  }

  function handleEditFragmentDoubleClick(fragment: Fragment) {
    dismissOverlayPreview();
    clearPrecisionPairSelection();
    setSelectedFragmentId(fragment.fragment_id);
    setActiveSource(fragment.source_video);
    setHighlightedPanoramaFrag(fragment.fragment_id);
    setFocusExpandedId(null);
    setTimeLensId(fragment.fragment_id);
    setInteractionMode('TIME_LENS');
    announcePolite(`${fragment.fragment_id} entered Time Lens.`);
  }

  function handleReservedSelect(fragment: Fragment) {
    if (selectedFragmentId === fragment.fragment_id && !focusExpandedId && !timeLensId) {
      resetEphemeralState(true);
      announcePolite('Hold Area selection cleared.');
      return;
    }

    dismissOverlayPreview();
    clearPrecisionPairSelection();
    setSelectedFragmentId(fragment.fragment_id);
    setActiveSource(fragment.source_video);
    setHighlightedPanoramaFrag(fragment.fragment_id);
    setFocusExpandedId(null);
    setTimeLensId(null);
    setInteractionMode('IDLE');
    announcePolite(`${fragment.fragment_id} selected from Hold Area.`);
  }

  function handlePlayToggle(fragment: Fragment) {
    if (playingFragmentId === fragment.fragment_id) {
      setPlayingFragmentId(null);
      setPlayProgress(0);
      announcePolite(`${fragment.fragment_id} playback stopped.`);
      return;
    }

    try {
      setPlayingFragmentId(fragment.fragment_id);
      setPlayProgress(0);
      announcePolite(`${fragment.fragment_id} playback started.`);
    } catch (error) {
      pushToast('error', `Playback failed for ${fragment.fragment_id}.`);
      setPlayingFragmentId(null);
      setPlayProgress(0);
    }
  }

  function handleExcludeToggle(fragment: Fragment) {
    commitMutation(fragment.excluded ? 'restore' : 'exclude', `${fragment.excluded ? 'Restored' : 'Excluded'} ${fragment.fragment_id}`, () => ({
      editFragments: editFragments.map((candidate) =>
        candidate.fragment_id === fragment.fragment_id
          ? {
              ...candidate,
              excluded: !candidate.excluded
            }
          : candidate
      )
    }));
  }

  function handleMoveToHold(fragment: Fragment) {
    commitMutation('move-to-hold', `Moved ${fragment.fragment_id} to Hold Area`, () => {
      const nextEditFragments = editFragments.filter((candidate) => candidate.fragment_id !== fragment.fragment_id);
      const nextReservedFragments = [...reservedFragments, { ...fragment, excluded: false }];
      const nextPositions = cloneHoldPositions(holdAreaPositions);
      nextPositions[fragment.fragment_id] = {
        x: 18 + reservedFragments.length * 22,
        y: 18 + (reservedFragments.length % 2) * 24
      };

      return {
        editFragments: nextEditFragments,
        reservedFragments: nextReservedFragments,
        holdAreaPositions: nextPositions
      };
    }, undefined, (resolvedNextState) => {
      const stillExists = resolvedNextState.reservedFragments.some(
        (candidate) => candidate.fragment_id === fragment.fragment_id
      );
      if (!stillExists) {
        return;
      }

      setSelectedFragmentId(fragment.fragment_id);
      setActiveSource(fragment.source_video);
      setHighlightedPanoramaFrag(fragment.fragment_id);
    });
  }

  function handleRestoreFromHold(fragment: Fragment) {
    commitMutation('restore-from-hold', `Restored ${fragment.fragment_id} from Hold Area`, () => {
      const nextReservedFragments = reservedFragments.filter((candidate) => candidate.fragment_id !== fragment.fragment_id);
      const nextEditFragments = [...editFragments, { ...fragment, excluded: false }];
      const nextPositions = cloneHoldPositions(holdAreaPositions);
      delete nextPositions[fragment.fragment_id];
      return {
        editFragments: nextEditFragments,
        reservedFragments: nextReservedFragments,
        holdAreaPositions: nextPositions
      };
    }, undefined, (resolvedNextState) => {
      const stillExists = resolvedNextState.editFragments.some(
        (candidate) => candidate.fragment_id === fragment.fragment_id
      );
      if (!stillExists) {
        return;
      }

      setSelectedFragmentId(fragment.fragment_id);
      setActiveSource(fragment.source_video);
      setHighlightedPanoramaFrag(fragment.fragment_id);
    });
  }

  function handleDragStart(fragmentId: string, origin: 'edit' | 'reserved') {
    dragFragmentIdRef.current = fragmentId;
    dragOriginRef.current = origin;
    dragTargetVisibleIndexRef.current = null;
    setDragOrigin(origin);
    setDragTargetVisibleIndex(null);
    setReplaceTargetId(null);
  }

  function handleDragTargetIndexChange(index: number | null) {
    if (dragOriginRef.current !== 'edit') {
      return;
    }

    dragTargetVisibleIndexRef.current = index;
    setDragTargetVisibleIndex(index);
  }

  function handleReplaceTargetChange(fragmentId: string | null) {
    setReplaceTargetId(fragmentId);
  }

  function clearDragState() {
    dragFragmentIdRef.current = null;
    dragOriginRef.current = null;
    dragTargetVisibleIndexRef.current = null;
    setDragOrigin(null);
    setDragTargetVisibleIndex(null);
    setReplaceTargetId(null);
  }

  function handleDragDrop() {
    const draggedId = dragFragmentIdRef.current;
    const targetVisibleIndex = dragTargetVisibleIndexRef.current;
    if (!draggedId || dragOriginRef.current !== 'edit' || targetVisibleIndex === null) {
      return false;
    }

    commitMutation('reorder', `Reordered ${draggedId}`, () => ({
      editFragments: reorderVisibleFragment(editFragments, draggedId, targetVisibleIndex)
    }), (previousState, nextState) => {
      const fromVisibleIndex = getVisibleFragmentIndex(previousState.editFragments, draggedId);
      const toVisibleIndex = getVisibleFragmentIndex(nextState.editFragments, draggedId);

      if (
        fromVisibleIndex === -1 ||
        toVisibleIndex === -1 ||
        fromVisibleIndex === toVisibleIndex
      ) {
        return undefined;
      }

      return {
        kind: 'reorder',
        fragmentId: draggedId,
        fromVisibleIndex,
        toVisibleIndex
      };
    });

    return true;
  }

  function handleReplaceDrop(targetFragmentId: string) {
    const draggedId = dragFragmentIdRef.current;
    if (!draggedId || dragOriginRef.current !== 'reserved') {
      clearDragState();
      return;
    }

    const sourceFragment = reservedFragments.find((fragment) => fragment.fragment_id === draggedId);
    const targetIndex = editFragments.findIndex((fragment) => fragment.fragment_id === targetFragmentId);
    const targetFragment = targetIndex === -1 ? null : editFragments[targetIndex];

    if (!sourceFragment || !targetFragment) {
      clearDragState();
      return;
    }

    commitMutation('replace-fragment', `Replaced ${targetFragment.fragment_id} with ${sourceFragment.fragment_id}`, () => {
      const nextEditFragments = cloneFragments(editFragments);
      nextEditFragments[targetIndex] = { ...sourceFragment, excluded: false };

      const nextReservedFragments = [
        ...reservedFragments.filter((fragment) => fragment.fragment_id !== sourceFragment.fragment_id),
        { ...targetFragment, excluded: false }
      ];

      const nextPositions = cloneHoldPositions(holdAreaPositions);
      const sourcePosition = nextPositions[sourceFragment.fragment_id] || { x: 18, y: 18 };
      delete nextPositions[sourceFragment.fragment_id];
      nextPositions[targetFragment.fragment_id] = sourcePosition;

      return {
        editFragments: nextEditFragments,
        reservedFragments: nextReservedFragments,
        holdAreaPositions: nextPositions
      };
    }, (previousState, nextState) => {
      const sourceReservedIndexBefore = previousState.reservedFragments.findIndex(
        (fragment) => fragment.fragment_id === sourceFragment.fragment_id
      );
      const targetReservedIndexAfter = nextState.reservedFragments.findIndex(
        (fragment) => fragment.fragment_id === targetFragment.fragment_id
      );

      if (sourceReservedIndexBefore === -1 || targetReservedIndexAfter === -1) {
        return undefined;
      }

      return {
        kind: 'replace-fragment',
        sourceFragmentId: sourceFragment.fragment_id,
        targetFragmentId: targetFragment.fragment_id,
        editIndex: targetIndex,
        sourceReservedIndexBefore,
        targetReservedIndexAfter
      };
    }, (resolvedNextState) => {
      dismissOverlayPreview();
      setFocusExpandedId(null);
      setTimeLensId(null);
      setInteractionMode('IDLE');

      const stillExists = resolvedNextState.editFragments.some(
        (candidate) => candidate.fragment_id === sourceFragment.fragment_id
      );
      if (!stillExists) {
        return;
      }

      setSelectedFragmentId(sourceFragment.fragment_id);
      setActiveSource(sourceFragment.source_video);
      setHighlightedPanoramaFrag(sourceFragment.fragment_id);
    });

    clearDragState();
  }

  function startBoundaryDrag(item: StructuralBoundaryItem, startX: number) {
    boundaryDragCleanupRef.current?.();
    boundaryDragCleanupRef.current = null;
    const originalFragments = cloneFragments(editFragments);
    let latestFragments = originalFragments;
    let latestDelta = 0;

    setInteractionMode('BOUNDARY_DRAGGING');
    recallSource([item.leftFragment.fragment_id, item.rightFragment.fragment_id]);

    const cleanup = () => {
      boundaryDragCleanupRef.current?.();
      boundaryDragCleanupRef.current = null;
      boundaryDragAbortRef.current = null;
      clearBoundaryPreview();
      syncInteractionMode(focusExpandedId, timeLensId);
    };

    const revert = () => {
      setEditFragments(originalFragments);
      setSelectedFragmentId(null);
      cleanup();
      announcePolite('Boundary drag cancelled.');
    };

    const applyPreviewState = (nextFragments: Fragment[]) => {
      setBoundaryPreviewOverrides(buildFragmentOverrideMap(nextFragments));
      setBoundaryPreviewHighlightIds([item.leftFragment.fragment_id, item.rightFragment.fragment_id]);
      recallSource([item.leftFragment.fragment_id, item.rightFragment.fragment_id]);
    };

    const scheduleBoundaryPreview = (clientX: number) => {
      latestDelta = Math.round((clientX - startX) / 0.7);
      latestFragments = applySharedBoundary(originalFragments, item.leftRealIndex, latestDelta);
      applyPreviewState(latestFragments);
    };

    const onPointerMove = (moveEvent: PointerEvent) => {
      scheduleBoundaryPreview(moveEvent.clientX);
    };

    const commitBoundaryDrag = () => {
      const changed = hasBoundaryChange(latestFragments, originalFragments);
      cleanup();

      if (!changed) {
        setEditFragments(originalFragments);
        return;
      }

      commitMutation(
        'boundary-resize',
        `Adjusted boundary ${item.leftFragment.fragment_id} / ${item.rightFragment.fragment_id}`,
        () => ({
          editFragments: latestFragments
        }),
        (previousState, nextState) =>
          deriveBoundaryUndoOperation(
            'boundary-resize',
            previousState.editFragments,
            nextState.editFragments
          )
      );
    };

    const onPointerUp = () => {
      commitBoundaryDrag();
    };

    const onPointerCancel = () => {
      revert();
    };

    const onWindowBlur = () => {
      revert();
    };

    boundaryDragAbortRef.current = revert;
    boundaryDragCleanupRef.current = beginGlobalDragLifecycle({
      cursor: 'col-resize',
      listeners: [
        { target: 'document', type: 'pointermove', listener: onPointerMove as EventListener },
        { target: 'document', type: 'pointerup', listener: onPointerUp as EventListener },
        { target: 'document', type: 'pointercancel', listener: onPointerCancel as EventListener },
        { target: 'window', type: 'pointermove', listener: onPointerMove as EventListener },
        { target: 'window', type: 'pointerup', listener: onPointerUp as EventListener },
        { target: 'window', type: 'pointercancel', listener: onPointerCancel as EventListener },
        { target: 'window', type: 'blur', listener: onWindowBlur as EventListener }
      ]
    });
  }

  function handleBoundaryPointerDown(item: StructuralBoundaryItem, event: React.PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) {
      return;
    }

    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    startBoundaryDrag(item, event.clientX);
  }

  function handleBoundaryNudge(item: StructuralBoundaryItem, deltaFrames: number) {
    commitMutation(
      'boundary-resize',
      `Nudged boundary ${item.leftFragment.fragment_id} / ${item.rightFragment.fragment_id}`,
      () => ({
        editFragments: applySharedBoundary(editFragments, item.leftRealIndex, deltaFrames)
      }),
      (previousState, nextState) =>
        deriveBoundaryUndoOperation(
          'boundary-resize',
          previousState.editFragments,
          nextState.editFragments
        )
    );
    recallSource([item.leftFragment.fragment_id, item.rightFragment.fragment_id]);
  }

  function openPrecisionEditor({
    entryType,
    mode,
    fragmentIds,
    anchorRect
  }: {
    entryType: PrecisionOverlayState['entryType'];
    mode: 'same-source' | 'cross-source';
    fragmentIds: string[];
    anchorRect: DOMRect;
  }) {
    const overlayState = buildOverlayState(entryType, mode, fragmentIds, editFragments, anchorRect);
    if (overlayState.chainRealIndices.length !== fragmentIds.length) {
      pushToast('error', 'Precision entry could not be opened from the current structure.');
      return;
    }

    setPrecisionOverlay(overlayState);
    setInteractionMode('PRECISION_OVERLAY');
    recallSource(fragmentIds);
    announcePolite(`Precision overlay opened for ${fragmentIds.length} related fragments.`);
  }

  function attemptPrecisionEntryOpen(
    handle: PrecisionEntryHandle,
    anchorRect: DOMRect,
    entryType: PrecisionOverlayState['entryType']
  ) {
    const scopeResult = resolvePrecisionScope(handle, editFragments);

    if (!scopeResult.ok && 'reason' in scopeResult) {
      const { reason } = scopeResult;

      if (reason === 'too-many-fragments') {
        pushToast(
          'info',
          'Precision Boundary Editor supports up to 4 related fragments. Use Original Panorama or Hold Area to restructure first.'
        );
        announcePolite('Precision entry rejected. Use Original Panorama or Hold Area to restructure first.');
        return false;
      }

      pushToast(
        'error',
        reason === 'not-local-refinement'
          ? 'Precision entry supports only local correction on the active edit chain.'
          : 'Precision entry could not be opened from the current structure.'
      );
      return false;
    }

    openPrecisionEditor({
      entryType,
      mode: scopeResult.mode,
      fragmentIds: scopeResult.fragmentIds,
      anchorRect
    });
    return true;
  }

  function handlePrecisionEntryOpen(handle: PrecisionEntryHandle, anchorRect: DOMRect) {
    attemptPrecisionEntryOpen(
      handle,
      anchorRect,
      handle.type === 'synthetic-seam' ? 'seam-click' : 'boundary-click'
    );
    return;
    /*

    const scopeResult = resolvePrecisionScope(handle, editFragments);

    if (!scopeResult.ok && 'reason' in scopeResult) {
      const { reason } = scopeResult;

      if (reason === 'too-many-fragments') {
        pushToast('info', 'Precision Boundary Editor 범위를 넘습니다. Original Panorama / Hold Area 기반 재구성으로 조정하세요.');
        announcePolite('Precision entry rejected. Use Original Panorama or Hold Area to restructure first.');
        return;
      }

      pushToast('error', 'Precision entry could not be opened from the current structure.');
      return;
    }

    openPrecisionEditor({
      entryType: handle.type === 'synthetic-seam' ? 'seam-click' : 'boundary-click',
      mode: scopeResult.mode,
      fragmentIds: scopeResult.fragmentIds,
      anchorRect
    });
    */
  }

  function handlePrecisionChatSubmit(text: string, anchorRect: DOMRect) {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    const request = resolvePrecisionChatRequest(
      trimmed,
      precisionPairSelectionIds,
      sourceFragments.map((fragment) => fragment.fragment_id),
      editFragments
    );

    if (!request.ok && 'reason' in request) {
      if (request.reason === 'unsupported-intent') {
        pushToast('info', 'Chat entry currently supports Precision Boundary Editor open requests only.');
      } else if (request.reason === 'needs-exactly-two-fragments') {
        pushToast(
          'info',
          'Mention exactly two fragment ids, or select exactly two edit fragments with Ctrl/Cmd+click before asking.'
        );
      } else if (request.reason === 'not-local-refinement') {
        pushToast(
          'info',
          'That request exceeds local precision refinement. Use Original Panorama or Hold Area to restructure first.'
        );
      } else {
        pushToast('error', 'Precision chat request could not resolve a valid fragment pair.');
      }
      return;
    }

    const opened = attemptPrecisionEntryOpen(request.handle, anchorRect, request.entryType);
    if (opened) {
      setChatInput('');
      announcePolite(
        request.entryType === 'pair-chat'
          ? 'Precision editor opened from the selected fragment pair.'
          : 'Precision editor opened from chat instruction.'
      );
    }
  }

  function handlePrecisionCommit(nextChain: Fragment[]) {
    if (!precisionOverlay) {
      return;
    }

    commitMutation(
      'precision-boundary',
      'Committed precision boundary adjustment',
      () => {
        const nextEditFragments = cloneFragments(editFragments);
        nextChain.forEach((fragment, index) => {
          const realIndex = precisionOverlay.chainRealIndices[index];
          if (typeof realIndex === 'number') {
            nextEditFragments[realIndex] = fragment;
          }
        });
        return { editFragments: nextEditFragments };
      },
      (previousState, nextState) =>
        deriveBoundaryUndoOperation(
          'precision-boundary',
          previousState.editFragments,
          nextState.editFragments
        ),
      () => {
        dismissOverlayPreview();
        syncInteractionMode(focusExpandedId, timeLensId);
      }
    );
  }

  const handlePreviewChange = useCallback((fragments: Fragment[]) => {
    setPrecisionPreviewHighlightIds(fragments.map((fragment) => fragment.fragment_id));
  }, []);

  const handlePreviewClear = useCallback(() => {
    clearPrecisionPreview();
  }, []);

  function closePrecisionOverlay() {
    dismissOverlayPreview();
    syncInteractionMode(focusExpandedId, timeLensId);
    announcePolite('Precision overlay closed.');
  }

  function handleHoldRepositionStart(fragment: Fragment, event: React.MouseEvent<HTMLDivElement>) {
    holdDragCleanupRef.current?.();
    holdDragCleanupRef.current = null;
    holdDragAbortRef.current = null;
    const target = event.target as HTMLElement;
    if (target.closest('[data-action-button="true"]')) {
      return;
    }

    event.preventDefault();

    const origin = holdAreaPositions[fragment.fragment_id] || { x: 18, y: 18 };
    const initialPositions = cloneHoldPositions(holdAreaPositions);
    const startX = event.clientX;
    const startY = event.clientY;
    let moved = false;

    setInteractionMode('HOLD_DRAGGING');

    const cleanup = () => {
      holdDragCleanupRef.current?.();
      holdDragCleanupRef.current = null;
      holdDragAbortRef.current = null;
      syncInteractionMode(focusExpandedId, timeLensId);
    };

    const onMouseMove = (moveEvent: MouseEvent) => {
      const dx = moveEvent.clientX - startX;
      const dy = moveEvent.clientY - startY;
      if (Math.abs(dx) >= 4 || Math.abs(dy) >= 4) {
        moved = true;
      }

      setHoldAreaPositions((current) => ({
        ...current,
        [fragment.fragment_id]: {
          x: Math.max(0, origin.x + dx),
          y: Math.max(0, origin.y + dy)
        }
      }));
    };

    const revert = (restoreSelection: boolean) => {
      setHoldAreaPositions(initialPositions);
      cleanup();
      if (restoreSelection) {
        handleReservedSelect(fragment);
      }
      announcePolite(`${fragment.fragment_id} hold drag cancelled.`);
    };

    const onMouseUp = () => {
      cleanup();

      if (!moved) {
        setHoldAreaPositions(initialPositions);
        handleReservedSelect(fragment);
        return;
      }

      const snapshot = createUndoEntry('hold-area-reposition', `Repositioned ${fragment.fragment_id} in Hold Area`, {
        editFragments,
        reservedFragments,
        holdAreaPositions: initialPositions
      });
      setUndoStack((current) => [...current.slice(-(MAX_UNDO_DEPTH - 1)), snapshot]);
      setRedoStack([]);
      announcePolite(`${fragment.fragment_id} repositioned in Hold Area.`);
    };

    const onWindowBlur = () => {
      revert(false);
    };

    holdDragAbortRef.current = () => {
      revert(false);
    };

    holdDragCleanupRef.current = beginGlobalDragLifecycle({
      cursor: 'grabbing',
      listeners: [
        { target: 'document', type: 'mousemove', listener: onMouseMove as EventListener },
        { target: 'document', type: 'mouseup', listener: onMouseUp as EventListener },
        { target: 'window', type: 'blur', listener: onWindowBlur as EventListener }
      ]
    });
  }

  function handleUndo() {
    const entry = undoStack[undoStack.length - 1];
    if (!entry) {
      return;
    }

    try {
      const currentState = buildStableBoardState(editFragments, reservedFragments, holdAreaPositions);
      const currentSnapshot = createUndoEntry(entry.type, entry.label, currentState, entry.op);
      const restored = restoreFromUndo(entry, currentState, 'undo');
      setUndoStack((current) => current.slice(0, -1));
      setRedoStack((current) => [...current.slice(-(MAX_UNDO_DEPTH - 1)), currentSnapshot]);
      setEditFragments(restored.editFragments);
      setReservedFragments(restored.reservedFragments);
      setHoldAreaPositions(restored.holdAreaPositions);
      setLastRestoreMode(restored.restoreMode);
      setLastRestoreDirection('undo');
      resetEphemeralState(true);
      announcePolite(`Undid ${entry.label}.`);
    } catch (error) {
      restoreStableState('Undo restore error. Last stable structure restored.');
    }
  }

  function handleRedo() {
    const entry = redoStack[redoStack.length - 1];
    if (!entry) {
      return;
    }

    try {
      const currentState = buildStableBoardState(editFragments, reservedFragments, holdAreaPositions);
      const currentSnapshot = createUndoEntry(entry.type, entry.label, currentState, entry.op);
      const restored = restoreFromUndo(entry, currentState, 'redo');
      setRedoStack((current) => current.slice(0, -1));
      setUndoStack((current) => [...current.slice(-(MAX_UNDO_DEPTH - 1)), currentSnapshot]);
      setEditFragments(restored.editFragments);
      setReservedFragments(restored.reservedFragments);
      setHoldAreaPositions(restored.holdAreaPositions);
      setLastRestoreMode(restored.restoreMode);
      setLastRestoreDirection('redo');
      resetEphemeralState(true);
      announcePolite(`Redid ${entry.label}.`);
    } catch (error) {
      restoreStableState('Undo restore error. Last stable structure restored.');
    }
  }

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target) {
        return;
      }

      if (target.closest('.fragment-tile') || target.closest('.boundary-handle') || target.closest('.synthetic-seam')) {
        return;
      }

      if (target.closest('.precision-overlay')) {
        return;
      }

      resetEphemeralState(true);
      announcePolite('Selection cleared.');
    };

    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [focusExpandedId, timeLensId]);

  useEffect(() => {
    return () => {
      boundaryDragCleanupRef.current?.();
      boundaryDragCleanupRef.current = null;
      boundaryDragAbortRef.current = null;
      holdDragCleanupRef.current?.();
      holdDragCleanupRef.current = null;
      holdDragAbortRef.current = null;
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault();
        if (event.shiftKey) {
          handleRedo();
        } else {
          handleUndo();
        }
        return;
      }

      if (event.key === 'Escape') {
        if (boundaryDragAbortRef.current) {
          event.preventDefault();
          boundaryDragAbortRef.current();
          return;
        }

        if (holdDragAbortRef.current) {
          event.preventDefault();
          holdDragAbortRef.current();
          return;
        }

        if (dragOrigin) {
          return;
        }

        event.preventDefault();
        resetEphemeralState(true);
        announcePolite('Selection cleared.');
        return;
      }

      if ((event.key === 'Backspace' || event.key === 'Delete') && selectedFragmentId) {
        const editFragment = editFragments.find((fragment) => fragment.fragment_id === selectedFragmentId);
        if (editFragment) {
          event.preventDefault();
          handleExcludeToggle(editFragment);
        }
        return;
      }

      if ((event.key === 'ArrowLeft' || event.key === 'ArrowRight') && selectedFragmentId) {
        const index = visibleFragments.findIndex((fragment) => fragment.fragment_id === selectedFragmentId);
        if (index === -1) {
          return;
        }

        const offset = event.key === 'ArrowLeft' ? -1 : 1;
        const nextFragment = visibleFragments[index + offset];
        if (!nextFragment) {
          return;
        }

        event.preventDefault();
        handleEditFragmentClick(nextFragment);
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [selectedFragmentId, editFragments, visibleFragments, undoStack, redoStack, dragOrigin]);

  function handleSplitterMouseDown(event: React.MouseEvent<HTMLButtonElement>) {
    event.preventDefault();

    const onMouseMove = (moveEvent: MouseEvent) => {
      const totalWidth = appRef.current?.clientWidth || window.innerWidth;
      setCenterWidth(clampCenterWidth(totalWidth, moveEvent.clientX));
    };

    let cleanup: (() => void) | null = null;

    const finish = () => {
      cleanup?.();
      cleanup = null;
    };

    const onMouseUp = () => {
      finish();
    };

    const onWindowBlur = () => {
      finish();
    };

    cleanup = beginGlobalDragLifecycle({
      cursor: 'col-resize',
      listeners: [
        { target: 'document', type: 'mousemove', listener: onMouseMove as EventListener },
        { target: 'document', type: 'mouseup', listener: onMouseUp as EventListener },
        { target: 'window', type: 'blur', listener: onWindowBlur as EventListener }
      ]
    });
  }

  return (
    <div
      className="ccut-shell"
      ref={appRef}
      data-last-restore-mode={lastRestoreMode}
      data-last-restore-direction={lastRestoreDirection}
    >
      <LeftNav activeNavItem={activeNavItem} onChange={setActiveNavItem} />

      <div className="center-column" style={{ width: centerWidth, minWidth: 260 }}>
        <CenterPanel
          sources={sourceVideos}
          selectedFragment={selectedFragment}
          activeSource={activeSource}
          focusExpandedId={focusExpandedId}
          timeLensId={timeLensId}
          intelligenceOn={intelligenceOn}
          visibleCount={visibleFragments.length}
          precisionPairSelectionIds={precisionPairSelectionIds}
          chatInput={chatInput}
          onChatInputChange={setChatInput}
          onChatSubmit={handlePrecisionChatSubmit}
        />
      </div>

      <button
        type="button"
        className="vertical-splitter"
        onMouseDown={handleSplitterMouseDown}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize center panel"
      >
        <span className="vertical-splitter__pill" />
      </button>

      <main className="right-workspace">
        <OriginalPanorama
          sources={sourceVideos}
          fragments={sourceFragments}
          activeSource={activeSource}
          selectedFragmentId={selectedFragmentId}
          highlightedFragmentId={highlightedPanoramaFrag}
          focusExpandedId={focusExpandedId || timeLensId}
          intelligenceOn={intelligenceOn}
          fragmentOverrides={boundaryPreviewOverrides}
          onSourceChange={setActiveSource}
          onFragmentSelect={handlePanoramaSelect}
          onToggleIntelligence={() => setIntelligenceOn((current) => !current)}
          onThumbnailError={(fragmentId) => pushToast('error', `Thumbnail load error on ${fragmentId}. Fallback thumbnail applied.`)}
        />

        <FragmentMap
          editFragments={editFragments}
          selectedFragmentId={selectedFragmentId}
          pairSelectedFragmentIds={precisionPairSelectionIds}
          focusExpandedId={focusExpandedId}
          timeLensId={timeLensId}
          playingFragmentId={playingFragmentId}
          playProgress={playProgress}
          boundaryHighlightIds={previewHighlightIds}
          isBoundaryDragging={interactionMode === 'BOUNDARY_DRAGGING'}
          fragmentOverrides={boundaryPreviewOverrides}
          dragOrigin={dragOrigin}
          dragTargetVisibleIndex={dragTargetVisibleIndex}
          replaceTargetId={replaceTargetId}
          onFragmentSingleClick={handleEditFragmentClick}
          onFragmentDoubleClick={handleEditFragmentDoubleClick}
          onPairSelectionToggle={handlePrecisionPairSelectionToggle}
          onPlayToggle={handlePlayToggle}
          onExcludeToggle={handleExcludeToggle}
          onMoveToHold={handleMoveToHold}
          onPrecisionEntryOpen={handlePrecisionEntryOpen}
          onThumbnailError={(fragmentId) => pushToast('error', `Thumbnail load error on ${fragmentId}. Fallback thumbnail applied.`)}
          onDragStart={handleDragStart}
          onDragTargetIndexChange={handleDragTargetIndexChange}
          onReplaceTargetChange={handleReplaceTargetChange}
          onReplaceDrop={handleReplaceDrop}
          onDragDrop={handleDragDrop}
          onDragEnd={clearDragState}
        />

        <ReservedFragments
          fragments={reservedFragments}
          positions={holdAreaPositions}
          selectedFragmentId={selectedFragmentId}
          focusExpandedId={focusExpandedId}
          timeLensId={timeLensId}
          playingFragmentId={playingFragmentId}
          playProgress={playProgress}
          onPlayToggle={handlePlayToggle}
          onRestore={handleRestoreFromHold}
          onSelect={handleReservedSelect}
          onRepositionStart={handleHoldRepositionStart}
          onReplaceDragStart={(fragmentId) => handleDragStart(fragmentId, 'reserved')}
          onReplaceDragEnd={clearDragState}
          onThumbnailError={(fragmentId) => pushToast('error', `Thumbnail load error on ${fragmentId}. Fallback thumbnail applied.`)}
        />
      </main>

      {precisionOverlay ? (
        <BoundaryPrecisionOverlay
          overlay={precisionOverlay}
          editFragments={editFragments}
          playingFragmentId={playingFragmentId}
          playProgress={playProgress}
          onClose={closePrecisionOverlay}
          onCommit={handlePrecisionCommit}
          onPreviewChange={handlePreviewChange}
          onPreviewClear={handlePreviewClear}
          onSourceRecall={recallSource}
          onPlayToggle={handlePlayToggle}
        />
      ) : null}

      <div className="sr-only" aria-live="polite">
        {announcement}
      </div>

      <div className="toast-stack" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast--${toast.kind}`}>
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  );
}
