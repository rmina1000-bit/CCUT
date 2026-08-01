import React from "react";
import { Search, Loader2, Sparkles, Film } from "lucide-react";

interface FragSearchState {
  query: string;
  searching: boolean;
  results: any[];
  done: boolean;
}

interface FragSearchPanelProps {
  fragSearch: FragSearchState | null;
  onClose: () => void;
}

export const FragSearchPanel: React.FC<FragSearchPanelProps> = ({ fragSearch, onClose }) => {
  if (!fragSearch) return null;

  return (
    <div className="w-full max-w-[800px] flex flex-col gap-3 py-4 animate-in fade-in slide-in-from-top-2 duration-500">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-foreground/90">
          <Search size={16} className="text-primary" />
          <span className="text-[14px] font-medium">
            “{fragSearch.query}” 조각 검색
          </span>
          {fragSearch.done && (
            <span className="text-[12px] text-muted-foreground/60">
              · {fragSearch.results.length}개
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-[12px] text-muted-foreground/76 hover:text-foreground/80 transition-colors px-2 py-1"
        >
          닫기 ✕
        </button>
      </div>

      {fragSearch.searching && (
        <div className="flex items-center gap-2 text-primary/60 py-6 justify-center">
          <Loader2 size={16} className="animate-spin" />
          <span className="text-[13px] animate-pulse">조각 자산을 검색하는 중...</span>
        </div>
      )}

      {fragSearch.done && fragSearch.results.length === 0 && (
        <div className="text-[13px] text-muted-foreground/60 py-6 text-center">
          관련 조각을 찾지 못했습니다. 다른 표현으로 다시 시도해 보세요.
        </div>
      )}

      {fragSearch.done && fragSearch.results.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {fragSearch.results.map((r) => (
            <div
              key={r.fragment_id}
              className="flex flex-col gap-2 p-3 rounded-xl bg-[#161618] border border-white/5 hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-2 flex-wrap">
                {r.role && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/15 text-primary font-medium">
                    {r.role}
                  </span>
                )}
                {r.is_curated && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 font-medium flex items-center gap-1">
                    <Sparkles size={9} /> 사용된 조각
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground/76 ml-auto flex items-center gap-1">
                  <Film size={10} /> #{(r.source_id || "").replace("SRC_", "").slice(0, 8)}
                </span>
              </div>
              <p className="text-[12px] leading-relaxed text-foreground/75 line-clamp-3">
                {r.visual_desc || r.transcript || "(설명 없음)"}
              </p>
              <div className="flex items-center justify-between text-[10px] text-muted-foreground/76 mt-auto pt-1">
                <span>
                  {r.start?.toFixed(1)}s ~ {r.end?.toFixed(1)}s
                  <span className="text-muted-foreground/65"> ({r.duration?.toFixed(1)}s)</span>
                </span>
                <span className="flex items-center gap-2">
                  {r.keyword_hit && <span className="text-emerald-400/70">키워드</span>}
                  <span className="text-primary/60">유사도 {(r.score * 100).toFixed(0)}%</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
