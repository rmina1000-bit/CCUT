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

// [SNS 현실 조사 2026-07] 개인 PC에서 지금 실제로 열리는 통로와 조건
const PLATFORM_INFO: Record<string, string> = {
  tiktok: "TikTok은 developers.tiktok.com에서 개발자 앱 등록과 심사를 통과해야 하고, 심사 전에는 업로드해도 '나만 보기'로 강제됩니다. 심사를 통과하면 이 버튼이 살아납니다.",
  instagram: "Instagram은 ①비즈니스 계정 전환 ②Meta 개발자 앱 심사(2~4주) ③영상이 공개 인터넷 주소에 있어야 함(내 PC 파일 불가) — 세 조건이 필요해 개인 PC 단독으로는 아직 불가능합니다.",
};

export const SnsUploadPanel: React.FC<{
  onNavigateToProject?: (id: string) => void;
  onRenameProject?: (id: string, newName: string) => void;
}> = ({ onNavigateToProject, onRenameProject }) => {
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  // [SNS-YT] 실업로드 상태
  const [yt, setYt] = useState<{ configured: boolean; connected: boolean; channel_title: string | null; client_secret_path?: string } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [uploadTarget, setUploadTarget] = useState<ExportRecord | null>(null);
  const [upTitle, setUpTitle] = useState("");
  const [upPrivacy, setUpPrivacy] = useState<"private" | "unlisted" | "public">("private");
  const [uploading, setUploading] = useState(false);
  const [uploadDone, setUploadDone] = useState<Record<string, string>>({});
  const [infoKey, setInfoKey] = useState<string | null>(null);

  const fetchYt = async () => {
    try { setYt(await fetch("/api/sns/youtube/status").then((r) => r.json())); } catch { setYt(null); }
  };
  useEffect(() => { fetchYt(); }, []);

  const connectYt = async () => {
    setConnecting(true);
    try {
      const r = await fetch("/api/sns/youtube/connect", { method: "POST" }).then((x) => x.json());
      if (r?.status === "OK") setYt((prev) => ({ ...(prev ?? { configured: true }), ...r } as any));
      else alert(r?.message || "연결 실패");
    } catch { alert("연결 중 오류 — 브라우저 로그인 창을 닫으셨나요?"); }
    setConnecting(false);
    fetchYt();
  };

  const doUpload = async () => {
    if (!uploadTarget) return;
    setUploading(true);
    try {
      const r = await fetch("/api/sns/youtube/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ export_id: uploadTarget.id, title: upTitle.trim() || "CCUT 편집 영상", privacy: upPrivacy }),
      }).then((x) => x.json());
      if (r?.status === "OK") {
        setUploadDone((prev) => ({ ...prev, [uploadTarget.id]: r.url }));
        setUploadTarget(null);
      } else {
        alert(r?.message || "업로드 실패");
      }
    } catch (e) { alert("업로드 중 오류가 났습니다."); }
    setUploading(false);
  };

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

      {/* [SNS-YT] 채널 연결 카드 */}
      <div className="px-8 pb-4 flex-shrink-0">
        <div className="rounded-xl border border-border/15 bg-card/20 px-5 py-4">
          <div className="flex items-center gap-3">
            <Youtube size={20} className="text-red-500 flex-shrink-0" />
            {yt?.connected ? (
              <>
                <span className="text-[13px] text-foreground flex-1"><b>{yt.channel_title}</b> 채널이 연결되어 있습니다. 아래 영상의 YouTube 버튼으로 바로 올릴 수 있어요.</span>
                <button onClick={async () => { await fetch("/api/sns/youtube/connect", { method: "DELETE" }); fetchYt(); }}
                  className="text-[11px] text-muted-foreground/60 hover:text-foreground px-2 py-1">연결 해제</button>
              </>
            ) : yt?.configured ? (
              <>
                <span className="text-[13px] text-foreground/80 flex-1">준비 완료 — 채널을 연결하면 업로드가 열립니다. (구글 로그인 창이 뜹니다)</span>
                <button onClick={connectYt} disabled={connecting}
                  className="px-3 py-1.5 rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500 hover:text-white text-[12px] font-bold transition-all disabled:opacity-50">
                  {connecting ? "브라우저에서 로그인하세요…" : "YouTube 채널 연결"}
                </button>
              </>
            ) : (
              <div className="flex-1 text-[12px] text-muted-foreground/70 leading-relaxed">
                <b className="text-foreground/90">YouTube 업로드 준비 (1회, 약 10분):</b>
                <span> ① console.cloud.google.com에서 프로젝트 생성 → YouTube Data API v3 사용 설정 ② OAuth 동의화면(외부·테스트)에 본인 이메일 추가 ③ 사용자 인증 정보 → OAuth 클라이언트 ID(<b>데스크톱 앱</b>) 만들고 JSON 다운로드 ④ 그 파일을 </span>
                <code className="text-primary/90 bg-black/30 px-1 rounded text-[11px]">{yt?.client_secret_path ?? "runtime\\sns\\client_secret.json"}</code>
                <span> 에 저장 → 새로고침. 무료로 하루 최대 100개까지 올릴 수 있습니다.</span>
              </div>
            )}
          </div>
        </div>
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
                  {uploadDone[ex.id] && (
                    <a href={uploadDone[ex.id]} target="_blank" rel="noreferrer"
                       className="flex items-center gap-1 px-2 py-1 rounded-md bg-red-500/10 text-red-400 text-[10px] font-semibold border border-red-500/20 hover:bg-red-500/20">
                      <Youtube size={10} /> 업로드됨 — 열기
                    </a>
                  )}
                  {PLATFORMS.map(({ key, label, icon: Icon, color }) => {
                    const isYt = key === "youtube";
                    const enabled = isYt && !!yt?.connected;
                    return (
                      <div key={key} className="relative">
                        <button
                          title={enabled ? "YouTube에 업로드" : isYt ? "먼저 위에서 채널을 연결하세요" : "클릭해서 준비 조건 보기"}
                          onClick={() => {
                            if (enabled) {
                              setUploadTarget(ex);
                              setUpTitle(ex.program_title || "CCUT 편집 영상");
                              setUpPrivacy("private");
                            } else if (!isYt) {
                              setInfoKey(infoKey === `${key}_${ex.id}` ? null : `${key}_${ex.id}`);
                            }
                          }}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${color} ${enabled ? "" : isYt ? "opacity-50" : "opacity-70"}`}
                        >
                          <Icon size={12} />
                          {label}
                        </button>
                        {infoKey === `${key}_${ex.id}` && PLATFORM_INFO[key] && (
                          <div className="absolute bottom-full mb-2 left-0 z-50 w-[300px] p-3 rounded-lg bg-[hsl(228,12%,12%)] border border-border/30 shadow-xl text-[11px] text-foreground/80 leading-relaxed">
                            {PLATFORM_INFO[key]}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* [SNS-YT] 업로드 다이얼로그 (인라인) */}
                {uploadTarget?.id === ex.id && (
                  <div className="mx-5 mb-4 rounded-xl border border-red-500/20 bg-red-500/5 p-4 space-y-3">
                    <p className="text-[12px] font-bold text-foreground">YouTube에 올리기</p>
                    <input
                      value={upTitle}
                      onChange={(e) => setUpTitle(e.target.value)}
                      placeholder="영상 제목"
                      className="w-full bg-black/30 border border-white/10 rounded-md px-3 py-2 text-[13px] text-foreground outline-none focus:border-red-500/40"
                    />
                    <div className="flex items-center gap-2">
                      {([["private", "비공개 (나만 보기)"], ["unlisted", "일부공개 (링크로만)"], ["public", "공개"]] as const).map(([v, l]) => (
                        <button key={v} onClick={() => setUpPrivacy(v)}
                          className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${upPrivacy === v ? "bg-red-500 text-white" : "bg-secondary/40 text-muted-foreground hover:text-foreground"}`}>
                          {l}
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 justify-end">
                      <button onClick={() => setUploadTarget(null)} disabled={uploading}
                        className="px-3 py-1.5 text-[12px] text-muted-foreground hover:text-foreground">취소</button>
                      <button onClick={doUpload} disabled={uploading || !upTitle.trim()}
                        className="px-4 py-1.5 rounded-lg bg-red-500 text-white text-[12px] font-bold hover:bg-red-600 disabled:opacity-50 transition-all">
                        {uploading ? "업로드 중… (영상 크기에 따라 수십 초)" : "지금 업로드"}
                      </button>
                    </div>
                    <p className="text-[10px] text-muted-foreground/50">처음엔 비공개로 올려서 확인한 뒤 YouTube 스튜디오에서 공개로 바꾸는 걸 권합니다.</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
