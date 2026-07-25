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
  // [STORY-LAYER-01 A-1] 보류·휴지통 = 프로젝트 스코프 하나. 스토리가 program 단위 하나이므로
  // "어디로 뺐다/버렸다"도 하나다. 구판(#38 제안별 {A,B} 버킷)은 A와 B가 서로 다른 이야기를
  // 갖던 폐기 모델의 잔재 — A/B 전환마다 보류맵이 갈리는 원인이었다.
  const [reservedFragments, setReservedFragments] = useState<Fragment[]>(initialReservedFragments);
  const [deletedFragments, setDeletedFragments] = useState<Fragment[]>([]);
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
