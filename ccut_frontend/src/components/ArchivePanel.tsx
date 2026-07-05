import React, { useState, useEffect, useRef } from "react";
import { fetcher } from "@/services/api";
import { Search, Film, Calendar, Clock, RotateCcw, Box, ArrowRight, Play, Edit3, X, Check, Hash, ChevronDown, ChevronUp, Trash2, AlertTriangle, EyeOff } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { videoService } from "@/services/videoService";
import { sourceDisplayName } from "@/lib/fragmentIdentity";

interface SourceUsage {
  program_id: string;
  name: string | null;
  used_at: string | null;
  // [국장지시] 프로젝트 안에서의 원본 라벨(A,B..) — 배지 "Vega-A" 병기용
  label?: string;
}

interface Source {
  source_id: string;
  file_path: string;
  title: string;
  duration: number;
  fps: number;
  hash_value: string | null;
  created_at: string | null;
  program_names: string[];
  usage: SourceUsage[];
  play_url: string | null;
}

interface Program {
  program_id: string;
  name: string;
  status: string;
  created_at: string | null;
  last_updated_at: string | null;
  source_count: number;
  proposal_count?: number;
  export_count?: number;
  deleted_at?: string | null;
}

interface Proposal {
  proposal_id: string;
  source_id: string;
  // [DISPLAY-NAME] 백엔드 권위: "{프로젝트명} · {N}번째 제안 · {mode}안"
  display_name?: string;
  mode: string;
  duration: number;
  created_at: string | null;
  program_id?: string | null;
  program_name: string | null;
  program_name_inferred: boolean;
  program_deleted?: boolean;
}

interface ArchiveData {
  sources: Source[];
  programs: Program[];
  proposals: Proposal[];
}

interface ExportRecord {
  id: string;
  program_id: string | null;
  // [DISPLAY-NAME] 그 제안의 이름 상속: "{프로젝트명} · 첫 번째 제안 · A안"
  display_name?: string | null;
  program_title: string | null;
  proposal_id: string;
  output_url: string;
  file_size: number | null;
  duration: number | null;
  created_at: string | null;
  program_last_updated_at: string | null;
}

export const ArchivePanel: React.FC<{
  onNavigateToProject?: (id: string) => void;
  onRenameProject?: (id: string, newName: string) => void;
}> = ({ onNavigateToProject, onRenameProject }) => {
  const [data, setData] = useState<ArchiveData | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  // [국장지시] 원본 리스트 정렬 선택 — 최신순(기본) / 이름순
  const [srcSort, setSrcSort] = useState<"recent" | "name">("recent");
  const [activeSubTab, setActiveSubTab] = useState<"sources" | "programs" | "proposals" | "exports">("sources");
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [expandedSourceId, setExpandedSourceId] = useState<string | null>(null);
  const [expandedProgramId, setExpandedProgramId] = useState<string | null>(null);
  const [propPlayingId, setPropPlayingId] = useState<string | null>(null);
  const [propPreviewUrl, setPropPreviewUrl] = useState<string | null>(null);
  const [propLoading, setPropLoading] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // [SOURCE] 원본 재생/이름변경/삭제
  const [sourcePlayingId, setSourcePlayingId] = useState<string | null>(null);
  const [srcDelete, setSrcDelete] = useState<{ id: string; title: string } | null>(null);

  const handleRenameSource = async (s: Source, newName: string) => {
    const trimmed = newName.trim();
    setRenamingId(null);
    if (!trimmed || trimmed === s.title) return;
    setData(prev => prev ? {
      ...prev,
      sources: prev.sources.map(x => x.source_id === s.source_id ? { ...x, title: trimmed } : x),
    } : prev);
    try {
      await videoService.renameSource(s.source_id, trimmed);
    } catch (e) {
      console.error("[ArchivePanel] source rename failed:", e);
    }
  };

  const handleDeleteSource = async (mode: "source_only" | "full") => {
    if (!srcDelete) return;
    const id = srcDelete.id;
    setSrcDelete(null);
    try {
      await videoService.deleteSource(id, mode);
      await fetchArchive();
    } catch (e) {
      console.error("[ArchivePanel] source delete failed:", e);
    }
  };

  // [드릴다운 인라인 플레이] 이력 항목 클릭 -> 그 자리에서 바로 재생
  const [drillPlay, setDrillPlay] = useState<{ key: string; url: string | null; loading: boolean } | null>(null);

  const playSourceInline = (s: Source) => {
    if (drillPlay?.key === s.source_id) { setDrillPlay(null); return; }
    setDrillPlay({ key: s.source_id, url: s.play_url, loading: false });
  };
  const playExportInline = (ex: ExportRecord) => {
    if (drillPlay?.key === ex.id) { setDrillPlay(null); return; }
    setDrillPlay({ key: ex.id, url: ex.output_url, loading: false });
  };
  const playProposalInline = async (proposalId: string) => {
    if (drillPlay?.key === proposalId) { setDrillPlay(null); return; }
    setDrillPlay({ key: proposalId, url: null, loading: true });
    try {
      const res = await videoService.makeProposalPreview(proposalId);
      setDrillPlay({ key: proposalId, url: res.preview_url, loading: false });
    } catch (e) {
      console.error("[ArchivePanel] drill proposal preview failed:", e);
      setDrillPlay({ key: proposalId, url: null, loading: false });
    }
  };

  const drillVideoSrc = (url: string) =>
    url.startsWith("http") ? url : `${videoService.API_BASE_URL.replace("/api", "")}${url}`;

  // [PROPOSAL-PREVIEW] 제안 재생: 즉석 렌더(또는 캐시) 후 mp4 표시
  const handlePlayProposal = async (proposalId: string) => {
    if (propPlayingId === proposalId) {
      setPropPlayingId(null);
      setPropPreviewUrl(null);
      return;
    }
    setPropPlayingId(proposalId);
    setPropPreviewUrl(null);
    setPropLoading(true);
    try {
      const res = await videoService.makeProposalPreview(proposalId);
      if (res.preview_url) setPropPreviewUrl(res.preview_url);
    } catch (e) {
      console.error("[ArchivePanel] proposal preview failed:", e);
    } finally {
      setPropLoading(false);
    }
  };

  // [SOFT-DELETE] 프로젝트 복원
  const handleRestore = async (programId: string) => {
    try {
      await videoService.restoreProject(programId);
      await fetchArchive();
    } catch (e) {
      console.error("[ArchivePanel] restore failed:", e);
    }
  };

  // [작업4] 제안 -> 내보낸 영상 연결 맵 (proposal_id -> ExportRecord)
  const exportByProposal = React.useMemo(() => {
    const m = new Map<string, ExportRecord>();
    exports.forEach(ex => { if (ex.proposal_id) m.set(ex.proposal_id, ex); });
    return m;
  }, [exports]);

  const fetchArchive = async () => {
    setLoading(true);
    try {
      const [archiveRes, exportsRes] = await Promise.all([
        fetcher("/archive/list") as Promise<ArchiveData>,
        fetch(`${videoService.API_BASE_URL}/exports/list`).then(r => r.json()).catch(() => ({ exports: [] })),
      ]);
      setData(archiveRes);
      setExports(exportsRes.exports ?? []);
    } catch (e) {
      console.error("[ArchivePanel] Error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchArchive(); }, []);

  // [HOTFIX 국장보고] 검색 크래시 — 빈 검색어에선 || 단락으로 숨어 있다가 글자 입력 시
  // null 필드(.toLowerCase)에 도달해 화면 전체 소멸. 모든 필드 널가드 단일화.
  const _q = searchQuery.toLowerCase();
  const _has = (v?: string | null) => (v || "").toLowerCase().includes(_q);

  const filteredSources = data?.sources.filter(s =>
    _has(s.title) || _has(s.source_id) ||
    // [국장지시] 프로젝트명으로도 원본을 찾는다 ("Dahlia" 검색 → 그 프로젝트 소스들)
    s.program_names?.some(n => _has(n))
  ) || [];

  // [국장지시] 원본 리스트 정렬 선택 — 최신순(사용/생성 기준, 기본) / 이름순.
  // 백엔드 정렬과 무관하게 화면에서 확정 정렬(데이터 캐시·형식 차이에 면역).
  const srcLatest = (s: Source) => Math.max(
    ...(s.usage?.map(u => Date.parse(u.used_at || "") || 0) ?? [0]),
    Date.parse(s.created_at || "") || 0,
  );
  const sortedSources = [...filteredSources].sort((a, b) =>
    srcSort === "recent"
      ? srcLatest(b) - srcLatest(a)
      : sourceDisplayName(a.title).localeCompare(sourceDisplayName(b.title), "ko"));

  const filteredPrograms = data?.programs.filter(p =>
    _has(p.name) || _has(p.program_id)
  ) || [];

  const filteredProposals = data?.proposals.filter(pr =>
    _has(pr.display_name) || _has(pr.program_name) ||
    _has(pr.proposal_id) || _has(pr.source_id)
  ) || [];

  const formatSecs = (seconds?: number) => {
    if (!seconds) return "0초";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return mins > 0 ? `${mins}분 ${secs}초` : `${secs}초`;
  };

  const startRenameExport = (ex: ExportRecord) => {
    setRenamingId("ex_" + ex.id);
    setRenameValue(ex.program_title || "");
  };

  const startRenameProgram = (p: Program) => {
    setRenamingId("pg_" + p.program_id);
    setRenameValue(p.name || "");
  };

  const commitRenameExport = async (ex: ExportRecord) => {
    const trimmed = renameValue.trim();
    setRenamingId(null);
    if (!trimmed || !ex.program_id) return;
    setExports(prev => prev.map(e => e.id === ex.id ? { ...e, program_title: trimmed } : e));
    onRenameProject?.(ex.program_id, trimmed);
    await fetch(`${videoService.API_BASE_URL}/programs/${ex.program_id}/name`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: trimmed }),
    }).catch(e => console.error("[Archive rename export]", e));
  };

  const commitRenameProgram = async (p: Program) => {
    const trimmed = renameValue.trim();
    setRenamingId(null);
    if (!trimmed) return;
    setData(prev => prev ? {
      ...prev,
      programs: prev.programs.map(pg => pg.program_id === p.program_id ? { ...pg, name: trimmed } : pg),
    } : prev);
    onRenameProject?.(p.program_id, trimmed);
    await fetch(`${videoService.API_BASE_URL}/programs/${p.program_id}/name`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: trimmed }),
    }).catch(e => console.error("[Archive rename program]", e));
  };

  return (
    <div className="flex flex-col h-full bg-[hsl(228_10%_9%)] p-6 space-y-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent">
            CCUT 미디어 아카이브
          </h1>
          <p className="text-[12px] text-muted-foreground/60 mt-1">
            분석이 완료된 비디오 소스 및 이전 제안 이력을 관리합니다.
          </p>
        </div>
        <button
          onClick={fetchArchive}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/80 hover:bg-secondary text-xs text-foreground/80 transition-colors border border-border/20"
        >
          <RotateCcw size={12} />
          새로고침
        </button>
      </div>

      {/* Stats Board */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-card/30 border-border/20">
          <CardHeader className="p-4 flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground/60">분석된 원본 영상</CardTitle>
            <Film size={14} className="text-primary" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-xl font-bold text-foreground/90">{data?.sources.length ?? 0}개</div>
          </CardContent>
        </Card>
        <Card className="bg-card/30 border-border/20">
          <CardHeader className="p-4 flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground/60">생성된 프로그램 프로젝트</CardTitle>
            <Box size={14} className="text-primary" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-xl font-bold text-foreground/90">{data?.programs.length ?? 0}개</div>
          </CardContent>
        </Card>
        <Card className="bg-card/30 border-border/20">
          <CardHeader className="p-4 flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground/60">AI 편집 제안서 이력</CardTitle>
            <ArrowRight size={14} className="text-primary" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-xl font-bold text-foreground/90">{data?.proposals.length ?? 0}개</div>
          </CardContent>
        </Card>
      </div>

      {/* Search & Tabs */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-card/15 p-3 rounded-xl border border-border/10">
        <div className="flex items-center gap-1.5 bg-secondary/30 rounded-lg p-0.5">
          {(["sources", "programs", "proposals", "exports"] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveSubTab(tab)}
              className={`px-4 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeSubTab === tab ? "bg-primary/20 text-primary" : "text-muted-foreground/60 hover:text-foreground/80"
              }`}
            >
              {tab === "sources" ? "원본 리스트" : tab === "programs" ? "프로젝트 관리" : tab === "proposals" ? "AI 편집제안 이력" : "내보낸 영상"}
            </button>
          ))}
        </div>
        <div className="relative w-full md:w-72">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/40" />
          <Input
            placeholder="아카이브 내 검색..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-8 bg-secondary/30 border-border/10 text-xs focus-visible:ring-primary/40 rounded-lg"
          />
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 min-h-[300px]">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-64 text-muted-foreground/40 text-xs gap-2">
            <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            아카이브 데이터 로드 중...
          </div>
        ) : (
          <div className="space-y-3">

            {/* ── 내보낸 영상 탭 (SNS 카드 스타일) ── */}
            {activeSubTab === "exports" && (
              exports.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-64 gap-3 text-muted-foreground/30">
                  <Film size={36} strokeWidth={1} />
                  <p className="text-sm font-medium">아직 내보낸 영상이 없습니다</p>
                </div>
              ) : exports.map((ex, idx) => (
                <div
                  key={ex.id}
                  className="rounded-2xl border border-border/10 bg-card/20 overflow-hidden hover:border-border/20 transition-colors"
                >
                  <div className="flex items-center gap-4 p-5">
                    <div className="relative flex-shrink-0">
                      <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
                        <Film size={18} className="text-primary" />
                      </div>
                      <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-primary/80 text-[9px] font-black text-white flex items-center justify-center">
                        {idx + 1}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      {renamingId === "ex_" + ex.id ? (
                        <input
                          autoFocus
                          value={renameValue}
                          onChange={e => setRenameValue(e.target.value)}
                          onBlur={() => commitRenameExport(ex)}
                          onKeyDown={e => {
                            if (e.key === "Enter") commitRenameExport(ex);
                            if (e.key === "Escape") setRenamingId(null);
                          }}
                          className="w-full text-[15px] font-bold bg-secondary/40 border border-primary/40 rounded px-2 py-0.5 text-foreground/90 outline-none focus:border-primary"
                        />
                      ) : (
                        <button
                          onClick={() => startRenameExport(ex)}
                          title="클릭하여 이름 변경"
                          className="text-[15px] font-bold text-foreground/90 truncate max-w-full text-left hover:text-primary transition-colors"
                        >
                          {/* [DISPLAY-NAME] 제안 이름 상속 — 어느 제안에서 나온 영상인지 즉시 인식 */}
                          {ex.display_name || ex.program_title || "내보낸 영상"}
                        </button>
                      )}
                      <div className="flex items-center gap-3 mt-1 text-[11px] text-muted-foreground/50">
                        {ex.duration != null && <span className="flex items-center gap-1"><Clock size={10} />{formatSecs(ex.duration)}</span>}
                        {ex.file_size != null && <span>{(ex.file_size / 1024 / 1024).toFixed(1)} MB</span>}
                        {(ex.program_last_updated_at || ex.created_at) && <span className="flex items-center gap-1"><Calendar size={10} />{new Date(ex.program_last_updated_at || ex.created_at!).toLocaleString()}</span>}
                      </div>
                    </div>
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

                  <div className="flex items-center gap-2 px-5 pb-4 flex-wrap">
                    <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-400 text-[10px] font-semibold border border-emerald-500/20">
                      <Check size={9} />
                      아카이브 저장됨
                    </span>
                    <span className="text-[10px] text-muted-foreground/40">
                      SNS 업로드는 좌측 메뉴 “SNS 업로드”에서
                    </span>
                  </div>
                </div>
              ))
            )}

            {/* ── 원본 리스트 탭 ── */}
            {activeSubTab === "sources" && (
              <>
              {/* [국장지시] 정렬 선택 — 최신순(사용/생성 기준) / 이름순 */}
              <div className="flex items-center gap-1.5 mb-2">
                {([["recent", "최신순"], ["name", "이름순"]] as const).map(([v, l]) => (
                  <button key={v} onClick={() => setSrcSort(v)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-all ${srcSort === v ? "bg-primary/20 text-primary" : "bg-secondary/30 text-muted-foreground/60 hover:text-foreground/80"}`}>
                    {l}
                  </button>
                ))}
              </div>
              <div className="bg-card/20 rounded-xl border border-border/10 overflow-hidden divide-y divide-border/10">
                {sortedSources.length > 0 ? sortedSources.map(s => {
                  const usageCount = s.usage?.length ?? 0;
                  const isExpanded = expandedSourceId === s.source_id;
                  const shortHash = s.hash_value ? s.hash_value.slice(0, 8) : null;
                  return (
                  <div key={s.source_id} className="hover:bg-secondary/20 transition-colors">
                    <div className="p-4 flex items-center justify-between">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-10 h-10 flex-shrink-0 rounded-lg bg-primary/10 flex items-center justify-center">
                          <Film size={16} className="text-primary" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            {renamingId === "src_" + s.source_id ? (
                              <input
                                autoFocus
                                value={renameValue}
                                onChange={e => setRenameValue(e.target.value)}
                                onBlur={() => handleRenameSource(s, renameValue)}
                                onKeyDown={e => {
                                  if (e.key === "Enter") handleRenameSource(s, renameValue);
                                  if (e.key === "Escape") setRenamingId(null);
                                }}
                                className="text-sm font-semibold bg-secondary/40 border border-primary/40 rounded px-2 py-0.5 text-foreground/90 outline-none focus:border-primary"
                              />
                            ) : (
                              <button
                                onClick={() => { setRenameValue(s.title); setRenamingId("src_" + s.source_id); }}
                                title="클릭하여 이름 변경"
                                className="text-sm font-semibold text-foreground/90 text-left hover:text-primary transition-colors truncate"
                              >
                                {sourceDisplayName(s.title)}
                              </button>
                            )}
                            {!s.play_url && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-red-500/10 text-red-400 border border-red-500/20 flex-shrink-0">원본 삭제됨</span>
                            )}
                            {/* [국장지시] 배지 = 최신 사용 프로젝트부터 + "-라벨" 병기
                                ("Vega-A" = Vega 프로젝트 원본맵의 A) — 아카이브↔원본맵 연결 */}
                            {s.usage?.slice(0, 3).map(u => (
                              <span key={u.program_id} className="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20 flex-shrink-0">
                                {u.name}{u.label ? <span className="text-blue-400/60">-{u.label}</span> : null}
                              </span>
                            ))}
                            {s.usage && s.usage.length > 3 && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-blue-500/5 text-blue-400/70 flex-shrink-0">+{s.usage.length - 3}</span>
                            )}
                            {(!s.usage || s.usage.length === 0) && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-secondary/40 text-muted-foreground/40">미분류</span>
                            )}
                          </div>
                          <div className="flex items-center gap-2.5 text-[11px] text-muted-foreground/60 mt-1">
                            <span className="flex items-center gap-1"><Clock size={10} /> {formatSecs(s.duration)}</span>
                            <span>·</span>
                            <span>{s.fps} FPS</span>
                            {shortHash && (
                              <>
                                <span>·</span>
                                <span className="flex items-center gap-0.5 font-mono text-muted-foreground/45" title={`전체 해시: ${s.hash_value}`}>
                                  <Hash size={9} />{shortHash}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {s.play_url && (
                          <button
                            onClick={() => setSourcePlayingId(sourcePlayingId === s.source_id ? null : s.source_id)}
                            className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-[10px] font-semibold text-emerald-400 transition-colors"
                          >
                            {sourcePlayingId === s.source_id ? <X size={11} /> : <Play size={11} />}
                            {sourcePlayingId === s.source_id ? "닫기" : "재생"}
                          </button>
                        )}
                        {usageCount > 0 && (
                          <button
                            onClick={() => setExpandedSourceId(isExpanded ? null : s.source_id)}
                            className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-secondary/40 hover:bg-secondary/70 text-[10px] font-semibold text-foreground/60 transition-colors"
                          >
                            이력 {usageCount}
                            {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                          </button>
                        )}
                        <button
                          onClick={() => setSrcDelete({ id: s.source_id, title: s.title })}
                          className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-red-500/10 hover:bg-red-500/20 text-[10px] font-semibold text-red-400 transition-colors"
                        >
                          <Trash2 size={11} /> 삭제
                        </button>
                      </div>
                    </div>
                    {sourcePlayingId === s.source_id && s.play_url && (
                      <div className="px-4 pb-4 pl-[68px]">
                        <video
                          src={`${videoService.API_BASE_URL.replace("/api", "")}${s.play_url}`}
                          controls
                          autoPlay
                          className="w-[360px] max-w-full aspect-video rounded-lg bg-black"
                        />
                      </div>
                    )}
                    {isExpanded && usageCount > 0 && (
                      <div className="px-4 pb-3 pl-[68px] space-y-1.5">
                        {s.usage.map(u => (
                          <button
                            key={u.program_id}
                            onClick={() => onNavigateToProject?.(u.program_id)}
                            className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-secondary/20 hover:bg-secondary/40 transition-colors group"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Box size={12} className="text-blue-400 flex-shrink-0" />
                              <span className="text-xs font-medium text-foreground/80 truncate group-hover:text-primary transition-colors">{u.name || u.program_id}</span>
                            </div>
                            <span className="text-[10px] text-muted-foreground/40 flex items-center gap-1 flex-shrink-0">
                              {u.used_at && <><Calendar size={9} />{new Date(u.used_at).toLocaleString()}</>}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  );
                }) : (
                  <div className="p-8 text-center text-xs text-muted-foreground/40">검색 조건에 맞는 원본 영상이 없습니다.</div>
                )}
              </div>
              </>
            )}

            {/* ── 프로젝트 관리 탭 (드릴다운: 원본/제안/내보내기 + 복귀/복원) ── */}
            {activeSubTab === "programs" && (
              <div className="bg-card/20 rounded-xl border border-border/10 overflow-hidden divide-y divide-border/10">
                {filteredPrograms.length > 0 ? filteredPrograms.map(p => {
                  const isExp = expandedProgramId === p.program_id;
                  const isDeleted = !!p.deleted_at;
                  const daysLeft = p.deleted_at
                    ? Math.max(0, 30 - Math.floor((Date.now() - new Date(p.deleted_at).getTime()) / 86400000))
                    : null;
                  const projSources = data?.sources.filter(s => s.usage?.some(u => u.program_id === p.program_id)) ?? [];
                  const projProposals = data?.proposals.filter(pr => pr.program_id === p.program_id) ?? [];
                  const projExports = exports.filter(e => e.program_id === p.program_id);
                  return (
                  <div key={p.program_id} className={isDeleted ? "bg-red-500/[0.04]" : ""}>
                    <div className="p-4 hover:bg-secondary/20 transition-colors flex items-center justify-between">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${isDeleted ? "bg-red-500/10" : "bg-primary/10"}`}>
                          <Box size={16} className={isDeleted ? "text-red-400" : "text-primary"} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            {renamingId === "pg_" + p.program_id ? (
                              <input
                                autoFocus
                                value={renameValue}
                                onChange={e => setRenameValue(e.target.value)}
                                onBlur={() => commitRenameProgram(p)}
                                onKeyDown={e => {
                                  if (e.key === "Enter") commitRenameProgram(p);
                                  if (e.key === "Escape") setRenamingId(null);
                                }}
                                className="text-sm font-semibold bg-secondary/40 border border-primary/40 rounded px-2 py-0.5 text-foreground/90 outline-none focus:border-primary"
                              />
                            ) : (
                              <button
                                onClick={() => startRenameProgram(p)}
                                title="클릭하여 이름 변경"
                                className="text-sm font-semibold text-foreground/90 text-left hover:text-primary transition-colors"
                              >
                                {p.name || p.program_id}
                              </button>
                            )}
                            {isDeleted && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-red-500/15 text-red-400 border border-red-500/25">
                                🗑 삭제됨 · {daysLeft}일 후 영구삭제
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-[11px] text-muted-foreground/60 mt-1">
                            <span className="text-muted-foreground/60">원본 {p.source_count}</span>
                            <span>·</span>
                            <span className="text-muted-foreground/60">제안 {p.proposal_count ?? 0}</span>
                            <span>·</span>
                            <span className="text-muted-foreground/60">내보내기 {p.export_count ?? 0}</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {isDeleted ? (
                          <button
                            onClick={() => handleRestore(p.program_id)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-[11px] font-semibold text-emerald-400 transition-colors"
                          >
                            <RotateCcw size={11} /> 복원
                          </button>
                        ) : (
                          <button
                            onClick={() => onNavigateToProject?.(p.program_id)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-primary/15 hover:bg-primary/25 text-[11px] font-semibold text-primary transition-colors"
                          >
                            열기 <ArrowRight size={11} />
                          </button>
                        )}
                        <button
                          onClick={() => setExpandedProgramId(isExp ? null : p.program_id)}
                          className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-secondary/40 hover:bg-secondary/70 text-[10px] font-semibold text-foreground/60 transition-colors"
                        >
                          이력 {isExp ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                        </button>
                      </div>
                    </div>
                    {isExp && (
                      <div className="px-4 pb-4 pl-[68px] space-y-3 animate-in fade-in slide-in-from-top-1 duration-300">
                        {isDeleted && (
                          <div className="text-[11px] text-red-400/80 bg-red-500/5 border border-red-500/15 rounded-lg px-3 py-2">
                            이 프로젝트는 삭제되었습니다. <span className="font-semibold">{daysLeft}일</span> 안에 복원하지 않으면 모든 이력이 영구 삭제됩니다.
                          </div>
                        )}
                        {/* 원본 */}
                        <div>
                          <div className="text-[10px] font-bold text-muted-foreground/50 uppercase mb-1.5">원본 {projSources.length}</div>
                          <div className="space-y-1">
                            {projSources.length ? projSources.map(s => (
                              <div key={s.source_id}>
                                <button onClick={() => playSourceInline(s)}
                                  className="w-full flex items-center gap-2 text-[11px] text-foreground/70 px-2 py-1 rounded bg-secondary/15 hover:bg-secondary/40 hover:text-primary transition-colors text-left">
                                  {drillPlay?.key === s.source_id ? <X size={10} className="text-emerald-400 flex-shrink-0" /> : <Play size={10} className="text-blue-400 flex-shrink-0" />}
                                  <span className="truncate">{sourceDisplayName(s.title)}</span>
                                  <span className="text-muted-foreground/40 ml-auto flex-shrink-0">{formatSecs(s.duration)}</span>
                                </button>
                                {drillPlay?.key === s.source_id && (
                                  drillPlay.url
                                    ? <video src={drillVideoSrc(drillPlay.url)} controls autoPlay className="w-[320px] max-w-full aspect-video rounded-lg bg-black mt-1.5" />
                                    : <div className="text-[10px] text-muted-foreground/40 px-2 py-2">원본이 삭제되어 재생할 수 없습니다</div>
                                )}
                              </div>
                            )) : <div className="text-[11px] text-muted-foreground/30 px-2">없음</div>}
                          </div>
                        </div>
                        {/* 제안 */}
                        <div>
                          <div className="text-[10px] font-bold text-muted-foreground/50 uppercase mb-1.5">AI 편집제안 {projProposals.length}</div>
                          <div className="space-y-1">
                            {projProposals.length ? projProposals.slice(0, 8).map(pr => (
                              <div key={pr.proposal_id}>
                                <button onClick={() => playProposalInline(pr.proposal_id)}
                                  className="w-full flex items-center gap-2 text-[11px] text-foreground/70 px-2 py-1 rounded bg-secondary/15 hover:bg-secondary/40 hover:text-primary transition-colors text-left">
                                  {drillPlay?.key === pr.proposal_id
                                    ? (drillPlay.loading ? <RotateCcw size={10} className="animate-spin text-emerald-400 flex-shrink-0" /> : <X size={10} className="text-emerald-400 flex-shrink-0" />)
                                    : <Play size={10} className="text-primary flex-shrink-0" />}
                                  <span className="font-mono truncate">{pr.proposal_id}</span>
                                  <span className="text-muted-foreground/40 ml-auto flex-shrink-0">{pr.mode} · {formatSecs(pr.duration)}</span>
                                </button>
                                {drillPlay?.key === pr.proposal_id && (
                                  drillPlay.loading
                                    ? <div className="text-[10px] text-muted-foreground/50 px-2 py-2 animate-pulse">제안 영상 생성 중...</div>
                                    : drillPlay.url
                                      ? <video src={drillVideoSrc(drillPlay.url)} controls autoPlay className="w-[320px] max-w-full aspect-video rounded-lg bg-black mt-1.5" />
                                      : <div className="text-[10px] text-muted-foreground/40 px-2 py-2">재생할 조각이 없습니다</div>
                                )}
                              </div>
                            )) : <div className="text-[11px] text-muted-foreground/30 px-2">없음</div>}
                            {projProposals.length > 8 && <div className="text-[10px] text-muted-foreground/40 px-2">외 {projProposals.length - 8}개</div>}
                          </div>
                        </div>
                        {/* 내보내기 */}
                        <div>
                          <div className="text-[10px] font-bold text-muted-foreground/50 uppercase mb-1.5">내보낸 영상 {projExports.length}</div>
                          <div className="space-y-1">
                            {projExports.length ? projExports.map(ex => (
                              <div key={ex.id}>
                                <button onClick={() => playExportInline(ex)}
                                  className="w-full flex items-center gap-2 text-[11px] text-foreground/70 px-2 py-1 rounded bg-secondary/15 hover:bg-secondary/40 hover:text-primary transition-colors text-left">
                                  {drillPlay?.key === ex.id ? <X size={10} className="text-emerald-400 flex-shrink-0" /> : <Play size={10} className="text-emerald-400 flex-shrink-0" />}
                                  <span className="truncate">{ex.program_title || ex.id}</span>
                                  <span className="text-muted-foreground/40 ml-auto flex-shrink-0">{ex.created_at ? new Date(ex.created_at).toLocaleDateString() : ""}</span>
                                </button>
                                {drillPlay?.key === ex.id && drillPlay.url && (
                                  <video src={drillVideoSrc(drillPlay.url)} controls autoPlay className="w-[320px] max-w-full aspect-video rounded-lg bg-black mt-1.5" />
                                )}
                              </div>
                            )) : <div className="text-[11px] text-muted-foreground/30 px-2">없음</div>}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                  );
                }) : (
                  <div className="p-8 text-center text-xs text-muted-foreground/40">검색 조건에 맞는 프로젝트가 없습니다.</div>
                )}
              </div>
            )}

            {/* ── AI 편집제안 이력 탭 (프로젝트 귀속 + 플레이 + 복귀/복원) ── */}
            {activeSubTab === "proposals" && (
              <div className="bg-card/20 rounded-xl border border-border/10 overflow-hidden divide-y divide-border/10">
                {filteredProposals.length > 0 ? filteredProposals.map(pr => {
                  const linkedExport = exportByProposal.get(pr.proposal_id);
                  const isPlaying = propPlayingId === pr.proposal_id;
                  const isDeleted = !!pr.program_deleted;
                  const isLoadingThis = isPlaying && propLoading;
                  return (
                  <div key={pr.proposal_id} className={isDeleted ? "bg-red-500/[0.04]" : ""}>
                    <div className="p-4 hover:bg-secondary/20 transition-colors flex items-center justify-between">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`w-10 h-10 flex-shrink-0 rounded-lg flex items-center justify-center ${isDeleted ? "bg-red-500/10" : "bg-primary/10"}`}>
                          <ArrowRight size={16} className={isDeleted ? "text-red-400" : "text-primary"} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            {/* [DISPLAY-NAME] 주이름 = "{프로젝트명} · N번째 제안 · X안" — raw PROP_ id는 툴팁으로만 */}
                            <h4 className="text-[15px] font-bold text-foreground/90 truncate" title={pr.proposal_id}>
                              {pr.display_name || `${pr.program_name || "프로젝트 미상"} · ${pr.mode}안`}
                            </h4>
                            {pr.program_name ? (
                              <span
                                className={`px-1.5 py-0.5 rounded text-[9px] font-bold border flex-shrink-0 ${
                                  isDeleted
                                    ? "bg-red-500/10 text-red-400 border-red-500/20"
                                    : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                                }`}
                              >
                                {isDeleted ? "🗑 " : ""}{pr.program_name}
                              </span>
                            ) : (
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-secondary/40 text-muted-foreground/40 border border-border/10">레거시</span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-[11px] text-muted-foreground/60 mt-1">
                            <span className="bg-primary/10 text-primary px-1 py-0.5 rounded text-[9px] font-bold">{pr.mode} Mode</span>
                            <span>·</span>
                            <span>길이: {formatSecs(pr.duration)}</span>
                            {linkedExport && (
                              <>
                                <span>·</span>
                                <span className="text-emerald-400/70 text-[9px] font-bold">✓ 내보냄</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button
                          onClick={() => handlePlayProposal(pr.proposal_id)}
                          disabled={isLoadingThis}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-[11px] font-semibold text-emerald-400 transition-colors disabled:opacity-50"
                        >
                          {isLoadingThis ? <RotateCcw size={11} className="animate-spin" /> : isPlaying ? <X size={11} /> : <Play size={11} />}
                          {isLoadingThis ? "렌더 중" : isPlaying ? "닫기" : "재생"}
                        </button>
                        {isDeleted ? (
                          pr.program_id && (
                            <button
                              onClick={() => handleRestore(pr.program_id!)}
                              className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-[11px] font-semibold text-emerald-400 transition-colors"
                            >
                              <RotateCcw size={11} /> 복원
                            </button>
                          )
                        ) : pr.program_id ? (
                          <button
                            onClick={() => onNavigateToProject?.(pr.program_id!)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-primary/15 hover:bg-primary/25 text-[11px] font-semibold text-primary transition-colors"
                          >
                            열기 <ArrowRight size={11} />
                          </button>
                        ) : null}
                        {pr.created_at && (
                          <div className="text-[10px] text-muted-foreground/40 hidden sm:flex items-center gap-1">
                            <Calendar size={9} />
                            {new Date(pr.created_at).toLocaleDateString()}
                          </div>
                        )}
                      </div>
                    </div>
                    {isDeleted && (
                      <div className="px-4 pb-3 pl-[68px] text-[11px] text-red-400/80">
                        이 제안이 속한 프로젝트는 삭제되었습니다. <span className="font-semibold">복원</span>하면 다시 편집할 수 있습니다.
                      </div>
                    )}
                    {isPlaying && (
                      <div className="px-4 pb-4 pl-[68px]">
                        {isLoadingThis ? (
                          <div className="w-[360px] max-w-full aspect-video rounded-lg bg-black/60 flex flex-col items-center justify-center gap-2">
                            <RotateCcw size={20} className="animate-spin text-emerald-400" />
                            <span className="text-[11px] text-muted-foreground/60 animate-pulse">제안 영상 생성 중...</span>
                          </div>
                        ) : propPreviewUrl ? (
                          <video
                            src={`${videoService.API_BASE_URL}${propPreviewUrl}`}
                            controls
                            autoPlay
                            className="w-[360px] max-w-full aspect-video rounded-lg bg-black"
                          />
                        ) : (
                          <div className="w-[360px] max-w-full aspect-video rounded-lg bg-black/40 flex items-center justify-center">
                            <span className="text-[11px] text-muted-foreground/50">재생할 조각이 없습니다</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  );
                }) : (
                  <div className="p-8 text-center text-xs text-muted-foreground/40">검색 조건에 맞는 제안 이력이 없습니다.</div>
                )}
              </div>
            )}

          </div>
        )}
      </div>

      {/* [SOURCE] 원본 삭제 모달 (전체 / 원본만 선택) */}
      {srcDelete && (
        <div
          className="fixed inset-0 z-[500] flex items-center justify-center bg-black/70 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={() => setSrcDelete(null)}
        >
          <div
            className="w-[460px] max-w-[90vw] bg-[hsl(228,12%,11%)] border border-red-500/30 rounded-2xl shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 px-6 pt-6 pb-3">
              <div className="w-11 h-11 rounded-xl bg-red-500/15 flex items-center justify-center flex-shrink-0">
                <AlertTriangle size={22} className="text-red-400" />
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-foreground">원본을 삭제하시겠습니까?</h3>
                <p className="text-[12px] text-red-400/80 truncate max-w-[320px]">“{sourceDisplayName(srcDelete.title)}”</p>
              </div>
            </div>

            <div className="px-6 pb-2 space-y-2.5">
              <button
                onClick={() => handleDeleteSource("source_only")}
                className="w-full text-left p-3 rounded-xl bg-amber-500/5 border border-amber-500/20 hover:bg-amber-500/10 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <EyeOff size={14} className="text-amber-400" />
                  <span className="text-[13px] font-bold text-amber-300">원본 파일만 삭제 (권장)</span>
                </div>
                <p className="text-[11px] text-muted-foreground/70 leading-relaxed">
                  노출되면 안 되는 영상일 때. 원본 mp4는 디스크에서 사라지지만,
                  <span className="text-foreground/80"> 편집에 사용한 조각·편집본은 그대로 남습니다.</span>
                </p>
              </button>

              <button
                onClick={() => handleDeleteSource("full")}
                className="w-full text-left p-3 rounded-xl bg-red-500/5 border border-red-500/20 hover:bg-red-500/10 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <Trash2 size={14} className="text-red-400" />
                  <span className="text-[13px] font-bold text-red-300">전체 삭제</span>
                </div>
                <p className="text-[11px] text-muted-foreground/70 leading-relaxed">
                  원본 파일 + 이 영상에서 만든 <span className="text-foreground/80">모든 조각·분석 데이터</span>를
                  완전히 제거합니다. 되돌릴 수 없습니다.
                </p>
              </button>
            </div>

            <div className="px-6 py-4">
              <button
                onClick={() => setSrcDelete(null)}
                className="w-full py-2.5 rounded-xl bg-secondary/60 text-foreground/90 text-[13px] font-medium hover:bg-secondary transition-colors"
              >
                취소 (안전)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
