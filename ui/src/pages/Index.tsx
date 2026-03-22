import React, { useState, useCallback, useRef, useEffect } from "react";
import LeftNav from "@/components/LeftNav";
import CenterPanel from "@/components/CenterPanel";
import { OriginalPanorama } from "@/components/OriginalPanorama";
import { FragmentMap } from "@/components/FragmentMap";
import { ReservedFragments } from "@/components/ReservedFragments";
import {
  Fragment,
  initialEditFragments,
  initialReservedFragments,
  sourceVideos,
  initialHoldAreaPositions,
} from "@/data/fragmentData";
import type { HoldPosition, PrecisionEntryHandle } from "@/types/boundaryTypes";

const STORAGE_KEY = "ccut-center-width";
const MIN_CENTER = 260;
const MIN_RIGHT = 400;
const DEFAULT_CENTER = 340;

const noop = () => {};
const noopFrag = (_f: Fragment) => {};
const noopBool = () => false;

const Index: React.FC = () => {
  const [activeNavItem, setActiveNavItem] = useState("projects");
  const [activeSource, setActiveSource] = useState("A");
  const [selectedFragment, setSelectedFragment] = useState<Fragment | null>(null);
  const [highlightedPanoramaFrag, setHighlightedPanoramaFrag] = useState<string | null>(null);
  const [expandedFragment, setExpandedFragment] = useState<string | null>(null);
  const [intelligenceOn, setIntelligenceOn] = useState(false);
  const [editFragments, setEditFragments] = useState<Fragment[]>(initialEditFragments);
  const [reservedFragments, setReservedFragments] = useState<Fragment[]>(initialReservedFragments);
  const [holdPositions] = useState<Record<string, HoldPosition>>(initialHoldAreaPositions);

  // Fragment overrides — Map<string, number> (duration overrides for boundary drag)
  const [fragmentOverrides, setFragmentOverrides] = useState<Map<string, number>>(new Map());

  // Splitter state
  const [centerWidth, setCenterWidth] = useState<number>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? Math.max(MIN_CENTER, Number(saved)) : DEFAULT_CENTER;
  });
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const leftNavWidth = 220;

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(centerWidth));
  }, [centerWidth]);

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const totalWidth = containerRect.width;
      const relativeX = e.clientX - containerRect.left - leftNavWidth;
      const maxCenter = totalWidth - leftNavWidth - MIN_RIGHT;
      const clamped = Math.max(MIN_CENTER, Math.min(maxCenter, relativeX));
      setCenterWidth(clamped);
    };
    const handleMouseUp = () => setIsDragging(false);
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging]);

  // Single click toggles selection
  const handleEditFragmentClick = useCallback((f: Fragment) => {
    if (selectedFragment?.fragment_id === f.fragment_id) {
      setSelectedFragment(null);
      setHighlightedPanoramaFrag(null);
      setExpandedFragment(null);
    } else {
      setSelectedFragment(f);
      setActiveSource(f.source_video);
      setHighlightedPanoramaFrag(f.fragment_id);
      setExpandedFragment(null);
    }
  }, [selectedFragment]);

  // Double click enters Time Lens
  const handleEditFragmentDoubleClick = useCallback((f: Fragment) => {
    setSelectedFragment(f);
    setActiveSource(f.source_video);
    setHighlightedPanoramaFrag(f.fragment_id);
    setExpandedFragment((prev) => (prev === f.fragment_id ? null : f.fragment_id));
  }, []);

  const handlePanoramaFragmentClick = useCallback((f: Fragment) => {
    if (selectedFragment?.fragment_id === f.fragment_id) {
      setSelectedFragment(null);
      setHighlightedPanoramaFrag(null);
    } else {
      setSelectedFragment(f);
    }
  }, [selectedFragment]);

  const handleReservedClick = useCallback((f: Fragment) => {
    if (selectedFragment?.fragment_id === f.fragment_id) {
      setSelectedFragment(null);
      setHighlightedPanoramaFrag(null);
    } else {
      setSelectedFragment(f);
      setActiveSource(f.source_video);
      setHighlightedPanoramaFrag(f.fragment_id);
    }
  }, [selectedFragment]);

  // Exclude from edit structure
  const handleExcludeFromEdit = useCallback((f: Fragment) => {
    setEditFragments((prev) =>
      prev.map((fr) =>
        fr.fragment_id === f.fragment_id ? { ...fr, excluded: !fr.excluded } : fr
      )
    );
  }, []);

  // Move to Hold Area
  const handleMoveToHold = useCallback((f: Fragment) => {
    setEditFragments((prev) => prev.filter((fr) => fr.fragment_id !== f.fragment_id));
    setReservedFragments((prev) => [...prev, { ...f, excluded: false }]);
    if (selectedFragment?.fragment_id === f.fragment_id) {
      setSelectedFragment(null);
    }
  }, [selectedFragment]);

  // Restore from Hold Area
  const handleRestoreFromHold = useCallback((f: Fragment) => {
    setReservedFragments((prev) => prev.filter((fr) => fr.fragment_id !== f.fragment_id));
    setEditFragments((prev) => [...prev, f]);
  }, []);

  // Reposition hold item
  const handleRepositionStart = useCallback((_fragment: Fragment, _event: React.MouseEvent<HTMLDivElement>) => {
    // Hold area reposition — stub for now
  }, []);

  // Global click-to-dismiss
  const handleBackgroundClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest(".fragment-tile")) return;
    setSelectedFragment(null);
    setHighlightedPanoramaFrag(null);
    setExpandedFragment(null);
  }, []);

  return (
    <div ref={containerRef} className="flex h-screen w-full overflow-hidden bg-background" onClick={handleBackgroundClick}>
      <LeftNav activeItem={activeNavItem} onItemClick={setActiveNavItem} />

      <div style={{ width: centerWidth, flexShrink: 0 }}>
        <CenterPanel
          selectedFragment={selectedFragment}
          selectedSource={activeSource}
          editSequence={editFragments}
        />
      </div>

      {/* Vertical Splitter */}
      <div
        className={`flex-shrink-0 flex items-center justify-center cursor-col-resize group transition-colors
          ${isDragging ? "bg-primary/15" : "hover:bg-primary/8"}`}
        style={{ width: 6 }}
        onMouseDown={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
      >
        <div
          className={`w-[2px] h-10 rounded-full transition-all duration-150
            ${isDragging
              ? "bg-primary/60 h-16"
              : "bg-border/40 group-hover:bg-primary/40 group-hover:h-14"
            }`}
        />
      </div>

      {/* Right Workspace */}
      <div className="flex-1 flex flex-col gap-2 p-2 overflow-hidden min-w-0">
        <OriginalPanorama
          sources={sourceVideos}
          fragments={editFragments}
          activeSource={activeSource}
          selectedFragmentId={selectedFragment?.fragment_id || null}
          highlightedFragmentId={highlightedPanoramaFrag}
          focusExpandedId={expandedFragment}
          intelligenceOn={intelligenceOn}
          fragmentOverrides={fragmentOverrides}
          onSourceChange={setActiveSource}
          onFragmentSelect={handlePanoramaFragmentClick}
          onToggleIntelligence={() => setIntelligenceOn((p) => !p)}
        />

        <div className="flex-1 overflow-y-auto">
          <FragmentMap
            editFragments={editFragments}
            selectedFragmentId={selectedFragment?.fragment_id || null}
            pairSelectedFragmentIds={[]}
            focusExpandedId={expandedFragment}
            timeLensId={null}
            playingFragmentId={null}
            playProgress={0}
            boundaryHighlightIds={[]}
            isBoundaryDragging={false}
            fragmentOverrides={fragmentOverrides}
            dragOrigin={null}
            dragTargetVisibleIndex={null}
            replaceTargetId={null}
            onFragmentSingleClick={handleEditFragmentClick}
            onFragmentDoubleClick={handleEditFragmentDoubleClick}
            onPairSelectionToggle={noopFrag}
            onPlayToggle={noopFrag}
            onExcludeToggle={handleExcludeFromEdit}
            onMoveToHold={handleMoveToHold}
            onPrecisionEntryOpen={(_handle: PrecisionEntryHandle, _rect: DOMRect) => {}}
            onDragStart={noop as any}
            onDragTargetIndexChange={noop as any}
            onReplaceTargetChange={noop as any}
            onReplaceDrop={noop as any}
            onDragDrop={noopBool}
            onDragEnd={noop}
          />
        </div>

        <ReservedFragments
          fragments={reservedFragments}
          positions={holdPositions}
          selectedFragmentId={selectedFragment?.fragment_id || null}
          focusExpandedId={expandedFragment}
          timeLensId={null}
          playingFragmentId={null}
          playProgress={0}
          onPlayToggle={noopFrag}
          onRestore={handleRestoreFromHold}
          onSelect={handleReservedClick}
          onRepositionStart={handleRepositionStart}
          onReplaceDragStart={noop as any}
          onReplaceDragEnd={noop}
        />
      </div>
    </div>
  );
};

export default Index;
