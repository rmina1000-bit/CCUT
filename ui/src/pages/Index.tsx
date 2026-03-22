import React, { useState, useCallback, useRef, useEffect } from "react";
import LeftNav from "@/components/LeftNav";
import CenterPanel from "@/components/CenterPanel";
import { OriginalPanorama } from "@/components/OriginalPanorama";
import { FragmentMap } from "@/components/FragmentMap";
import { ReservedFragments } from "@/components/ReservedFragments";
import { Fragment, initialEditFragments, initialReservedFragments } from "@/data/fragmentData";
const STORAGE_KEY = "ccut-center-width";
const MIN_CENTER = 260;
const MIN_RIGHT = 400;
const DEFAULT_CENTER = 340;
const Index: React.FC = () => {
  const [activeNavItem, setActiveNavItem] = useState("projects");
  const [activeSource, setActiveSource] = useState("A");
  const [selectedFragment, setSelectedFragment] = useState<Fragment | null>(null);
  const [highlightedPanoramaFrag, setHighlightedPanoramaFrag] = useState<string | null>(null);
  const [expandedFragment, setExpandedFragment] = useState<string | null>(null);
  const [intelligenceOn, setIntelligenceOn] = useState(false);
  const [editFragments, setEditFragments] = useState<Fragment[]>(initialEditFragments);
  const [reservedFragments, setReservedFragments] = useState<Fragment[]>(initialReservedFragments);
  // Boundary drag source-recall state
  const [boundaryHighlightIds, setBoundaryHighlightIds] = useState<string[]>([]);
  const [fragmentOverrides, setFragmentOverrides] = useState<Map<string, Fragment>>(new Map());
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
  // Exclude from edit structure: toggle excluded flag (structurally preserved for boundaries)
  const handleExcludeFromEdit = useCallback((f: Fragment) => {
    setEditFragments((prev) =>
      prev.map((fr) =>
        fr.fragment_id === f.fragment_id
          ? { ...fr, excluded: true }
          : fr
      )
    );
    // Keep selection so user sees the excluded state
  }, []);
  // Restore excluded fragment back to active render
  const handleRestoreFragment = useCallback((f: Fragment) => {
    setEditFragments((prev) =>
      prev.map((fr) =>
        fr.fragment_id === f.fragment_id
          ? { ...fr, excluded: false }
          : fr
      )
    );
  }, []);
  // Move to Hold Area (fully remove from edit structure to reserved)
  const handleMoveToHold = useCallback((f: Fragment) => {
    setEditFragments((prev) => prev.filter((fr) => fr.fragment_id !== f.fragment_id));
    setReservedFragments((prev) => [...prev, { ...f, excluded: false }]);
    if (selectedFragment?.fragment_id === f.fragment_id) {
      setSelectedFragment(null);
    }
  }, [selectedFragment]);
  // Restore from Hold Area (re-add to end of edit structure)
  const handleRestoreFromHold = useCallback((f: Fragment) => {
    setReservedFragments((prev) => prev.filter((fr) => fr.fragment_id !== f.fragment_id));
    setEditFragments((prev) => [...prev, f]);
  }, []);
  // Deleted fragments (trash bin state)
  const [deletedFragments, setDeletedFragments] = useState<Fragment[]>([]);
  // Delete from Hold Area — move to trash (not permanent)
  const handleDeleteFromHold = useCallback((f: Fragment) => {
    setReservedFragments((prev) => prev.filter((fr) => fr.fragment_id !== f.fragment_id));
    setDeletedFragments((prev) => [...prev, f]);
    if (selectedFragment?.fragment_id === f.fragment_id) {
      setSelectedFragment(null);
    }
  }, [selectedFragment]);
  // Restore from trash to hold area
  const handleRestoreToHold = useCallback((f: Fragment) => {
    setDeletedFragments((prev) => prev.filter((fr) => fr.fragment_id !== f.fragment_id));
    setReservedFragments((prev) => [...prev, f]);
  }, []);
  // Restore from trash to edit structure
  const handleRestoreToEdit = useCallback((f: Fragment) => {
    setDeletedFragments((prev) => prev.filter((fr) => fr.fragment_id !== f.fragment_id));
    setEditFragments((prev) => [...prev, f]);
  }, []);
  // Empty trash permanently
  const handleEmptyTrash = useCallback(() => {
    setDeletedFragments([]);
  }, []);
  // Boundary drag: source recall + override sync
  const handleBoundaryDragChange = useCallback((leftFrag: Fragment | null, rightFrag: Fragment | null) => {
    if (!leftFrag || !rightFrag) {
      setBoundaryHighlightIds([]);
      setFragmentOverrides(new Map());
      return;
    }
    setActiveSource(leftFrag.source_video);
    setBoundaryHighlightIds([leftFrag.fragment_id, rightFrag.fragment_id]);
  }, []);
  // Keep overrides in sync with editFragments during boundary drag
  useEffect(() => {
    if (boundaryHighlightIds.length === 0) return;
    const overrides = new Map<string, Fragment>();
    for (const fid of boundaryHighlightIds) {
      const frag = editFragments.find((f) => f.fragment_id === fid);
      if (frag) overrides.set(fid, frag);
    }
    setFragmentOverrides(overrides);
  }, [editFragments, boundaryHighlightIds]);
  // Global click-to-dismiss: clicking empty space restores default state
  const handleBackgroundClick = useCallback((e: React.MouseEvent) => {
    // Only dismiss if clicking directly on a background container, not a fragment
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
          activeSource={activeSource}
          onSourceChange={setActiveSource}
          highlightedFragmentId={highlightedPanoramaFrag}
          selectedFragmentId={selectedFragment?.fragment_id || null}
          onFragmentClick={handlePanoramaFragmentClick}
          intelligenceOn={intelligenceOn}
          onToggleIntelligence={() => setIntelligenceOn((p) => !p)}
          fragmentOverrides={fragmentOverrides}
          boundaryHighlightIds={boundaryHighlightIds}
        />
        <div className="flex-1 overflow-y-auto">
          <FragmentMap
            fragments={editFragments}
            onFragmentsChange={setEditFragments}
            selectedFragmentId={selectedFragment?.fragment_id || null}
            expandedFragmentId={expandedFragment}
            onFragmentClick={handleEditFragmentClick}
            onFragmentDoubleClick={handleEditFragmentDoubleClick}
            onExcludeFragment={handleExcludeFromEdit}
            onRestoreFragment={handleRestoreFragment}
            onMoveToHold={handleMoveToHold}
            onBoundaryDragChange={handleBoundaryDragChange}
            onTrashRestore={handleRestoreToEdit}
          />
        </div>
        <ReservedFragments
          fragments={reservedFragments}
          selectedFragmentId={selectedFragment?.fragment_id || null}
          onFragmentClick={handleReservedClick}
          onRestoreFragment={handleRestoreFromHold}
          onDeleteFragment={handleDeleteFromHold}
          deletedFragments={deletedFragments}
          onRestoreToHold={handleRestoreToHold}
          onRestoreToEdit={handleRestoreToEdit}
          onEmptyTrash={handleEmptyTrash}
        />
      </div>
    </div>
  );
};
export default Index;
