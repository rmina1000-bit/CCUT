import React from "react";
import { Loader2 } from "lucide-react";

interface AnalysisLoadingViewProps {
  analyzeMessage?: string;
  analysisLogs?: string[];
  analyzeProgress: number;
}

export function AnalysisLoadingView({ analyzeMessage, analysisLogs, analyzeProgress }: AnalysisLoadingViewProps) {
  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="flex flex-col items-center gap-6 w-full max-w-[420px]">
        <div className="relative">
          <div className="w-16 h-16 rounded-2xl bg-secondary/60 flex items-center justify-center animate-pulse">
            <Loader2 size={24} className="text-primary animate-spin" />
          </div>
          <div className="absolute -top-1 -right-1 w-4 h-4 bg-primary rounded-full animate-ping opacity-20" />
        </div>

        <div className="text-center space-y-1.5">
          <p className="text-[14px] font-bold text-foreground/90 tracking-tight">
            AI 인지 분석 시퀀스 가동
          </p>
          <p className="text-[11px] text-muted-foreground/60">
            {analyzeMessage || "장면의 맥락과 감정 선을 분석하는 중입니다."}
          </p>
        </div>

        <div style={{
          marginTop: "12px",
          width: "100%",
          maxHeight: "30%",
          overflow: "hidden",
          fontFamily: "monospace",
          fontSize: "11px",
          color: "#6b7280",
          lineHeight: "1.5",
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end"
        }}>
          {(analysisLogs ?? []).map((line, i) => (
            <div key={i} style={{whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{line}</div>
          ))}
        </div>

        <div className="w-full h-1.5 bg-secondary/40 rounded-full overflow-hidden shadow-inner">
          <div
            className="h-full bg-primary rounded-full transition-all duration-500 ease-out shadow-[0_0_10px_rgba(var(--primary),0.5)]"
            style={{ width: `${Math.min(analyzeProgress, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}
