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
  // [UI-②] 분석 후에도 영상 추가/빼기
  onAddSource?: () => void;
  onRemoveSource?: (source: any) => void;
  onBoundaryClick?: (leftFragId: string | null, rightFragId: string | null) => void;
  sourceFragments?: Fragment[];
  sources?: { source_id: string; label?: string; title?: string; file_path?: string; video_url?: string }[];
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
  onAddSource,
  onRemoveSource,
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
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <h3 className="text-[11px] font-semibold text-foreground/80 uppercase tracking-widest whitespace-nowrap">원본맵</h3>
            <div className="flex gap-1 overflow-x-auto no-scrollbar flex-1 min-w-0 py-1">
              {sources && Array.isArray(sources) && sources.map((s) => (
                <span key={s.source_id} className="relative group/srctab flex-shrink-0">
                  <button
                    onClick={() => onSourceChange(s.label || s.source_id)}
                    /* [DISPLAY-NAME] 라벨만으론 어느 영상인지 알 수 없다 — 원본 제목 툴팁 */
                    title={(s as any).title ? String((s as any).title).replace(/\.[A-Za-z0-9]{2,4}$/, "") : undefined}
                    className={`px-2 py-0.5 rounded-[3px] text-[9px] font-medium transition-all
                      ${(s.label || s.source_id) === activeSource
                        ? "bg-primary/20 text-primary"
                        : "text-muted-foreground/60 hover:text-foreground/70 hover:bg-secondary/40"
                      }`}
                  >
                    {(s as any).label || (s.source_id.split('_').pop() || s.source_id)}
                  </button>
                  {/* [UI-②] 호버 시 이 영상을 프로젝트에서 빼기 */}
                  {onRemoveSource && (
                    <button
                      title="이 영상 빼기"
                      onClick={(e) => { e.stopPropagation(); onRemoveSource(s); }}
                      className="absolute -top-1 -right-1 hidden group-hover/srctab:flex w-3 h-3 items-center justify-center rounded-full bg-red-600 text-white text-[8px] leading-none"
                    >×</button>
                  )}
                </span>
              ))}
              {/* [UI-②] 영상 추가 */}
              {onAddSource && (
                <button
                  title="영상 추가"
                  onClick={onAddSource}
                  className="px-1.5 py-0.5 rounded-[3px] text-[10px] font-bold text-muted-foreground/50 hover:text-primary hover:bg-primary/10 transition-all flex-shrink-0"
                >＋</button>
              )}
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
