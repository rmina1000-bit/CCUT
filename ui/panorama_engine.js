/**
 * panorama_engine.js
 * ------------------
 * Manages states for CCUT Right Panel 3-layer architecture:
 * 1. original_fragments (read-only panorama)
 * 2. edit_structure (active editing structures)
 * 3. board_fragments (ideas / discarded fragments)
 * 4. selected_fragments (multi-select)
 */
import { useState, useCallback, useMemo, useEffect, useRef } from 'react';

const MIN_FRAGMENT_DURATION = 0.8;

function clamp(lo, hi, value) {
    return value < lo ? lo : value > hi ? hi : value;
}

function roundSeconds(value) {
    return Math.round(value * 1000) / 1000;
}

function normalizeFragments(fragments) {
    return Array.isArray(fragments) ? fragments.filter(Boolean) : [];
}

function getFragmentsSignature(fragments) {
    return normalizeFragments(fragments)
        .map((fragment) => `${fragment.id}:${fragment.start}:${fragment.end}:${fragment.originalId || ''}:${fragment.fx || ''}`)
        .join('|');
}

function adjustAdjacentFragments(prev, leftIndex, deltaSeconds) {
    if (leftIndex < 0 || leftIndex >= prev.length - 1) return prev;

    const updated = [...prev];
    const leftFragment = { ...updated[leftIndex] };
    const rightFragment = { ...updated[leftIndex + 1] };

    // Calculate possible movement range for left fragment's end
    // leftFragment.start + MIN_DURATION <= leftFragment.end + delta <= source_end (not known here, but we can clamp by duration)
    // rightFragment.start + delta >= source_start (not known) and rightFragment.end - rightFragment.start - delta >= MIN_DURATION

    // For now, respect the internal durations of both
    const leftMinEnd = (parseFloat(leftFragment.start) || 0) + MIN_FRAGMENT_DURATION;
    const rightMaxStart = (parseFloat(rightFragment.end) || 0) - MIN_FRAGMENT_DURATION;

    // deltaSeconds is positive -> drag right (left grows, right shrinks)
    // We must ensure:
    // 1. leftFragment.end + delta >= leftMinEnd
    // 2. rightFragment.start + delta <= rightMaxStart

    let actualDelta = deltaSeconds;

    if (actualDelta > 0) {
        // Dragging right: left grows, right shrinks
        const capacityRight = rightMaxStart - (parseFloat(rightFragment.start) || 0);
        actualDelta = Math.min(actualDelta, capacityRight);
    } else {
        // Dragging left: left shrinks, right grows
        const capacityLeft = (parseFloat(leftFragment.end) || 0) - leftMinEnd;
        actualDelta = Math.max(actualDelta, -capacityLeft);
    }

    if (Math.abs(actualDelta) < 0.001) return prev;

    leftFragment.end = roundSeconds((parseFloat(leftFragment.end) || 0) + actualDelta);
    leftFragment.duration = roundSeconds(leftFragment.end - (parseFloat(leftFragment.start) || 0));

    rightFragment.start = roundSeconds((parseFloat(rightFragment.start) || 0) + actualDelta);
    rightFragment.duration = roundSeconds((parseFloat(rightFragment.end) || 0) - rightFragment.start);

    updated[leftIndex] = leftFragment;
    updated[leftIndex + 1] = rightFragment;

    return updated;
}

export function usePanoramaEngine(sourceFragments = [], selectedFragments = []) {
    const normalizedSourceFragments = useMemo(() => normalizeFragments(sourceFragments), [sourceFragments]);
    const normalizedSelectedFragments = useMemo(() => normalizeFragments(selectedFragments), [selectedFragments]);
    const [originalFragments, setOriginalFragments] = useState(normalizedSourceFragments);
    const [editStructure, setEditStructure] = useState(normalizedSelectedFragments);
    const [boardFragments, setBoardFragments] = useState([]);
    const [trashFragments, setTrashFragments] = useState([]);
    const [selectedIds, setSelectedIds] = useState([]);
    const sourceSignature = useMemo(() => getFragmentsSignature(normalizedSourceFragments), [normalizedSourceFragments]);
    const selectedSignature = useMemo(() => getFragmentsSignature(normalizedSelectedFragments), [normalizedSelectedFragments]);
    const editSignature = useMemo(() => getFragmentsSignature(editStructure), [editStructure]);
    const lastSourceSignatureRef = useRef(sourceSignature);
    const lastSelectedSignatureRef = useRef(selectedSignature);

    // Replace all fragments (e.g., loaded from API)
    const initialize = useCallback((sourceFrags, editFrags = sourceFrags) => {
        const nextSourceFragments = normalizeFragments(sourceFrags);
        const nextEditFragments = normalizeFragments(editFrags);

        setOriginalFragments(nextSourceFragments);
        setEditStructure(nextEditFragments);
        setBoardFragments([]);
        setTrashFragments([]);
        setSelectedIds([]);
    }, []);

    // Sync source fragments only when a new upload arrives from the parent.
    useEffect(() => {
        if (lastSourceSignatureRef.current !== sourceSignature) {
            lastSourceSignatureRef.current = sourceSignature;
            setOriginalFragments(normalizedSourceFragments);
            setBoardFragments([]);
            setTrashFragments([]);
            setSelectedIds([]);
        }
    }, [normalizedSourceFragments, sourceSignature]);

    // Sync selected/edit fragments only when MainLayout sends a genuinely new edit rail.
    useEffect(() => {
        if (lastSelectedSignatureRef.current !== selectedSignature) {
            lastSelectedSignatureRef.current = selectedSignature;
            if (editSignature === selectedSignature) {
                return;
            }
            setEditStructure(normalizedSelectedFragments);
            setBoardFragments([]);
            setSelectedIds([]);
        }
    }, [editSignature, normalizedSelectedFragments, selectedSignature]);

    // Move multiple fragments from edit_structure to board
    const moveToBoard = useCallback((ids) => {
        const moved = editStructure.filter((fragment) => ids.includes(fragment.id));
        setEditStructure((prev) => prev.filter((fragment) => !ids.includes(fragment.id)));
        setBoardFragments((prev) => [...prev, ...moved]);
        setSelectedIds([]);
    }, [editStructure]);

    // Restore fragment from board to edit_structure
    const restoreFromBoard = useCallback((id) => {
        const fragment = boardFragments.find((item) => item.id === id);
        if (!fragment) return;
        setBoardFragments((prev) => prev.filter((item) => item.id !== id));
        setEditStructure((prev) => [...prev, fragment].sort((a, b) => a.start - b.start));
    }, [boardFragments]);

    // Apply edit proposal by keeping the selected original fragment ids.
    const applyProposal = useCallback((proposalIds) => {
        const keep = originalFragments.filter((fragment) => proposalIds.includes(fragment.id));

        setEditStructure(keep);
        setBoardFragments([]);
        setSelectedIds([]);
    }, [originalFragments]);

    // Handle Multi-Select Shift-Click
    const toggleSelect = useCallback((id, isShiftCmd) => {
        if (isShiftCmd) {
            setSelectedIds((prev) => prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]);
        } else {
            setSelectedIds([id]);
        }
    }, []);

    // Update a fragment's duration (Resize from edge)
    const resizeFragment = useCallback((id, newStart, newEnd) => {
        setEditStructure((prev) => prev.map((fragment) => (
            fragment.id === id ? { ...fragment, start: newStart, end: newEnd } : fragment
        )));
    }, []);

    // Move fragment within edit_structure
    const moveFragment = useCallback((dragIndex, hoverIndex) => {
        setEditStructure((prev) => {
            const updated = [...prev];
            const [draggedItem] = updated.splice(dragIndex, 1);
            updated.splice(hoverIndex, 0, draggedItem);
            return updated;
        });
    }, []);

    // Insert fragment from original panorama to specific index in edit_structure
    const insertFromOriginal = useCallback((id, toIndex) => {
        const fragment = originalFragments.find((item) => item.id === id);
        if (!fragment) return;

        const newFragment = { ...fragment, id: `${fragment.id}_${Date.now()}`, originalId: fragment.id };

        setEditStructure((prev) => {
            const updated = [...prev];
            updated.splice(toIndex, 0, newFragment);
            return updated;
        });
    }, [originalFragments]);

    // Insert fragment from board to specific index in edit_structure
    const insertFromBoard = useCallback((id, toIndex) => {
        const fragment = boardFragments.find((item) => item.id === id);
        if (!fragment) return;

        setBoardFragments((prev) => prev.filter((item) => item.id !== id));
        setEditStructure((prev) => {
            const updated = [...prev];
            updated.splice(toIndex, 0, fragment);
            return updated;
        });
    }, [boardFragments]);

    const insertFromOriginalToBoard = useCallback((id, nextId) => {
        const fragment = originalFragments.find((item) => item.id === id);
        if (!fragment) return;

        const boardFragment = {
            ...fragment,
            id: nextId || `${fragment.id}_board_${Date.now()}`,
            originalId: fragment.originalId || fragment.id
        };

        setBoardFragments((prev) => [...prev, boardFragment]);
    }, [originalFragments]);

    // Adjust the ratio (start/end times) between two adjacent fragments in edit_structure
    const adjustDividerRatio = useCallback((leftIndex, deltaSeconds) => {
        setEditStructure((prev) => {
            const updated = adjustAdjacentFragments(prev, leftIndex, deltaSeconds);
            if (updated === prev) return prev;

            // Calculate actual applied delta (clamped by MIN_DURATION)
            const actualDeltaApplied = roundSeconds((parseFloat(updated[leftIndex].end) || 0) - (parseFloat(prev[leftIndex].end) || 0));
            if (Math.abs(actualDeltaApplied) < 0.001) return updated;

            const leftFrag = updated[leftIndex];
            const rightFrag = updated[leftIndex + 1];

            if (leftFrag && rightFrag) {
                const leftOrigId = leftFrag.originalId || leftFrag.id;
                const rightOrigId = rightFrag.originalId || rightFrag.id;

                setOriginalFragments(origPrev => {
                    const lIdx = origPrev.findIndex(f => f.id === leftOrigId);
                    const rIdx = origPrev.findIndex(f => f.id === rightOrigId);

                    if (lIdx !== -1 && rIdx !== -1) {
                        const startIdx = Math.min(lIdx, rIdx);
                        const endIdx = Math.max(lIdx, rIdx);
                        const direction = (lIdx < rIdx) ? 1 : -1;
                        const syncDelta = actualDeltaApplied * direction;

                        const newOrig = [...origPrev];
                        // Master Divider Shift: Adjust all boundaries between lIdx and rIdx
                        for (let i = startIdx; i < endIdx; i++) {
                            const left = { ...newOrig[i] };
                            const right = { ...newOrig[i + 1] };

                            left.end = roundSeconds(parseFloat(left.end) + syncDelta);
                            left.duration = roundSeconds(left.end - (parseFloat(left.start) || 0));
                            right.start = roundSeconds(parseFloat(right.start) + syncDelta);
                            right.duration = roundSeconds((parseFloat(right.end) || 0) - right.start);

                            newOrig[i] = left;
                            newOrig[i + 1] = right;
                        }
                        return newOrig;
                    }
                    return origPrev;
                });
            }
            return updated;
        });
    }, [originalFragments]);

    const adjustOriginalDividerRatio = useCallback((leftIndex, deltaSeconds) => {
        setOriginalFragments((prev) => adjustAdjacentFragments(prev, leftIndex, deltaSeconds));
    }, []);

    const removeFragment = useCallback((id) => {
        let fragmentToTrash = null;
        setEditStructure((prev) => {
            const found = prev.find((fragment) => fragment.id === id);
            if (found) fragmentToTrash = found;
            return prev.filter((fragment) => fragment.id !== id);
        });
        setBoardFragments((prev) => {
            const found = prev.find((fragment) => fragment.id === id);
            if (found) fragmentToTrash = found;
            return prev.filter((fragment) => fragment.id !== id);
        });

        setTimeout(() => {
            if (fragmentToTrash) {
                setTrashFragments((prev) => [...prev, fragmentToTrash]);
            }
        }, 0);
    }, []);

    const insertFromTrashToEdit = useCallback((id, toIndex) => {
        setTrashFragments((prev) => {
            const fragment = prev.find((item) => item.id === id);
            if (fragment) {
                setEditStructure((editPrev) => {
                    const updated = [...editPrev];
                    updated.splice(toIndex, 0, fragment);
                    return updated;
                });
            }
            return prev.filter((item) => item.id !== id);
        });
    }, []);

    const insertFromTrashToBoard = useCallback((id) => {
        setTrashFragments((prev) => {
            const fragment = prev.find((item) => item.id === id);
            if (fragment) {
                setBoardFragments((boardPrev) => [...boardPrev, fragment]);
            }
            return prev.filter((item) => item.id !== id);
        });
    }, []);

    const updateFragmentStatus = useCallback((id, status) => {
        setOriginalFragments((prev) => prev.map((f) => (f.id === id ? { ...f, status } : f)));
        setBoardFragments((prev) => prev.map((f) => (f.id === id ? { ...f, status } : f)));
        setEditStructure((prev) => prev.map((f) => (f.id === id ? { ...f, status } : f)));
    }, []);

    return {
        originalFragments,
        editStructure,
        boardFragments,
        trashFragments,
        selectedIds,
        initialize,
        moveToBoard,
        restoreFromBoard,
        applyProposal,
        toggleSelect,
        resizeFragment,
        moveFragment,
        insertFromBoard,
        insertFromOriginal,
        insertFromOriginalToBoard,
        adjustOriginalDividerRatio,
        adjustDividerRatio,
        removeFragment,
        insertFromTrashToEdit,
        insertFromTrashToBoard,
        updateFragmentStatus
    };
}