import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useLayout } from '../context/LayoutContext.jsx';
import { useVideo } from '../context/VideoContext.jsx';
import { useAppState } from '../context/AppStateContext.jsx';
import { useWorkspace } from '../context/WorkspaceContext.jsx';
import ResizablePanel from './ResizablePanel.jsx';
import ResizeHandle from './ResizeHandle.jsx';
import LeftPanel from '../left_panel.jsx';
import CenterPanel from '../center_panel.jsx';
import RightPanel from '../right_panel.jsx';

const API_BASE = 'http://localhost:8765';
const PROPOSAL_META = [
  { id: 'A', title: 'Proposal A', description: 'Stable hero cut' },
  { id: 'B', title: 'Proposal B', description: 'Fast contrast cut' },
  { id: 'C', title: 'Proposal C', description: 'Late-story hero cut' },
  { id: 'D', title: 'Proposal D', description: 'Distributed contrast cut' },
];

function getFragmentDuration(fragment) {
  return fragment.duration ?? Math.max(0, (fragment.end ?? 0) - (fragment.start ?? 0));
}

function uniqueFragmentIds(fragments) {
  return [...new Set((fragments || []).map((fragment) => fragment?.id).filter(Boolean))];
}

// getFragmentLabel is now a useCallback inside MainLayout to support global A1, A2 labeling across multiple sources

function resolveFragmentsByIds(source, ids) {
  console.log('[MainLayout] resolveFragmentsByIds - source count:', source?.length, 'ids to find:', ids);
  const fragmentsById = new Map((source || []).map((fragment) => [fragment.id, fragment]));
  const resolved = (ids || []).map((id) => fragmentsById.get(id)).filter(Boolean);
  console.log('[MainLayout] resolveFragmentsByIds - resolved count:', resolved.length);
  return resolved;
}

function getDurationStats(source) {
  const durations = source.map(getFragmentDuration).sort((a, b) => a - b);
  const total = durations.reduce((sum, duration) => sum + duration, 0);
  const average = total / (durations.length || 1);
  const middle = Math.floor(durations.length / 2);
  const median = durations.length % 2
    ? durations[middle]
    : ((durations[middle - 1] ?? average) + (durations[middle] ?? average)) / 2;

  return { average: average || 0, median: median || average || 0, total };
}

function getTotalDuration(source) {
  return source.reduce((max, fragment) => Math.max(max, fragment.end ?? 0), 0) || 1;
}

function getFragmentMidpoint(fragment) {
  const start = fragment.start ?? 0;
  const end = fragment.end ?? start;
  return (start + end) / 2;
}

function sortFragmentsByTime(source) {
  // Sort by source ID first to keep video groups together, then by start time.
  // This ensures 'Upload Order x Time' if sourceIds are sequential or we preserve original pooled order.
  return [...source].sort((a, b) => {
    if (a.sourceId !== b.sourceId) {
      // If we have an explicit source list to reference, we could use indexes.
      // For now, lexicographical sourceId sort provides a stable grouping.
      return (a.sourceId || '').localeCompare(b.sourceId || '');
    }
    return (a.start ?? 0) - (b.start ?? 0);
  });
}

function getStableLimit(count) {
  if (count <= 1) return count;
  if (count <= 3) return 1;
  if (count <= 6) return 2;
  return Math.min(3, Math.max(2, Math.round(count * 0.45)));
}

function getContrastLimit(count) {
  if (count <= 1) return count;
  if (count <= 3) return Math.min(2, count - 1);
  if (count <= 5) return 3;
  return Math.min(6, Math.max(4, Math.ceil(count * 0.8)));
}

function getSourceIndexMap(source) {
  return new Map(source.map((fragment, index) => [fragment.id, index]));
}

function buildTargetIndexes(count, limit, startRatio = 0.2, endRatio = 0.85) {
  if (!count || !limit) return [];

  const boundedStart = Math.max(0, Math.min(1, startRatio));
  const boundedEnd = Math.max(boundedStart, Math.min(1, endRatio));
  if (limit === 1) {
    return [Math.round((count - 1) * ((boundedStart + boundedEnd) / 2))];
  }

  return Array.from({ length: limit }, (_, index) => {
    const normalized = boundedStart + (((boundedEnd - boundedStart) * index) / Math.max(1, limit - 1));
    return normalized * (count - 1);
  });
}

function getWindowedFragments(source, totalDuration, startRatio = 0, endRatio = 1) {
  const startTime = totalDuration * Math.max(0, Math.min(1, startRatio));
  const endTime = totalDuration * Math.max(startRatio, Math.min(1, endRatio));
  const filtered = source.filter((fragment) => {
    const midpoint = getFragmentMidpoint(fragment);
    return midpoint >= startTime && midpoint <= endTime;
  });

  return filtered.length ? filtered : source;
}

function finalizeSelection(selection, limit, fallback) {
  const pickedIds = new Set(uniqueFragmentIds(selection));
  const ordered = sortFragmentsByTime(selection);

  for (const fragment of fallback) {
    if (ordered.length >= limit) break;
    if (!fragment?.id || pickedIds.has(fragment.id)) continue;
    ordered.push(fragment);
    pickedIds.add(fragment.id);
  }

  return sortFragmentsByTime(ordered).slice(0, limit);
}

function getIndexSpacingBonus(index, pickedIndexes, weight) {
  if (!pickedIndexes.length) return weight;
  return Math.min(...pickedIndexes.map((pickedIndex) => Math.abs(index - pickedIndex))) * weight;
}

function scoreStableOpening(fragment, index, stats, introTargetTime, windowStartTime, excludedIds) {
  const duration = getFragmentDuration(fragment);
  const midpoint = getFragmentMidpoint(fragment);
  const introDistancePenalty = Math.abs(midpoint - introTargetTime);
  const anchorBonus = (fragment.start ?? 0) <= (windowStartTime + Math.max(stats.average * 1.5, 0.8)) ? stats.average : 0;
  const firstFragmentBonus = index === 0 ? stats.average : 0;
  const exclusionPenalty = excludedIds.has(fragment.id) ? (stats.average || 1) * 8 : 0;

  return (duration * 3.5) + anchorBonus + firstFragmentBonus - introDistancePenalty - exclusionPenalty;
}

function scoreStableFragment(fragment, index, targetIndex, stats, excludedIds) {
  const duration = getFragmentDuration(fragment);
  const distancePenalty = Math.abs(index - targetIndex) * (stats.average || 1);
  const stabilityBonus = duration >= stats.median ? (stats.average || 1) * 1.5 : 0;
  const exclusionPenalty = excludedIds.has(fragment.id) ? (stats.average || 1) * 5 : 0;

  return (duration * 2.4) + stabilityBonus - distancePenalty - exclusionPenalty;
}

function pickStableFragments(source, limit, options = {}) {
  if (!source.length || limit <= 0) return [];

  const { excludedIds = new Set(), windowStartRatio = 0, windowEndRatio = 1 } = options;
  const ordered = sortFragmentsByTime(source);
  const stats = getDurationStats(ordered);
  const totalDuration = getTotalDuration(ordered);
  const windowed = getWindowedFragments(ordered, totalDuration, windowStartRatio, windowEndRatio);
  const windowStartTime = totalDuration * Math.max(0, Math.min(1, windowStartRatio));
  const windowEndTime = totalDuration * Math.max(windowStartRatio, Math.min(1, windowEndRatio));
  const windowSpan = Math.max(0.8, windowEndTime - windowStartTime || totalDuration);
  const stableThreshold = windowed.length > 2 ? Math.max(stats.median, stats.average * 0.95) : 0;
  const stablePool = windowed.filter((fragment) => getFragmentDuration(fragment) >= (stableThreshold * 0.95));
  const introCutoffTime = windowStartTime + (windowSpan * 0.45);
  const introPool = stablePool.filter((fragment) => getFragmentMidpoint(fragment) <= introCutoffTime);
  const introSource = introPool.length ? introPool : (stablePool.length ? stablePool : windowed);
  const introTargetTime = windowStartTime + (windowSpan * 0.18);
  const intro = [...introSource].sort((a, b) => {
    const aIndex = windowed.findIndex((fragment) => fragment.id === a.id);
    const bIndex = windowed.findIndex((fragment) => fragment.id === b.id);
    return scoreStableOpening(b, bIndex, stats, introTargetTime, windowStartTime, excludedIds)
      - scoreStableOpening(a, aIndex, stats, introTargetTime, windowStartTime, excludedIds)
      || (a.start ?? 0) - (b.start ?? 0);
  })[0];

  const picked = intro ? [intro] : [];
  const pickedIds = new Set(uniqueFragmentIds(picked));
  const remainingLimit = Math.max(0, limit - picked.length);
  const candidatePool = stablePool.length >= Math.max(1, remainingLimit) ? stablePool : windowed;
  const remainderPool = candidatePool.filter((fragment) => !pickedIds.has(fragment.id));
  const targetIndexes = buildTargetIndexes(remainderPool.length, remainingLimit, 0.35, 0.95);

  targetIndexes.forEach((targetIndex) => {
    let best = null;

    remainderPool.forEach((fragment, index) => {
      if (pickedIds.has(fragment.id)) return;
      const score = scoreStableFragment(fragment, index, targetIndex, stats, excludedIds);

      if (!best || score > best.score || (score === best.score && (fragment.start ?? 0) < (best.fragment.start ?? 0))) {
        best = { fragment, score };
      }
    });

    if (best) {
      picked.push(best.fragment);
      pickedIds.add(best.fragment.id);
    }
  });

  const fallback = [...candidatePool, ...windowed, ...ordered]
    .filter((fragment) => fragment?.id)
    .sort((a, b) => {
      const aExcluded = excludedIds.has(a.id) ? 1 : 0;
      const bExcluded = excludedIds.has(b.id) ? 1 : 0;
      return aExcluded - bExcluded
        || getFragmentDuration(b) - getFragmentDuration(a)
        || (a.start ?? 0) - (b.start ?? 0);
    });

  return finalizeSelection(picked, limit, fallback);
}

function getContrastBaseScore(source, fragment, index, stats, excludedIds, reservedStartIds, totalDuration, preferOpening = false) {
  const duration = getFragmentDuration(fragment);
  const midpoint = getFragmentMidpoint(fragment);
  const prev = source[index - 1];
  const next = source[index + 1];
  const prevDuration = prev ? getFragmentDuration(prev) : duration;
  const nextDuration = next ? getFragmentDuration(next) : duration;
  const neighborContrast = Math.abs(duration - prevDuration) + Math.abs(duration - nextDuration);
  const durationDeviation = Math.abs(duration - stats.average);
  const shortnessBonus = Math.max(0, (stats.average * 1.25) - duration) * 2.5;
  const noveltyBonus = excludedIds.has(fragment.id) ? -((stats.average || 1) * 4) : ((stats.average || 1) * 4);
  const reservedPenalty = reservedStartIds.has(fragment.id) ? (stats.average || 1) * 9 : 0;
  const earlyDifferenceBonus = preferOpening && midpoint <= totalDuration * 0.45 ? (stats.average || 1) * 2 : 0;
  const edgeBonus = (index === 0 || index === source.length - 1) ? (stats.average || 1) * 0.75 : 0;
  const longPenalty = Math.max(0, duration - stats.average) * 1.5;

  return shortnessBonus + (neighborContrast * 2.5) + durationDeviation + noveltyBonus + earlyDifferenceBonus + edgeBonus - reservedPenalty - longPenalty;
}

function scoreContrastFragment(source, fragment, index, targetIndex, pickedIndexes, stats, excludedIds, reservedStartIds, totalDuration, preferOpening = false) {
  const distancePenalty = Math.abs(index - targetIndex) * ((stats.average || 1) * 0.55);
  const spacingBonus = getIndexSpacingBonus(index, pickedIndexes, (stats.average || 1) * 0.45);

  return getContrastBaseScore(source, fragment, index, stats, excludedIds, reservedStartIds, totalDuration, preferOpening)
    + spacingBonus
    - distancePenalty;
}

function pickContrastFragments(source, limit, options = {}) {
  if (!source.length || limit <= 0) return [];

  const {
    excludedIds = new Set(),
    reservedStartIds = new Set(),
    windowStartRatio = 0,
    windowEndRatio = 1,
  } = options;
  const ordered = sortFragmentsByTime(source);
  const stats = getDurationStats(ordered);
  const totalDuration = getTotalDuration(ordered);
  const windowed = getWindowedFragments(ordered, totalDuration, windowStartRatio, windowEndRatio);
  const sourceIndexById = getSourceIndexMap(windowed);
  const nonOverlapPool = windowed.filter((fragment) => !excludedIds.has(fragment.id));
  const candidatePool = nonOverlapPool.length >= Math.max(2, Math.min(limit, windowed.length - 1))
    ? nonOverlapPool
    : windowed;
  const openingCutoff = totalDuration * (windowStartRatio + (Math.max(0.15, windowEndRatio - windowStartRatio) * 0.55));
  const openingPool = candidatePool.filter((fragment) => getFragmentMidpoint(fragment) <= openingCutoff && !reservedStartIds.has(fragment.id));
  const openingSource = openingPool.length ? openingPool : (candidatePool.filter((fragment) => !reservedStartIds.has(fragment.id)).length
    ? candidatePool.filter((fragment) => !reservedStartIds.has(fragment.id))
    : candidatePool);
  const opening = [...openingSource].sort((a, b) => {
    const aIndex = sourceIndexById.get(a.id) ?? 0;
    const bIndex = sourceIndexById.get(b.id) ?? 0;
    return scoreContrastFragment(windowed, b, bIndex, 0, [], stats, excludedIds, reservedStartIds, totalDuration, true)
      - scoreContrastFragment(windowed, a, aIndex, 0, [], stats, excludedIds, reservedStartIds, totalDuration, true)
      || (a.start ?? 0) - (b.start ?? 0);
  })[0];

  const picked = opening ? [opening] : [];
  const pickedIds = new Set(uniqueFragmentIds(picked));
  const pickedIndexes = opening ? [sourceIndexById.get(opening.id) ?? 0] : [];
  const remainingLimit = Math.max(0, limit - picked.length);
  const targetIndexes = buildTargetIndexes(windowed.length, remainingLimit, 0.18, 0.98);

  targetIndexes.forEach((targetIndex) => {
    let best = null;

    candidatePool.forEach((fragment) => {
      if (pickedIds.has(fragment.id)) return;
      const index = sourceIndexById.get(fragment.id) ?? 0;
      const score = scoreContrastFragment(
        windowed,
        fragment,
        index,
        targetIndex,
        pickedIndexes,
        stats,
        excludedIds,
        reservedStartIds,
        totalDuration,
        false,
      );

      if (!best || score > best.score || (score === best.score && (fragment.start ?? 0) < (best.fragment.start ?? 0))) {
        best = { fragment, score, index };
      }
    });

    if (best) {
      picked.push(best.fragment);
      pickedIds.add(best.fragment.id);
      pickedIndexes.push(best.index);
    }
  });

  const fallback = [...candidatePool, ...windowed, ...ordered]
    .filter((fragment) => fragment?.id)
    .sort((a, b) => {
      const aIndex = sourceIndexById.get(a.id) ?? 0;
      const bIndex = sourceIndexById.get(b.id) ?? 0;
      return getContrastBaseScore(windowed, b, bIndex, stats, excludedIds, reservedStartIds, totalDuration)
        - getContrastBaseScore(windowed, a, aIndex, stats, excludedIds, reservedStartIds, totalDuration)
        || getFragmentDuration(a) - getFragmentDuration(b)
        || (a.start ?? 0) - (b.start ?? 0);
    });

  return finalizeSelection(picked, limit, fallback);
}


// Updated buildProposalDescription to move it inside MainLayout or just pass a label-getter
function buildProposalDescription(proposalId, selection, labelGetter = (f) => f.id) {
  if (!selection.length) {
    return PROPOSAL_META.find((meta) => meta.id === proposalId)?.description || '';
  }

  const labels = selection.slice(0, 3).map(labelGetter).join(' -> ');
  const suffix = selection.length > 3 ? '...' : '';
  const countLabel = `${selection.length} cut${selection.length === 1 ? '' : 's'}`;

  switch (proposalId) {
    case 'A':
      return `${countLabel} | long anchors | ${labels}${suffix}`;
    case 'B':
      return `${countLabel} | contrast rhythm | ${labels}${suffix}`;
    case 'C':
      return `${countLabel} | late anchors | ${labels}${suffix}`;
    case 'D':
      return `${countLabel} | wide contrast | ${labels}${suffix}`;
    default:
      return `${countLabel} | ${labels}${suffix}`;
  }
}

function buildProposalsFromFragments(sourceFragments) {
  const fragments = Array.isArray(sourceFragments)
    ? sourceFragments.filter((fragment) => fragment && fragment.id != null)
    : [];

  if (!fragments.length) return [];

  const sorted = sortFragmentsByTime(fragments);
  const fallback = sorted.slice(0, Math.min(5, sorted.length));
  const selectionA = pickStableFragments(sorted, getStableLimit(sorted.length), {
    windowStartRatio: 0,
    windowEndRatio: 1,
  });
  const selectionAIds = new Set(uniqueFragmentIds(selectionA));
  const selectionAStartIds = new Set(uniqueFragmentIds(selectionA.slice(0, 2)));
  const selectionB = pickContrastFragments(sorted, getContrastLimit(sorted.length), {
    excludedIds: selectionAIds,
    reservedStartIds: selectionAStartIds,
    windowStartRatio: 0,
    windowEndRatio: 1,
  });
  const selectionC = pickStableFragments(sorted, getStableLimit(sorted.length), {
    excludedIds: selectionAIds,
    windowStartRatio: 0.35,
    windowEndRatio: 1,
  });
  const selectionD = pickContrastFragments(sorted, getContrastLimit(sorted.length), {
    excludedIds: new Set(uniqueFragmentIds(selectionB)),
    reservedStartIds: new Set(uniqueFragmentIds(selectionC.slice(0, 2))),
    windowStartRatio: 0.15,
    windowEndRatio: 1,
  });
  const selections = [selectionA, selectionB, selectionC, selectionD];

  return PROPOSAL_META.map((meta, index) => {
    const proposalFragments = uniqueFragmentIds(selections[index]).length
      ? uniqueFragmentIds(selections[index])
      : uniqueFragmentIds(fallback);

    const resolved = resolveFragmentsByIds(sorted, proposalFragments);
    // Note: buildProposalDescription still needs a global numbering context. 
    // We'll use a local fallback and then finalize it in the UI if needed.
    const tempLabeler = (f) => {
      const idx = sorted.findIndex(p => p.id === f.id);
      return idx !== -1 ? `A${idx + 1}` : f.id;
    };

    return {
      ...meta,
      description: buildProposalDescription(meta.id, resolved, tempLabeler),
      fragments: proposalFragments,
    };
  });
}

export default function MainLayout({ fragments = [], onFragments, onAction, onFragmentsLoad, workspaceData = {}, onWorkspaceDataChange }) {
  const { activeView, uploadDecisionFlow, setUploadDecisionFlow, isRightPanelOpen, setIsRightPanelOpen } = useAppState();
  const { addSourceToWorkspace, selectedWorkspaceId, workspaceList, createWorkspace, selectWorkspace } = useWorkspace();
  const { widths, collapsed, setRef, toggleCollapse } = useLayout();
  const { setVideoURL, videoURL } = useVideo();
  const containerRef = useRef(null);
  const sourceFragmentsRef = useRef([]);

  const [sourceFragments, setSourceFragments] = useState(() => {
    if (workspaceData.fragments?.length) return workspaceData.fragments;
    return Array.isArray(fragments) ? fragments.filter((f) => f && f.id != null) : [];
  });
  const [messages, setMessages] = useState(workspaceData.chatMessages?.length ? workspaceData.chatMessages : [
    { role: 'system', text: '영상을 드래그 앤 드롭으로 올리세요.' },
  ]);
  const [input, setInput] = useState('');
  const [proposals, setProposals] = useState(workspaceData.proposals || []);
  const [isEditing, setIsEditing] = useState(workspaceData.isEditing || false);
  const [selectedProposal, setSelectedProposal] = useState(workspaceData.selectedProposal || null);
  const [selectedFragments, setSelectedFragments] = useState(workspaceData.selectedFragments || []);
  const [editSessionId, setEditSessionId] = useState(Date.now());
  const [isDirty, setIsDirty] = useState(workspaceData.isDirty || false);
  const [pendingSwitchProposal, setPendingSwitchProposal] = useState(null);
  const [activeFX, setActiveFX] = useState(workspaceData.activeFX || null);

  useEffect(() => {
    setRef('container', containerRef.current);
  }, [setRef]);

  const getFragmentLabel = useCallback((fragOrId) => {
    const id = typeof fragOrId === 'string' ? fragOrId : fragOrId?.id;
    if (!id) return '??';
    const pool = sourceFragmentsRef.current.length ? sourceFragmentsRef.current : sourceFragments;
    const idx = pool.findIndex(f => f.id === id);
    return idx !== -1 ? `A${idx + 1}` : id;
  }, [sourceFragments]);

  const lastSyncedRef = useRef('');
  const hasMountedRef = useRef(false);

  // Sync Layout collapse state with isRightPanelOpen - One-way master control
  useEffect(() => {
    // Only toggle if necessary to avoid state loops
    const isCurrentlyCollapsed = !!collapsed.right;
    const shouldBeCollapsed = !isRightPanelOpen;

    if (isCurrentlyCollapsed !== shouldBeCollapsed) {
      console.log('[MainLayout] Syncing Right Panel Collapse:', shouldBeCollapsed);
      toggleCollapse('right');
    }
  }, [isRightPanelOpen, toggleCollapse, collapsed.right]);

  // Initial Layout: Set chat-centric proportions on first workspace load
  useEffect(() => {
    if (!hasMountedRef.current && activeView === 'workspace') {
      // Force Left to be thin (e.g., 14%) and Right to be collapsed
      if (!collapsed.right) toggleCollapse('right');
    }
  }, [activeView]);

  // Sync state upward when edited
  useEffect(() => {
    const currentData = {
      chatMessages: messages,
      proposals,
      isEditing,
      selectedProposal,
      fragments: sourceFragments,
      selectedFragments,
      isDirty,
      activeFX
    };

    const sig = JSON.stringify(currentData);
    if (sig === lastSyncedRef.current) return;

    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      lastSyncedRef.current = sig;
      return;
    }

    lastSyncedRef.current = sig;

    // Breaking synchronous recursion with a micro-task delay
    // This is a definitive way to stop "Maximum update depth exceeded" 
    // when multiple components fight over the same shared state.
    setTimeout(() => {
      onWorkspaceDataChange?.(currentData);
    }, 0);
  }, [
    messages, proposals, isEditing, selectedProposal,
    sourceFragments, selectedFragments, isDirty, activeFX,
    onWorkspaceDataChange
  ]);

  // Robust dirty state tracking using Refs to bypass React stale closures
  const cleanSignatureRef = useRef('');
  const currentSignatureRef = useRef('');

  const calculateSignature = (frags) => {
    return (frags || [])
      .map(f => `${f.id}-${Math.round((f.start || 0) * 10) / 10}-${Math.round((f.end || 0) * 10) / 10}-${f.fx || ''}`)
      .join('|');
  };

  // Redundant cyclical sync removed to break loop. 
  // State is now managed by initial useState and handled by key={selectedWorkspaceId} remount.

  const activateProposal = (proposal) => {
    if (!proposal) return false;

    const proposalSource = sourceFragmentsRef.current.length ? sourceFragmentsRef.current : sourceFragments;
    const nextSelectedFragments = resolveFragmentsByIds(proposalSource, proposal.fragments);

    if (!nextSelectedFragments.length) {
      console.warn('Failed to resolve proposal fragments:', proposal.id);
      return false;
    }

    console.log('[MainLayout] Activating proposal:', proposal.id, '| cuts:', nextSelectedFragments.length);
    setSelectedProposal(proposal);
    setSelectedFragments(nextSelectedFragments);
    const sig = calculateSignature(nextSelectedFragments);
    cleanSignatureRef.current = sig;
    currentSignatureRef.current = sig;
    setIsDirty(false);

    const newSessionId = Date.now();
    setEditSessionId(newSessionId);
    console.log('[MainLayout] Activated:', proposal.id, '| Sig:', sig);
    setIsEditing(true);
    return true;
  };

  const handleBatchUpload = useCallback(async (filesToProcess, mode, integration) => {
    setMessages((prev) => [...prev, { role: 'system', text: `[System] Processing batch of ${filesToProcess.length} file(s)...` }]);
    let newSources = [];

    for (let i = 0; i < filesToProcess.length; i++) {
      const file = filesToProcess[i];
      try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(`${API_BASE}/generate-fragments`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(res.statusText);

        const data = await res.json();
        const rawFragments = Array.isArray(data.fragments) ? data.fragments : [];
        if (!rawFragments.length) throw new Error('API returned empty fragments');

        const objectUrl = URL.createObjectURL(file);
        // Using batch index + timestamp for stable multisource ordering
        const sourceId = `src_${Date.now()}_${i}_${Math.random().toString(36).substr(2, 4)}`;

        const enrichedFragments = rawFragments.map((frag) => ({
          ...frag,
          id: `${sourceId}_${frag.id}`,
          sourceId,
          src: objectUrl,
          label: frag.id,
          duration: frag.duration ?? Math.round((frag.end - frag.start) * 1000) / 1000,
        }));

        const newSource = {
          id: sourceId,
          fileName: file.name,
          sourceType: 'local-upload',
          objectUrl,
          durationMs: enrichedFragments.reduce((max, f) => Math.max(max, (f.end || 0) * 1000), 0),
          fragments: enrichedFragments
        };

        newSources.push(newSource);

        // Persist to Workspace Context
        if (selectedWorkspaceId) addSourceToWorkspace?.(selectedWorkspaceId, newSource);

      } catch (err) {
        console.warn('Failed to generate fragments for', file.name, err);
        setMessages((prev) => [...prev, { role: 'system', text: `[Error] Upload Failed for ${file.name}: ${err.message || String(err)}` }]);
      }
    }

    if (newSources.length === 0) return { ok: false };

    // Set fallback video URL for the preview player if necessary
    setVideoURL(newSources[0].objectUrl);

    // Pool fragments
    const existingSources = workspaceData.sources || [];
    const allSources = [...existingSources, ...newSources];
    const pooledFragments = allSources.flatMap(s => s.fragments);

    sourceFragmentsRef.current = pooledFragments;
    setSourceFragments(pooledFragments);

    const userMsg = { role: 'user', text: `Uploaded ${newSources.length} Video(s)` };
    setMessages((prev) => [...prev, userMsg]);

    // Integration Strategy
    if (integration === 'regenerate-proposals') {
      const nextProposals = buildProposalsFromFragments(pooledFragments);
      setProposals(nextProposals.slice(0, 2));
      setMessages((prev) => [...prev, { role: 'system', text: '영상 분석이 완료되었습니다. 전체 소스를 기준으로 새로운 제안 A와 B가 추가로 준비되었습니다. (기존 편집은 덮어쓰지 않습니다)' }]);
    } else {
      // source-only append
      setMessages((prev) => [...prev, { role: 'system', text: '기존 편집 상태를 유지하며 원본 소스만 파노라마 대기열에 추가했습니다.' }]);
    }

    return { ok: true, count: pooledFragments.length };

  }, [addSourceToWorkspace, selectedWorkspaceId, workspaceData.sources, setVideoURL]);

  // Pick up queued global batch uploads from Modal
  useEffect(() => {
    if (uploadDecisionFlow && uploadDecisionFlow.step === 0 && uploadDecisionFlow.files.length > 0 && uploadDecisionFlow.integration) {
      if (uploadDecisionFlow.targetWorkspaceId === null || uploadDecisionFlow.targetWorkspaceId === selectedWorkspaceId) {
        const filesToProcess = [...uploadDecisionFlow.files];
        const mode = uploadDecisionFlow.mode;
        const integration = uploadDecisionFlow.integration;

        setUploadDecisionFlow({ files: [], step: 0, targetWorkspaceId: null, mode: null, integration: null });
        handleBatchUpload(filesToProcess, mode, integration);
      }
    }
  }, [uploadDecisionFlow, selectedWorkspaceId, handleBatchUpload, setUploadDecisionFlow]);

  const handleGlobalUploadTrigger = useCallback((payload) => {
    // payload can be a File or FileList or Array depending on ChatUI
    let filesArr = Array.isArray(payload) ? payload : (payload instanceof FileList ? Array.from(payload) : [payload]);
    filesArr = filesArr.filter(f => f && typeof f.name === 'string');
    if (!filesArr.length) return;

    if (!workspaceList || workspaceList.length === 0) {
      const newId = createWorkspace(filesArr[0].name);
      selectWorkspace(newId);
      setUploadDecisionFlow({
        files: filesArr, step: 0, targetWorkspaceId: newId, mode: 'new-workspace', integration: 'regenerate-proposals'
      });
    } else {
      setUploadDecisionFlow({
        files: filesArr, step: 1, targetWorkspaceId: selectedWorkspaceId, mode: null, integration: null
      });
    }
  }, [workspaceList, createWorkspace, selectWorkspace, setUploadDecisionFlow, selectedWorkspaceId]);

  const handleSelectProposal = (p) => {
    // Immediate signature check to bypass any state delay
    const isActuallyDirty = currentSignatureRef.current !== cleanSignatureRef.current;

    console.log('[MainLayout] handleSelectProposal:', p.id, '| Dirty:', isActuallyDirty);

    if (isActuallyDirty && selectedProposal) {
      const confirmMsg = {
        role: 'system',
        text: `편집중이던 ${selectedProposal.id} 제안의 내용이 사라집니다. 계속하시겠습니까?`,
        actions: [
          {
            label: '계속 (전환)',
            primary: true,
            onClick: () => confirmSwitch(p)
          },
          {
            label: '취소',
            primary: false,
            onClick: () => {
              setMessages(prev => [...prev, { role: 'system', text: '제안 전환을 취소했습니다.' }]);
              setPendingSwitchProposal(null);
            }
          }
        ]
      };
      setPendingSwitchProposal(p);
      setMessages(prev => [...prev, confirmMsg]);
      return;
    }

    confirmSwitch(p);
  };

  const confirmSwitch = (p) => {
    console.log('[MainLayout] confirmSwitch executed for:', p?.id);
    if (!activateProposal(p)) {
      console.error('[MainLayout] activateProposal failed for:', p?.id);
      return;
    }
    setMessages((prev) => [...prev, { role: 'system', text: `${p.id} 제안이 선택되었습니다. 편집 모드로 전환합니다.` }]);
    setIsDirty(false);
    setPendingSwitchProposal(null);
  };

  const handleSend = useCallback(() => {
    if (!input.trim()) return;
    const userMsg = { role: 'user', text: input };
    setMessages(prev => [...prev, userMsg]);
    onAction?.(input);

    const lower = input.toLowerCase().trim();

    // 0. Detect VFX (Cognitive Editing) - Decoupled keywords for maximum flexibility
    const vfxKeywords = ['눈', '비', '폭발', '불꽃'];
    const foundVFX = vfxKeywords.find(kw => lower.includes(kw));
    const isVFXIntent = foundVFX && (
      lower.includes('내려') || lower.includes('와') || lower.includes('해') ||
      lower.includes('넣어') || lower.includes('줘') || lower.includes('보여') ||
      lower.includes('적용') || lower.includes('뿌려')
    );

    // 1. Handle Pending Confirmation NLP
    if (pendingSwitchProposal) {
      if (lower.includes('계속') || lower.includes('응') || lower.includes('yes') || lower.includes('해') || lower.includes('그래') || lower.includes('ㅇㅇ')) {
        confirmSwitch(pendingSwitchProposal);
        setInput('');
        return;
      }
      if (lower.includes('취소') || lower.includes('아니') || lower.includes('no') || lower.includes('안해') || lower.includes('ㄴㄴ')) {
        setMessages(prev => [...prev, { role: 'system', text: '전환을 취소했습니다.' }]);
        setPendingSwitchProposal(null);
        setInput('');
        return;
      }
    }

    // 1.5 Detect Decision / Confirmation
    if (lower.includes('결정') || lower.includes('확정') || lower.includes('선택완료') || lower.includes('완료해') || lower === 'ok') {
      if (isEditing) {
        setIsDirty(false);
        cleanSignatureRef.current = currentSignatureRef.current;
        setMessages(prev => [...prev, { role: 'system', text: '현재 편집본으로 결정이 완료되었습니다. 내보내기를 진행할 수 있습니다.' }]);
      } else {
        setMessages(prev => [...prev, { role: 'system', text: '아직 편집 모드가 아닙니다. 원하는 제안의 방향성 버튼(A지정, B지정)을 먼저 선택해 주세요.' }]);
      }
      setInput('');
      return;
    }

    // 1.6 Detect Export / 내보내기
    if (lower.includes('내보내') || lower.includes('추출') || lower.includes('export') || lower.includes('렌더링')) {
      if (isEditing && cleanSignatureRef.current === currentSignatureRef.current) {
        setMessages(prev => [...prev, { role: 'system', text: '영상 추출 및 내보내기 작업이 백그라운드에서 시작되었습니다. 완료 시 이메일 또는 알림을 전송해 드립니다! (현재는 목업 동작입니다)' }]);
      } else {
        setMessages(prev => [...prev, { role: 'system', text: '제안을 확정짓지 않았거나 남은 편집 사항이 있습니다. 먼저 "결정한다" 라고 명령어 입력 후 내보내기를 시도해 주세요.' }]);
      }
      setInput('');
      return;
    }

    let reply = `명령어 해석: ${input}`;

    // 2. Check if user wants different proposals
    const isNewProposalIntent = [
      '다른', '새로운', '다시', '바꿔', '다른거', '딴거', 'new', 'another', 'different', '거절', '싫어'
    ].some(keyword => lower.includes(keyword)) &&
      (lower.includes('제안') || lower.includes('영상') || lower.includes('거') || lower.includes('줘') || lower.includes('해')) &&
      !lower.match(/\d+/); // Don't trigger new suggestions if user is mentioning specific indices

    if (isNewProposalIntent || lower === 'reject') {
      const proposalSource = sourceFragmentsRef.current.length ? sourceFragmentsRef.current : sourceFragments;
      const nextProposals = buildProposalsFromFragments(proposalSource).slice(2);

      setMessages(prev => [...prev, { role: 'system', text: '기존 제안을 지우고, 다른 제안 세트를 생성 중입니다...' }]);
      setInput('');
      setIsEditing(false);
      setSelectedProposal(null);
      setSelectedFragments([]);
      setProposals([]); // Clear A and B
      setPendingSwitchProposal(null);

      if (!nextProposals.length) {
        setTimeout(() => {
          setMessages(prev => [...prev, { role: 'system', text: '더 이상 생성할 수 있는 새로운 제안이 없습니다.' }]);
        }, 1000);
        return;
      }

      setTimeout(() => {
        setMessages(prev => [...prev, { role: 'system', text: '분석된 조각들로부터 제안 C와 D를 생성했습니다.' }]);
        setProposals(nextProposals);
      }, 1500);
      return;
    }

    // 3. Chat Editing Suite (Structural Edits)
    const deleteMatch = lower.match(/(?:A)?(\d+)(?:번째|번|개|조각)?\s*(?:지워|삭제|탈락)/i);
    const swapMatch = lower.match(/(?:A)?(\d+)(?:번)?(?:이랑|하고|와|과)\s*(?:A)?(\d+)(?:번)?\s*(?:바꿔|교체)/i);
    const clearMatch = lower.match(/(?:다|전부|모두)\s*(?:지워|삭제|초기화)/i);
    const addMatch = lower.match(/(?:f|frag|조각|A)(\d+)\s*(?:추가|넣어|빌드)/i);
    const trimMatch = lower.match(/(?:A)?(\d+)(?:번째|번)?\s*(?:(\d+)초|일초|잠깐)\s*(?:잘라|줄여|늘려)/i);

    if (deleteMatch) {
      const idx = parseInt(deleteMatch[1]) - 1;
      if (idx >= 0 && idx < selectedFragments.length) {
        const removed = selectedFragments[idx];
        const next = selectedFragments.filter((_, i) => i !== idx);
        setSelectedFragments(next);
        reply = `${idx + 1}번째 조각(${getFragmentLabel(removed)})을 삭제했습니다.`;
        if (isEditing) {
          const sig = calculateSignature(next);
          currentSignatureRef.current = sig;
          if (sig !== cleanSignatureRef.current) setIsDirty(true);
        }
      } else {
        reply = `현재 편집본에 ${deleteMatch[1]}번째 조각이 없습니다. (총 ${selectedFragments.length}개)`;
      }
      setMessages(prev => [...prev, { role: 'system', text: reply }]);
      setInput('');
      return;
    }
    else if (swapMatch) {
      const idx1 = parseInt(swapMatch[1]) - 1;
      const idx2 = parseInt(swapMatch[2]) - 1;
      if (idx1 >= 0 && idx1 < selectedFragments.length && idx2 >= 0 && idx2 < selectedFragments.length) {
        const next = [...selectedFragments];
        [next[idx1], next[idx2]] = [next[idx2], next[idx1]];
        setSelectedFragments(next);
        reply = `${idx1 + 1}번과 ${idx2 + 1}번 조각의 위치를 서로 바꿨습니다.`;
        if (isEditing) {
          const sig = calculateSignature(next);
          currentSignatureRef.current = sig;
          if (sig !== cleanSignatureRef.current) setIsDirty(true);
        }
      } else {
        reply = '바꾸려는 조각의 번호과 현재 편집본의 범위를 벗어납니다.';
      }
      setMessages(prev => [...prev, { role: 'system', text: reply }]);
      setInput('');
      return;
    }
    else if (clearMatch) {
      setSelectedFragments([]);
      reply = '편집 타임라인을 모두 비웠습니다.';
      if (isEditing) {
        currentSignatureRef.current = '';
        setIsDirty(true);
      }
      setMessages(prev => [...prev, { role: 'system', text: reply }]);
      setInput('');
      return;
    }
    else if (addMatch) {
      const num = addMatch[1];
      const target = sourceFragments.find(f => f.id === `frag_${num}` || (f.label && f.label.toUpperCase() === `F${num}`));
      if (target) {
        const next = [...selectedFragments, target];
        setSelectedFragments(next);
        reply = `${getFragmentLabel(target)} 조각을 타임라인 끝에 추가했습니다.`;
        if (isEditing) {
          const sig = calculateSignature(next);
          currentSignatureRef.current = sig;
          if (sig !== cleanSignatureRef.current) setIsDirty(true);
        }
      } else {
        reply = `원본 조각 중에 ${num}번 조각을 찾을 수 없습니다.`;
      }
      setMessages(prev => [...prev, { role: 'system', text: reply }]);
      setInput('');
      return;
    }
    else if (trimMatch) {
      const idx = parseInt(trimMatch[1]) - 1;
      const seconds = trimMatch[2] ? parseFloat(trimMatch[2]) : 1.0;
      if (idx >= 0 && idx < selectedFragments.length) {
        const next = [...selectedFragments];
        const frag = { ...next[idx] };
        if (frag.end - frag.start > seconds) {
          frag.end -= seconds;
          next[idx] = frag;
          setSelectedFragments(next);
          reply = `${idx + 1}번 조각의 끝을 ${seconds}초만큼 줄였습니다.`;
          if (isEditing) {
            const sig = calculateSignature(next);
            currentSignatureRef.current = sig;
            if (sig !== cleanSignatureRef.current) setIsDirty(true);
          }
        } else {
          reply = '조각이 너무 짧아 더 이상 줄일 수 없습니다.';
        }
      } else {
        reply = `현재 편집본에 ${trimMatch[1]}번 조각이 없습니다.`;
      }
      setMessages(prev => [...prev, { role: 'system', text: reply }]);
      setInput('');
      return;
    }

    if (['1', 'a', '첫번째', '첫 번째'].includes(lower)) {
      if (proposals.length > 0) {
        handleSelectProposal(proposals[0]);
        setInput('');
        return;
      }
    }
    else if (['2', 'b', '두번째', '두 번째'].includes(lower)) {
      if (proposals.length > 1) {
        handleSelectProposal(proposals[1]);
        setInput('');
        return;
      }
    }
    else if (['c'].includes(lower)) {
      if (proposals.length > 0) {
        handleSelectProposal(proposals[0]);
        setInput('');
        return;
      }
    }
    else if (['d'].includes(lower)) {
      if (proposals.length > 1) {
        handleSelectProposal(proposals[1]);
        setInput('');
        return;
      }
    }
    else if (lower === 'play' || lower.includes('재생')) reply = '미리보기 재생을 시작합니다.';

    // 4. Magical Generative VFX (Global & Targeted)
    else if (isVFXIntent) {
      const fragMatch = lower.match(/(?:f|frag|조각|)(\d+)/i);
      setActiveFX(null);

      const updateFrags = (list, targetNum = null) => (list || []).map(f => {
        if (targetNum === null) return { ...f, fx: foundVFX };
        const idRegex = new RegExp(`^frag_${targetNum}(?:_|$)`);
        const isMatch = idRegex.test(f.id) || (f.label && f.label.toUpperCase() === `F${targetNum}`);
        return { ...f, fx: isMatch ? foundVFX : null };
      });

      const nextSource = updateFrags(sourceFragments, fragMatch ? fragMatch[1] : null);
      const nextSelected = updateFrags(selectedFragments, fragMatch ? fragMatch[1] : null);

      setSourceFragments(nextSource);
      sourceFragmentsRef.current = nextSource;
      setSelectedFragments(nextSelected);

      reply = fragMatch
        ? `F${fragMatch[1]} 조각에만 ${foundVFX} 효과를 적용하고 나머지는 제거했습니다.`
        : `${foundVFX} 효과를 전체 적용했습니다.`;

      // If it's a GLOBAL change, we treat it as an environmental shift (not a project edit)
      // If it's TARGETED, it's a project edit.
      if (isEditing) {
        const nextSig = calculateSignature(nextSelected);
        currentSignatureRef.current = nextSig; // Update current sig pointer

        if (fragMatch) {
          // Targeted: Mark as dirty if it differs from the baseline
          if (nextSig !== cleanSignatureRef.current) setIsDirty(true);
        } else {
          // Global: Update baseline so it doesn't trigger "modified" spam/dirty warning
          // Global VFX is treated like a "Viewing Mode" rather than a structural edit.
          cleanSignatureRef.current = nextSig;
          setIsDirty(false);
        }
      }
    }
    else if (lower.includes('효과') && (lower.includes('지워') || lower.includes('삭제'))) {
      setActiveFX(null);
      const clearFX = (list) => (list || []).map(f => ({ ...f, fx: null }));
      const nextSource = clearFX(sourceFragments);
      const nextSelected = clearFX(selectedFragments);
      setSourceFragments(nextSource);
      sourceFragmentsRef.current = nextSource;
      setSelectedFragments(nextSelected);
      reply = '모든 특수 효과를 제거했습니다.';
    }

    if (!reply || reply.includes('명령어 해석')) {
      reply = '죄송합니다. 해당 명령어를 이해하지 못했습니다. (지워, 바꿔, 추가, 눈 내려줘 등을 사용해 보세요)';
    }

    setMessages(prev => [...prev, { role: 'system', text: reply }]);
    setInput('');
  }, [activateProposal, input, onAction, proposals, sourceFragments, selectedFragments, isEditing]);

  // Determine if Chat should move to Right Panel
  // Criteria: Center width < 15 or is collapsed (delayed so it stays in center longer)
  const isChatMoved = widths.center < 15 || collapsed.center;

  const chatProps = {
    messages,
    input,
    setInput,
    onSend: handleSend,
    disabled: false,
    onFileUpload: handleGlobalUploadTrigger,
    proposals,
    selectedProposal,
    selectedFragments,
    onSelectProposal: handleSelectProposal,
    videoURL,
    sourceFragments,
    activeFX
  };

  return (
    <div ref={containerRef} className="main-layout" id="main-layout" style={{
      display: 'flex',
      width: '100%',
      height: '100vh',
      background: '#09090b',
      overflow: 'hidden'
    }}>
      <ResizablePanel id="left" headerLeft={
        <div style={{ display: 'flex', flexDirection: 'column', marginTop: 2, paddingLeft: 4 }}>
          {/* Main Ornate Logo: C  C  U  [T] */}
          <div style={{
            fontFamily: '"Cormorant Garamond", "Cinzel", serif',
            fontSize: 22,
            fontWeight: 500,
            color: '#eaeaeb', // slightly warm off-white
            letterSpacing: '0.12em',
            whiteSpace: 'nowrap',
            lineHeight: 1
          }}>
            C&nbsp;&thinsp;C&nbsp;&thinsp;U&nbsp;&nbsp;<span style={{ display: 'inline-block', transform: 'scaleX(1.15)', transformOrigin: 'left' }}>T</span>
          </div>
          {/* Subtitle: Cognitive Cut */}
          <div style={{
            fontFamily: 'sans-serif',
            fontSize: 7.5,
            color: '#8b949e',
            letterSpacing: '0.42em',
            textTransform: 'uppercase',
            marginTop: 4,
            marginLeft: 2
          }}>
            Cognitive Cut
          </div>
        </div>
      }>
        <LeftPanel
          isEditing={isEditing}
          onWorkspaceCreate={() => { }}
          onWorkspaceSelect={() => { }}
          onFileUpload={handleGlobalUploadTrigger}
          isRightPanelOpen={isRightPanelOpen}
          setIsRightPanelOpen={setIsRightPanelOpen}
        />
      </ResizablePanel>

      <ResizeHandle between="lc" />

      <ResizablePanel id="center">
        {activeView === 'workspace' ? (
          <CenterPanel
            chatProps={chatProps}
          />
        ) : (
          <div style={{
            flex: 1, height: '100%', display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', background: '#09090b', color: '#71717a'
          }}>
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ marginBottom: 16 }}>
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            </svg>
            <div style={{ fontSize: 24, fontWeight: 300, letterSpacing: '0.1em' }}>
              {activeView.toUpperCase()} VIEW
            </div>
            <div style={{ marginTop: 8, fontSize: 13, color: '#52525b' }}>
              Placeholder for {activeView} content
            </div>
          </div>
        )}
      </ResizablePanel>

      {isRightPanelOpen && <ResizeHandle between="cr" />}

      <ResizablePanel id="right">
        {(activeView === 'workspace' && isRightPanelOpen) && (
          <RightPanel
            key={editSessionId}
            isEditing={isEditing}
            selectedProposal={selectedProposal}
            sources={workspaceData.sources || []}
            fragments={sourceFragments}
            selectedFragments={selectedFragments}
            onFragmentsChange={(next) => {
              if (isEditing) {
                const sig = calculateSignature(next);
                currentSignatureRef.current = sig;

                const isNowDirty = sig !== cleanSignatureRef.current;

                if (isNowDirty && !isDirty) {
                  setIsDirty(true);
                  setMessages(prev => [...prev, { role: 'system', text: '편집본이 변경되었습니다. 다른 제안으로 넘어가면 현재 작업 내용이 사라집니다.' }]);
                } else if (!isNowDirty && isDirty) {
                  setIsDirty(false);
                }
              }
              setSelectedFragments(next);
            }}
            chatProps={isChatMoved ? { ...chatProps, renderMode: 'input' } : null}
          />
        )}
      </ResizablePanel>
    </div>
  );
}
