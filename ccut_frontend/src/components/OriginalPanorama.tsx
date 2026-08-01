import React, { useRef, useEffect, useMemo, useState } from "react";
import { Fragment, allFragments } from "@/data/fragmentData";
import FragmentTile from "./FragmentTile";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface OriginalPanoramaProps {
  activeSource: string;
  onSourceChange: (src: string) => void;
  highlightedFragmentId: string | null;
  selectedFragmentId: string | null;
  onFragmentClick: (f: Fragment) => void;
  onFragmentPlay?: (f: Fragment) => void;
  intelligenceOn: boolean;
  onToggleIntelligence: () => void;
  fragmentOverrides?: Map<string, Fragment>;
  boundaryHighlightIds?: string[];
  // [UI-②] 분석 후에도 영상 추가/빼기
  onAddSource?: () => void;
  onRemoveSource?: (source: any) => void;
  onRenameSource?: (source: any, name: string) => void;
  compactLabels?: boolean;
  onBoundaryClick?: (leftFragId: string | null, rightFragId: string | null) => void;
  sourceFragments?: Fragment[];
  sources?: { source_id: string; label?: string; title?: string; file_path?: string; video_url?: string }[];
  /** [LAB-38 C] 하이라이트 출처 — FragmentMap:127과 동일 게이트용. 기본 "user"(기존 동작 보존). */
  focusOrigin?: "sequence" | "user";
}

const OriginalPanorama: React.FC<OriginalPanoramaProps> = ({
  activeSource,
  onSourceChange,
  highlightedFragmentId,
  selectedFragmentId,
  onFragmentClick,
  onFragmentPlay,
  intelligenceOn,
  onToggleIntelligence,
  fragmentOverrides,
  boundaryHighlightIds,
  onBoundaryClick,
  sourceFragments = [],
  sources = [],
  onAddSource,
  onRemoveSource,
  onRenameSource,
  compactLabels,
  focusOrigin = "user",
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [renamingSourceId, setRenamingSourceId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [hoveredPlayId, setHoveredPlayId] = useState<string | null>(null);

  useEffect(() => {
    if (highlightedFragmentId && scrollRef.current) {
      // [LAB-38 C] 스크롤 따라가기는 **사용자 클릭일 때만** — FragmentMap.tsx:127과 같은 게이트.
      //   시퀀스 재생 진행(origin="sequence")마다 scrollIntoView가 조상 스크롤을 끌어
      //   화면이 위/아래로 튀었다(실측: 매 경계 SCROLL_REPORT 발화와 튐 일치, 2026-07-29).
      //   하이라이트는 렌더가 담당하므로 여기서 스크롤만 생략하면 추적 표시는 산다.
      if (focusOrigin !== "user") return;
      const el = scrollRef.current.querySelector(`[data-fid="${highlightedFragmentId}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }, [highlightedFragmentId, focusOrigin]);

  useEffect(() => {
    if (boundaryHighlightIds && boundaryHighlightIds.length > 0 && scrollRef.current) {
      const el = scrollRef.current.querySelector(`[data-fid="${boundaryHighlightIds[0]}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }, [boundaryHighlightIds]);

  const baseFragments = useMemo(() => {
    if (sourceFragments.length > 0) return sourceFragments;
    return allFragments[activeSource] || [];
  }, [activeSource, sourceFragments]);

  const fragments = useMemo(() => {
    if (!fragmentOverrides || fragmentOverrides.size === 0) return baseFragments;
    return baseFragments.map((f) => {
      const override = fragmentOverrides.get(f.fragment_id);
      if (override) {
        return { ...f, duration: override.duration, start_frame: override.start_frame, end_frame: override.end_frame };
      }
      return f;
    });
  }, [baseFragments, fragmentOverrides]);

  const isBoundaryHighlighted = (fid: string) =>
    boundaryHighlightIds ? boundaryHighlightIds.includes(fid) : false;

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex flex-col bg-card/50 rounded-lg overflow-hidden border border-border/20">
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <h3 className="text-[12px] font-semibold text-foreground/80 uppercase tracking-widest whitespace-nowrap">원본맵</h3>
            <div className="flex gap-1 overflow-x-auto no-scrollbar flex-1 min-w-0 py-1">
              {sources && Array.isArray(sources) && sources.map((s) => (
                <span key={s.source_id} className="relative group/srctab flex-shrink-0">
                  {renamingSourceId === s.source_id ? (
                    <input
                      autoFocus
                      className="w-28 rounded-md border border-primary/35 bg-background/95 px-2 py-0.5 text-[12px] text-foreground outline-none shadow-lg"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          onRenameSource?.(s, renameValue.trim());
                          setRenamingSourceId(null);
                        }
                        if (e.key === "Escape") setRenamingSourceId(null);
                      }}
                      onBlur={() => {
                        if (renameValue.trim()) onRenameSource?.(s, renameValue.trim());
                        setRenamingSourceId(null);
                      }}
                    />
                  ) : (
                  <>
                  <button
                    onClick={() => onSourceChange(s.label || s.source_id)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setRenamingSourceId(s.source_id);
                      setRenameValue(String((s as any).display_name || (s as any).title || ""));
                    }}
                    /* [DISPLAY-NAME] 라벨만으론 어느 영상인지 알 수 없다 — 원본 제목 툴팁 */
                    title={(s as any).display_name || undefined}
                    className={`px-2 py-0.5 rounded-[3px] text-[12px] font-medium transition-all
                      ${(s.label || s.source_id) === activeSource
                        ? "bg-primary/20 text-primary"
                        : "text-muted-foreground/60 hover:text-foreground/70 hover:bg-secondary/40"
                      }`}
                  >
                    {(s as any).label || (s.source_id.split('_').pop() || s.source_id)}
                  </button>
                  <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 hidden -translate-x-1/2 whitespace-nowrap rounded-xl border border-white/10 bg-[hsl(228_14%_10%)] px-3 py-2 text-[12px] text-foreground/85 shadow-2xl shadow-black/45 group-hover/srctab:block">
                    {(s as any).display_name || ""}
                  </span>
                  </>
                  )}
                </span>
              ))}
              {/* [UI-②] 영상 추가 */}
              {onAddSource && (
                <button
                  title="영상 추가"
                  onClick={onAddSource}
                  className="px-1.5 py-0.5 rounded-[3px] text-[12px] font-bold text-muted-foreground/76 hover:text-primary hover:bg-primary/10 transition-all flex-shrink-0"
                >+</button>
              )}
            </div>
          </div>
        </div>

        <div
          ref={scrollRef}
          className="flex flex-row flex-nowrap items-center gap-0 px-2 py-2 overflow-x-auto panorama-scroll"
        >
          {fragments.map((f, i) => (
            <React.Fragment key={f.fragment_id}>
              <div
                data-fid={f.fragment_id}
                className={`relative transition-all duration-150 cursor-grab active:cursor-grabbing ${highlightedFragmentId === f.fragment_id
                  ? "ring-4 ring-primary/80 bg-primary/20 rounded shadow-[0_0_18px_rgba(96,165,250,0.45)]"
                  : isBoundaryHighlighted(f.fragment_id)
                    ? "ring-2 ring-primary/50 bg-primary/10 rounded"
                    : ""
                  }`}
                onMouseEnter={() => setHoveredPlayId(f.fragment_id)}
                onMouseMove={() => setHoveredPlayId(f.fragment_id)}
                onMouseLeave={() => setHoveredPlayId((current) => current === f.fragment_id ? null : current)}
                draggable={true}
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/ccut-fragment-hold", JSON.stringify(f));
                  e.dataTransfer.effectAllowed = "move";
                }}
              >
                <FragmentTile
                  fragment={f}
                  isSelected={selectedFragmentId === f.fragment_id}
                  isHighlighted={highlightedFragmentId === f.fragment_id || isBoundaryHighlighted(f.fragment_id)}
                  hasActiveSelection={!!selectedFragmentId}
                  onClick={() => onFragmentClick(f)}
                  widthScale={0.6}
                  variant="panorama"
                  compactLabelOnly={true}
                  showPlayButton={true}
                  playButtonVisible={hoveredPlayId === f.fragment_id}
                  onPlay={(e) => {
                    e.stopPropagation();
                    onFragmentPlay?.({
                      ...f,
                      video_url: (f as any).video_url ?? sources.find((s) => s.label === activeSource)?.video_url,
                    } as Fragment);
                  }}
                  showIntelligence={intelligenceOn}
                  videoPath={
                    // [FIX-ACTIVE-SOURCE] activeSource는 라벨(A/B/C), source_id와 혼동 금지
                    (sources.find((s) => s.label === activeSource)?.video_url ||
                      sources.find((s) => s.label === activeSource)?.file_path) ||
                    null
                  }
                />
              </div>
              {/* Boundary divider */}
              {i < fragments.length - 1 && (
                <div
                  className="w-px h-8 bg-border/30 flex-shrink-0 mx-0.5"
                />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
    </TooltipProvider>
  );
};

export default OriginalPanorama;
