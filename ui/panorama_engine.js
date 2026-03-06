/**
 * panorama_engine.js
 * ------------------
 * Manages states for CCUT Right Panel 3-layer architecture:
 * 1. original_fragments (read-only panorama)
 * 2. edit_structure (active editing structures)
 * 3. board_fragments (ideas / discarded fragments)
 * 4. selected_fragments (multi-select)
 */
import { useState, useCallback, useMemo, useEffect } from 'react';

export function usePanoramaEngine(initialFragments = []) {
    const [originalFragments, setOriginalFragments] = useState(initialFragments);
    const [editStructure, setEditStructure] = useState(initialFragments);
    const [boardFragments, setBoardFragments] = useState([]);
    const [selectedIds, setSelectedIds] = useState([]);

    // Replace all fragments (e.g., loaded from API)
    const initialize = useCallback((frags) => {
        setOriginalFragments(frags);
        setEditStructure(frags);
        setBoardFragments([]);
        setSelectedIds([]);
    }, []);

    // Sync fragments if loaded asynchronously after mount
    useEffect(() => {
        if (originalFragments.length === 0 && initialFragments.length > 0) {
            initialize(initialFragments);
        }
    }, [initialFragments, originalFragments.length, initialize]);

    // Move multiple fragments from edit_structure to board
    const moveToBoard = useCallback((ids) => {
        setEditStructure(prev => prev.filter(f => !ids.includes(f.id)));
        setBoardFragments(prev => {
            const moved = originalFragments.filter(f => ids.includes(f.id) && !prev.some(bf => bf.id === f.id));
            return [...prev, ...moved];
        });
        setSelectedIds([]);
    }, [originalFragments]);

    // Restore fragment from board to edit_structure
    const restoreFromBoard = useCallback((id) => {
        const frag = boardFragments.find(f => f.id === id);
        if (!frag) return;
        setBoardFragments(prev => prev.filter(f => f.id !== id));
        setEditStructure(prev => {
            // Re-insert based on original chronological order assuming IDs or start times are sequential
            const updated = [...prev, frag].sort((a, b) => a.start - b.start);
            return updated;
        });
    }, [boardFragments]);

    // Apply edit proposal (e.g. AI suggests A or B)
    const applyProposal = useCallback((proposalIds) => {
        // proposalIds are the ones to KEEP in edit_structure. Everything else goes to board.
        const keep = originalFragments.filter(f => proposalIds.includes(f.id));
        const discard = originalFragments.filter(f => !proposalIds.includes(f.id));

        setEditStructure(keep);
        setBoardFragments(discard);
        setSelectedIds([]);
    }, [originalFragments]);

    // Handle Multi-Select Shift-Click
    const toggleSelect = useCallback((id, isShiftCmd) => {
        if (isShiftCmd) {
            setSelectedIds(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
        } else {
            setSelectedIds([id]);
        }
    }, []);

    // Update a fragment's duration (Resize from edge)
    const resizeFragment = useCallback((id, newStart, newEnd) => {
        setEditStructure(prev => prev.map(f => f.id === id ? { ...f, start: newStart, end: newEnd } : f));
    }, []);

    // Move fragment within edit_structure
    const moveFragment = useCallback((dragIndex, hoverIndex) => {
        setEditStructure(prev => {
            const updated = [...prev];
            const [draggedItem] = updated.splice(dragIndex, 1);
            updated.splice(hoverIndex, 0, draggedItem);
            return updated;
        });
    }, []);

    // Insert fragment from board to specific index in edit_structure
    const insertFromBoard = useCallback((id, toIndex) => {
        const frag = boardFragments.find(f => f.id === id);
        if (!frag) return;

        setBoardFragments(prev => prev.filter(f => f.id !== id));
        setEditStructure(prev => {
            const updated = [...prev];
            updated.splice(toIndex, 0, frag);
            return updated;
        });
    }, [boardFragments]);

    return {
        originalFragments,
        editStructure,
        boardFragments,
        selectedIds,
        initialize,
        moveToBoard,
        restoreFromBoard,
        applyProposal,
        toggleSelect,
        resizeFragment,
        moveFragment,
        insertFromBoard
    };
}
