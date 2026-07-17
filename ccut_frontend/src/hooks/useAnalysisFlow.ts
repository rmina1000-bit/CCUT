import { useState, useCallback } from "react";
import { Fragment, initialEditFragments, initialReservedFragments } from "@/data/fragmentData";
import type { AppState, SourceEntry } from "@/types";

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

// ── [REFACTOR-01] Index god-component 해체: analysis 관련 13 state + reset 격리 ──
// 기능 변경 0. Index 원문 타입/초기값/순서/빈 deps 그대로 이동.
export function useAnalysisFlow() {
  const [selectedFragment, setSelectedFragment] = useState<Fragment | null>(null);
  const [highlightedPanoramaFrag, setHighlightedPanoramaFrag] = useState<string | null>(null);
  const [expandedFragment, setExpandedFragment] = useState<string | null>(null);
  const [editFragments, setEditFragments] = useState<Fragment[]>(initialEditFragments);
  // [#38 — "조각의 속성은 공유, 제안의 구성은 분리"] 보류·휴지통은 제안(A/B)별 구성 정보.
  // 원료 웅덩이(editFragments)는 공용 유지 — 조각 실물은 하나다 (헌장 §1-9).
  const [reservedByProposal, setReservedByProposal] = useState<Record<"A" | "B", Fragment[]>>({
    A: initialReservedFragments, B: initialReservedFragments,
  });
  const [deletedByProposal, setDeletedByProposal] = useState<Record<"A" | "B", Fragment[]>>({ A: [], B: [] });
  const [appState, setAppState] = useState<AppState>("empty");
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
    setReservedByProposal({ A: [], B: [] });
    setDeletedByProposal({ A: [], B: [] });
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
    reservedByProposal, setReservedByProposal,
    deletedByProposal, setDeletedByProposal,
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
