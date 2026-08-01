import React, { useRef } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Film } from "lucide-react";
import { videoService } from "@/services/videoService";

// [아카이브 작업대 2026-07-06] 조각 구간 미리보기 모달.
// video_url(원본) + start/end로 해당 구간만 재생. 전체 원본 hover 재생 금지.
// 재생 불가(파일 없음)면 검은 화면 대신 정직한 안내.

export interface PreviewItem {
  fragment_id: string;
  display_name: string | null;
  video_url: string | null;
  start: number | null;
  end: number | null;
  source_title?: string | null;
}

const abs = (url: string) =>
  url.startsWith("http") ? url : `${videoService.API_BASE_URL.replace("/api", "")}${url}`;

const fmt = (sec: number | null) => {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

export const ArchivePreviewModal: React.FC<{
  item: PreviewItem | null;
  onClose: () => void;
}> = ({ item, onClose }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const onLoaded = () => {
    const v = videoRef.current;
    if (v && item?.start != null) { try { v.currentTime = item.start; } catch { /* noop */ } }
  };
  // 구간 끝에서 멈춤 — 전체 원본으로 흘러가지 않게
  const onTime = () => {
    const v = videoRef.current;
    if (v && item?.end != null && v.currentTime >= item.end) v.pause();
  };

  return (
    <Dialog open={!!item} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-xl p-0 gap-0 bg-[hsl(228,12%,11%)] border-border/20 overflow-hidden">
        <div className="px-4 py-3 border-b border-border/10">
          <DialogTitle className="text-sm font-bold text-foreground/90 truncate">{item?.display_name || item?.fragment_id || "미리보기"}</DialogTitle>
          <p className="text-[11px] text-muted-foreground/76">
            {item?.source_title ? `${item.source_title} · ` : ""}{fmt(item?.start ?? null)}–{fmt(item?.end ?? null)} 구간
          </p>
        </div>
        <div className="bg-black aspect-video flex items-center justify-center">
          {item?.video_url ? (
            <video
              key={item.fragment_id}
              ref={videoRef}
              src={abs(item.video_url)}
              controls
              autoPlay
              onLoadedMetadata={onLoaded}
              onTimeUpdate={onTime}
              className="w-full h-full"
            />
          ) : (
            <div className="flex flex-col items-center gap-2 text-muted-foreground/76">
              <Film size={32} strokeWidth={1} />
              <p className="text-xs">원본 파일이 없어 재생할 수 없습니다.</p>
              <p className="text-[10px] text-muted-foreground/70">원본이 삭제됐거나 업로드 경로에 없습니다.</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
