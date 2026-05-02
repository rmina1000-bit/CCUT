import React, { useRef, useEffect, useMemo } from "react";
import { Fragment, allFragments } from "@/data/fragmentData";
import FragmentTile from "./FragmentTile";
import { Eye, EyeOff } from "lucide-react";
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
  intelligenceOn: boolean;
  onToggleIntelligence: () => void;
  fragmentOverrides?: Map<string, Fragment>;
  boundaryHighlightIds?: string[];
  onBoundaryClick?: (leftIndex: number, rightIndex: number) => void;
  sourceFragments?: Fragment[];
  sources?: { source_id: string; file_path?: string; video_url?: string }[];
}

const OriginalPanorama: React.FC<OriginalPanoramaProps> = ({
  activeSource,
  onSourceChange,
  highlightedFragmentId,
  selectedFragmentId,
  onFragmentClick,
  intelligenceOn,
  onToggleIntelligence,
  fragmentOverrides,
  boundaryHighlightIds,
  onBoundaryClick,
  sourceFragments = [],
  sources = [],
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highlightedFragmentId && scrollRef.current) {
      const el = scrollRef.current.querySelector(`[data-fid="${highlightedFragmentId}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }, [highlightedFragmentId]);

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
          <div className="flex items-center gap-2.5">
            <h3 className="text-[11px] font-semibold text-foreground/80 uppercase tracking-widest whitespace-nowrap">원본맵</h3>
            <div className="flex gap-1 overflow-x-auto no-scrollbar max-w-[60%] py-1">
              {sources && Array.isArray(sources) && sources.map((s) => (
                <button
                  key={s.source_id}
                  onClick={() => onSourceChange(s.source_id)}
                  className={`px-2 py-0.5 rounded-[3px] text-[9px] font-medium transition-all flex-shrink-0
                    ${s.source_id === activeSource
                      ? "bg-primary/20 text-primary"
                      : "text-muted-foreground/60 hover:text-foreground/70 hover:bg-secondary/40"
                    }`}
                >
                  {(s as any).label || (s.source_id.split('_').pop() || s.source_id)}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={onToggleIntelligence}
            className={`flex items-center gap-1 px-1.5 py-0.5 rounded-[3px] text-[9px] font-medium transition-all
              ${intelligenceOn
                ? "bg-ccut-indigo/15 text-ccut-amber/80"
                : "text-muted-foreground/40 hover:text-foreground/50"
              }`}
          >
            {intelligenceOn ? <Eye size={10} /> : <EyeOff size={10} />}
            정보
          </button>
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
                  ? "ring-1 ring-primary/40"
                  : isBoundaryHighlighted(f.fragment_id)
                    ? "ring-1 ring-primary/30"
                    : ""
                  }`}
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
                  showIntelligence={intelligenceOn}
                  videoPath={
                    (sources.find((s) => s.source_id === activeSource)?.video_url ||
                      sources.find((s) => s.source_id === activeSource)?.file_path) ||
                    null
                  }
                />
              </div>
              {/* Boundary divider — click to open precision editor */}
              {i < fragments.length - 1 && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div
                      className="boundary-link w-px h-8 bg-border/30 flex-shrink-0 mx-0.5 cursor-pointer hover:bg-primary/50 hover:w-[2px] transition-all"
                      onClick={(e) => {
                        e.stopPropagation();
                        // Note: panorama boundaries use source-local indices, not edit indices.
                        // For now, this is a visual affordance. In production it would resolve to edit indices.
                        onBoundaryClick?.(i, i + 1);
                      }}
                    />
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="text-[9px]">
                    경계 편집 열기
                  </TooltipContent>
                </Tooltip>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
    </TooltipProvider>
  );
};

export default OriginalPanorama;
