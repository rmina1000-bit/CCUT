import React, { useState, useEffect } from "react";
import { RotateCcw, Film, Clock, Calendar, Play, Edit3, X, Youtube, Tv2, Instagram, Check } from "lucide-react";
import { videoService } from "@/services/videoService";

interface ExportRecord {
  id: string;
  program_id: string | null;
  program_title: string | null;
  output_url: string;
  file_size: number | null;
  duration: number | null;
  created_at: string | null;
  program_last_updated_at: string | null;
}

const formatSecs = (s?: number | null) => {
  if (!s) return "0초";
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return m > 0 ? `${m}분 ${sec}초` : `${sec}초`;
};

const PLATFORMS = [
  { key: "youtube", label: "YouTube Shorts", icon: Youtube, color: "text-red-500 bg-red-500/10 hover:bg-red-500/20 border-red-500/20" },
  { key: "tiktok",  label: "TikTok",         icon: Tv2,     color: "text-pink-400 bg-pink-500/10 hover:bg-pink-500/20 border-pink-500/20" },
  { key: "instagram", label: "Instagram",    icon: Instagram, color: "text-purple-400 bg-purple-500/10 hover:bg-purple-500/20 border-purple-500/20" },
];

export const SnsUploadPanel: React.FC<{
  onNavigateToProject?: (id: string) => void;
  onRenameProject?: (id: string, newName: string) => void;
}> = ({ onNavigateToProject, onRenameProject }) => {
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const fetchExports = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${videoService.API_BASE_URL}/exports/list`).then(r => r.json()).catch(() => ({ exports: [] }));
      setExports(res.exports ?? []);
    } catch {
      setExports([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchExports(); }, []);

  const startRename = (ex: ExportRecord) => {
    setRenamingId(ex.id);
    setRenameValue(ex.program_title || "");
  };

  const commitRename = async (ex: ExportRecord) => {
    const trimmed = renameValue.trim();
    if (!trimmed || !ex.program_id) { setRenamingId(null); return; }
    setExports(prev => prev.map(e => e.id === ex.id ? { ...e, program_title: trimmed } : e));
    setRenamingId(null);
    onRenameProject?.(ex.program_id, trimmed);
    await fetch(`${videoService.API_BASE_URL}/programs/${ex.program_id}/name`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: trimmed }),
    }).catch(e => console.error("[SNS rename]", e));
  };

  return (
    <div className="flex flex-col h-full bg-[hsl(228_10%_9%)] overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-8 pt-8 pb-4 flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent">
            SNS 업로드
          </h1>
          <p className="text-[12px] text-muted-foreground/50 mt-1">
            편집 완료된 영상을 채널로 발행하세요.
          </p>
        </div>
        <button
          onClick={fetchExports}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/80 hover:bg-secondary text-xs text-foreground/80 transition-colors border border-border/20"
        >
          <RotateCcw size={12} />
          새로고침
        </button>
      </div>

      {/* 내보낸 영상 목록 */}
      <div className="flex-1 px-8 pb-8">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-64 gap-3 text-muted-foreground/40">
            <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-xs">불러오는 중...</span>
          </div>
        ) : exports.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 gap-3 text-muted-foreground/30">
            <Film size={36} strokeWidth={1} />
            <p className="text-sm font-medium">아직 내보낸 영상이 없습니다</p>
            <p className="text-xs">프로젝트에서 A안 또는 B안을 내보내면 여기에 나타납니다.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {exports.map((ex, idx) => (
              <div
                key={ex.id}
                className="rounded-2xl border border-border/10 bg-card/20 overflow-hidden hover:border-border/20 transition-colors"
              >
                {/* 항목 헤더 */}
                <div className="flex items-center gap-4 p-5">
                  {/* 인덱스 + 아이콘 */}
                  <div className="relative flex-shrink-0">
                    <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
                      <Film size={18} className="text-primary" />
                    </div>
                    <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-primary/80 text-[9px] font-black text-white flex items-center justify-center">
                      {idx + 1}
                    </span>
                  </div>

                  {/* 정보 */}
                  <div className="flex-1 min-w-0">
                    {renamingId === ex.id ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={e => setRenameValue(e.target.value)}
                        onBlur={() => commitRename(ex)}
                        onKeyDown={e => {
                          if (e.key === "Enter") commitRename(ex);
                          if (e.key === "Escape") setRenamingId(null);
                        }}
                        className="w-full text-[15px] font-bold bg-secondary/40 border border-primary/40 rounded px-2 py-0.5 text-foreground/90 outline-none focus:border-primary"
                      />
                    ) : (
                      <button
                        onClick={() => startRename(ex)}
                        title="클릭하여 이름 변경"
                        className="text-[15px] font-bold text-foreground/90 truncate max-w-full text-left hover:text-primary transition-colors"
                      >
                        {ex.program_title || ex.program_id || "프로젝트"}
                      </button>
                    )}
                    <div className="flex items-center gap-3 mt-1 text-[11px] text-muted-foreground/50">
                      {ex.duration != null && (
                        <span className="flex items-center gap-1">
                          <Clock size={10} />
                          {formatSecs(ex.duration)}
                        </span>
                      )}
                      {ex.file_size != null && (
                        <span>{(ex.file_size / 1024 / 1024).toFixed(1)} MB</span>
                      )}
                      {(ex.program_last_updated_at || ex.created_at) && (
                        <span className="flex items-center gap-1">
                          <Calendar size={10} />
                          {new Date(ex.program_last_updated_at || ex.created_at!).toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 액션 버튼들 */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => setPlayingId(playingId === ex.id ? null : ex.id)}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-secondary/60 hover:bg-secondary text-xs font-medium transition-colors"
                    >
                      {playingId === ex.id ? <X size={13} /> : <Play size={13} />}
                      {playingId === ex.id ? "닫기" : "재생"}
                    </button>
                    {ex.program_id && (
                      <button
                        onClick={() => onNavigateToProject?.(ex.program_id!)}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-foreground/70 text-xs font-medium transition-colors border border-border/15"
                      >
                        <Edit3 size={13} />
                        다시 편집
                      </button>
                    )}
                  </div>
                </div>

                {/* 인라인 플레이어 (컴팩트) */}
                {playingId === ex.id && (
                  <div className="mx-5 mb-3 rounded-xl overflow-hidden bg-black w-[360px] aspect-video">
                    <video
                      src={`${videoService.API_BASE_URL.replace("/api", "")}${ex.output_url}`}
                      controls
                      autoPlay
                      className="w-full h-full"
                    />
                  </div>
                )}

                {/* 하단: 저장 배지 + 플랫폼 버튼 */}
                <div className="flex items-center gap-2 px-5 pb-4 flex-wrap">
                  <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-400 text-[10px] font-semibold border border-emerald-500/20">
                    <Check size={9} />
                    아카이브 저장됨
                  </span>
                  {PLATFORMS.map(({ key, label, icon: Icon, color }) => (
                    <button
                      key={key}
                      title="연동 준비 중"
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border opacity-50 cursor-not-allowed transition-colors ${color}`}
                    >
                      <Icon size={12} />
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
