import { useState, useCallback } from "react";
import { Fragment, initialEditFragments, initialReservedFragments } from "@/data/fragmentData";

// ── [REFACTOR-01] Index.tsx에서 이관된 analysis 타입 (원문 그대로) ──
export type QuickScanData = {
  source_id?: string;
  status?: string;
  summary?: any;
  hypothesis?: any;
  questions?: any[];
  default_intent_seed?: any;
};

export type SemanticFragmentData = {
  fragment_id: string;
  source_id?: string;
  start: number;
  end: number;
  semantic?: any;
  structural?: any;
  continuity?: any;
  confidence?: number;
  fallback_reason?: string | null;
};

export type SourceEntry = {
  source_id: string;
  label: string;
  video_url: string;
  fragments: Fragment[];
  file_size_bytes?: number;
  duration_sec?: number;
};

// ── [REFACTOR-01] Index god-component 해체: analysis 관련 13 state + reset 격리 ──
// 기능 변경 0. Index 원문 타입/초기값/순서/빈 deps 그대로 이동.
export function useAnalysisFlow() {
  const [selectedFragment, setSelectedFragment] = useState<Fragment | null>(null);
  const [highlightedPanoramaFrag, setHighlightedPanoramaFrag] = useState<string | null>(null);
  const [expandedFragment, setExpandedFragment] = useState<string | null>(null);
  const [editFragments, setEditFragments] = useState<Fragment[]>(initialEditFragments);
  const [reservedFragments, setReservedFragments] = useState<Fragment[]>(initialReservedFragments);
  const [deletedFragments, setDeletedFragments] = useState<Fragment[]>([]);
  const [appState, setAppState] = useState<"empty" | "analyzing" | "complete">("empty");
  const [sourceFragments, setSourceFragments] = useState<Fragment[]>([]);
  const [currentSourceId, setCurrentSourceId] = useState<string | null>(null);
  const [currentVideoUrl, setCurrentVideoUrl] = useState<string | null>(null);
  const [quickScanData, setQuickScanData] = useState<QuickScanData | null>(null);
  const [semanticFragments, setSemanticFragments] = useState<SemanticFragmentData[]>([]);
  const [sourceEntries, setSourceEntries] = useState<SourceEntry[]>([]);

  // Index 원본 resetAnalysisState의 13개 setter (proposal 4개 제외) — 순서 그대로, 빈 deps 그대로.
  const resetAnalysisFlow = useCallback(() => {
    setSourceFragments([]);
    setEditFragments([]);
    setReservedFragments([]);
    setDeletedFragments([]);
    setSelectedFragment(null);
    setHighlightedPanoramaFrag(null);
    setExpandedFragment(null);
    setCurrentSourceId(null);
    setCurrentVideoUrl(null);
    setSourceEntries([]);
    setQuickScanData(null);
    setSemanticFragments([]);
    setAppState("empty");
  }, []);

  return {
    selectedFragment, setSelectedFragment,
    highlightedPanoramaFrag, setHighlightedPanoramaFrag,
    expandedFragment, setExpandedFragment,
    editFragments, setEditFragments,
    reservedFragments, setReservedFragments,
    deletedFragments, setDeletedFragments,
    appState, setAppState,
    sourceFragments, setSourceFragments,
    currentSourceId, setCurrentSourceId,
    currentVideoUrl, setCurrentVideoUrl,
    quickScanData, setQuickScanData,
    semanticFragments, setSemanticFragments,
    sourceEntries, setSourceEntries,
    resetAnalysisFlow,
  };
}
