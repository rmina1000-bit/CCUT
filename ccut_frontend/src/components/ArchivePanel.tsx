import React, { useState, useEffect, useRef } from "react";
import { fetcher } from "@/services/api";
import { Search, Film, Calendar, Clock, RotateCcw, Box, ArrowRight, Play, Edit3, X, Check, Hash, ChevronDown, ChevronUp, Trash2, AlertTriangle, EyeOff } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { videoService } from "@/services/videoService";
import { sourceDisplayName } from "@/lib/fragmentIdentity";
import { SingleFragmentEditor } from "@/components/SingleFragmentEditor";
import { ArchiveWorkbench } from "@/components/ArchiveWorkbench";
import { AppDialog } from "@/components/AppDialog";

// [Archive 단계B] hydrate 분리 — /archive/list 대형 응답 폐지.
// summary(경량) + sources(페이징) + source 상세(lazy) + timeline(day 페이징)로 분리.

interface ArchiveSummary {
  source_count: number;
  program_count: number;
  latest_shot_date: string | null;
  recent_source_ids: string[];
}

interface SourceCard {
  source_id: string;
  title: string;
  shot_date: string | null;
  shot_date_fallback: boolean;
  created_at: string | null;
  duration: number | null;
  thumbnail_url: string | null;
  fragment_count: number;
}

interface SourceUsage {
  program_id: string;
  name: string | null;
  used_at: string | null;
  label?: string;
  deleted_at?: string | null;
}

interface SourceNote {
  note_id: number;
  text: string;
  origin: string;
  said_at: string;
}

interface SourceDetail {
  source_id: string;
  title: string;
  duration: number | null;
  fps: number | null;
  hash_value: string | null;
  created_at: string | null;
  shot_date: string | null;
  shot_date_fallback: boolean;
  play_url: string | null;
  notes: SourceNote[];
  usage: SourceUsage[];
  exports: { id: string; program_id: string | null; display_name: string | null; output_url: string; status: string; created_at: string | null }[];
  fragment_count: number;
  adopted_events: number;
  edited_events: number;
  exported_events: number;
  fragments: any[];
}

interface TimelineDay {
  date_key: string;
  source_count: number;
  thumbnail_url: string | null;
  has_fallback: boolean;
}

interface ExportRecord {
  id: string;
  program_id: string | null;
  display_name?: string | null;
  program_title: string | null;
  proposal_id: string;
  output_url: string;
  file_size: number | null;
  duration: number | null;
  created_at: string | null;   // [LAB-20] 이 행의 시각은 산출물 생성시각 하나뿐이다
  thumbnail_url?: string | null;
}

const videoSrc = (url: string) =>
  url.startsWith("http") ? url : `${videoService.API_BASE_URL.replace("/api", "")}${url}`;

const formatSecs = (seconds?: number | null) => {
  if (!seconds) return "0초";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return mins > 0 ? `${mins}분 ${secs}초` : `${secs}초`;
};

export const ArchivePanel: React.FC<{
  onNavigateToProject?: (id: string, reEdit?: boolean) => void;
  onRenameProject?: (id: string, newName: string) => void;
}> = ({ onNavigateToProject, onRenameProject }) => {
  const [summary, setSummary] = useState<ArchiveSummary | null>(null);
  const [sourceCards, setSourceCards] = useState<SourceCard[]>([]);
  const [sourcesCursor, setSourcesCursor] = useState<string | null>(null);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [sourcesLoadingMore, setSourcesLoadingMore] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [srcSort, setSrcSort] = useState<"shot_date_desc" | "created_desc">("shot_date_desc");

  // [상세 lazy hydrate] source_id → 상세(note/usage/export/조각 이력), 클릭 시에만 조회
  const [detailCache, setDetailCache] = useState<Record<string, SourceDetail>>({});
  const [detailLoading, setDetailLoading] = useState<Record<string, boolean>>({});

  const [viewerFrag, setViewerFrag] = useState<any | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [creatingFor, setCreatingFor] = useState<string | null>(null);
  const createProjectFromSource = async (sourceId: string) => {
    if (creatingFor) return;
    setCreatingFor(sourceId);
    try {
      const r = await videoService.createProject(undefined, [sourceId]);
      if (r?.program_id) onNavigateToProject?.(r.program_id);
    } catch (e) {
      console.warn("[NEW-PROJECT] 생성 실패:", e);
    } finally {
      setCreatingFor(null);
    }
  };

  const fetchSourceDetail = async (sid: string): Promise<SourceDetail | null> => {
    if (detailCache[sid]) return detailCache[sid];
    setDetailLoading(prev => ({ ...prev, [sid]: true }));
    try {
      const r = await fetcher(`/archive/source/${encodeURIComponent(sid)}`) as SourceDetail;
      setDetailCache(prev => ({ ...prev, [sid]: r }));
      return r;
    } catch (e) {
      console.warn("[SOURCE-DETAIL] 조회 실패:", e);
      return null;
    } finally {
      setDetailLoading(prev => ({ ...prev, [sid]: false }));
    }
  };

  // [국장지시 2026-07-05] 프로젝트/제안은 과정(process) — 사용자가 프로젝트를 지우면 함께 사라진다.
  // 아카이브는 결과(원본·조각·내보낸 영상)만 남기는 곳이므로 "프로젝트 관리"/"AI 편집제안 이력" 탭은 폐지.
  // [국장지시 2026-07-06] 작업대가 아카이브 기본 경험 — 진입 즉시 작업대.
  const [activeSubTab, setActiveSubTab] = useState<"workbench" | "sources" | "timeline" | "exports">("workbench");

  // [exports] 첫 진입 필수 아님 — exports 탭 클릭 시에만 lazy 조회
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [exportsLoaded, setExportsLoaded] = useState(false);
  const [exportsLoading, setExportsLoading] = useState(false);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ExportRecord | null>(null);
  const [deleteNotice, setDeleteNotice] = useState<string | null>(null);

  /** [LAB-25] 산출물 1건을 휴지통으로 보낸다. 파일은 storage/trash 에 남는다.
   *  대화상자는 브라우저 기본창이 아니라 AppDialog 를 쓴다(앱 디자인 일관성). */
  const runDeleteExport = async (ex: ExportRecord) => {
    setDeletingId(ex.id);
    try {
      const res = await fetch(`${videoService.API_BASE_URL}/exports/${encodeURIComponent(ex.id)}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setExports(prev => prev.filter(e => e.id !== ex.id));
      if (playingId === ex.id) setPlayingId(null);
    } catch (e) {
      console.error("산출물 삭제 실패:", e);
      setDeleteNotice("삭제하지 못했습니다. 로그를 확인해 주세요.");
    } finally {
      setDeletingId(null);
    }
  };
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [expandedSourceId, setExpandedSourceId] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const [sourcePlayingId, setSourcePlayingId] = useState<string | null>(null);
  const [srcDelete, setSrcDelete] = useState<{ id: string; title: string } | null>(null);

  // [연대기] 날짜 묶음 페이징 + day 상세
  const [timelineDays, setTimelineDays] = useState<TimelineDay[]>([]);
  const [timelineCursor, setTimelineCursor] = useState<string | null>(null);
  const [timelineLoaded, setTimelineLoaded] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [dayDetail, setDayDetail] = useState<{ date_key: string; sources: SourceCard[] } | null>(null);
  const [dayLoading, setDayLoading] = useState(false);

  const handleRenameSource = async (s: SourceCard, newName: string) => {
    const trimmed = newName.trim();
    setRenamingId(null);
    if (!trimmed || trimmed === s.title) return;
    setSourceCards(prev => prev.map(x => x.source_id === s.source_id ? { ...x, title: trimmed } : x));
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
      setSourceCards(prev => prev.filter(s => s.source_id !== id));
    } catch (e) {
      console.error("[ArchivePanel] source delete failed:", e);
    }
  };

  const [drillPlay, setDrillPlay] = useState<{ key: string; url: string | null; loading: boolean } | null>(null);

  const playExportInline = (ex: ExportRecord) => {
    if (drillPlay?.key === ex.id) { setDrillPlay(null); return; }
    setDrillPlay({ key: ex.id, url: ex.output_url, loading: false });
  };

  const fetchSummary = async () => {
    try {
      const r = await fetcher("/archive/summary") as ArchiveSummary;
      setSummary(r);
    } catch (e) {
      console.error("[ArchivePanel] summary error:", e);
    }
  };

  const fetchSourcesPage = async (reset: boolean) => {
    if (reset) setSourcesLoading(true); else setSourcesLoadingMore(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "20");
      params.set("sort", srcSort);
      if (searchQuery.trim()) params.set("q", searchQuery.trim());
      if (!reset && sourcesCursor) params.set("cursor", sourcesCursor);
      const r = await fetcher(`/archive/sources?${params.toString()}`) as { sources: SourceCard[]; next_cursor: string | null };
      setSourceCards(prev => reset ? r.sources : [...prev, ...r.sources]);
      setSourcesCursor(r.next_cursor);
    } catch (e) {
      console.error("[ArchivePanel] sources error:", e);
    } finally {
      setSourcesLoading(false);
      setSourcesLoadingMore(false);
    }
  };

  const fetchExports = async () => {
    setExportsLoading(true);
    try {
      const r = await fetch(`${videoService.API_BASE_URL}/exports/list`).then(r => r.json()).catch(() => ({ exports: [] }));
      setExports(r.exports ?? []);
    } finally {
      setExportsLoading(false);
      setExportsLoaded(true);
    }
  };

  const fetchTimelineDays = async (reset: boolean) => {
    setTimelineLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "20");
      if (!reset && timelineCursor) params.set("before", timelineCursor);
      const r = await fetcher(`/archive/timeline/days?${params.toString()}`) as { days: TimelineDay[]; next_cursor: string | null };
      setTimelineDays(prev => reset ? r.days : [...prev, ...r.days]);
      setTimelineCursor(r.next_cursor);
    } catch (e) {
      console.error("[ArchivePanel] timeline days error:", e);
    } finally {
      setTimelineLoading(false);
      setTimelineLoaded(true);
    }
  };

  const openDay = async (dateKey: string) => {
    if (selectedDay === dateKey) { setSelectedDay(null); setDayDetail(null); return; }
    setSelectedDay(dateKey);
    setDayLoading(true);
    try {
      const r = await fetcher(`/archive/timeline/day/${encodeURIComponent(dateKey)}`) as { date_key: string; sources: SourceCard[] };
      setDayDetail(r);
    } catch (e) {
      console.error("[ArchivePanel] timeline day error:", e);
    } finally {
      setDayLoading(false);
    }
  };

  // [마운트] summary + sources 첫 페이지만 — /archive/list, /exports/list 전량 fetch 제거
  useEffect(() => { fetchSummary(); fetchSourcesPage(true); }, []);

  // 정렬 변경 시 처음부터 다시 — 각 effect가 자신의 최초 실행(마운트와 동시 발화)만 개별 스킵.
  // 공유 ref로 스킵하면 마운트 effect가 먼저 ref를 true로 바꿔 다음 effect가 오작동한다.
  const isFirstSort = useRef(true);
  useEffect(() => {
    if (isFirstSort.current) { isFirstSort.current = false; return; }
    fetchSourcesPage(true);
  }, [srcSort]);

  // 검색어 디바운스 재조회 (최초 마운트 제외)
  const isFirstSearch = useRef(true);
  useEffect(() => {
    if (isFirstSearch.current) { isFirstSearch.current = false; return; }
    const t = setTimeout(() => { fetchSourcesPage(true); }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  useEffect(() => {
    if (activeSubTab === "exports" && !exportsLoaded) fetchExports();
    if (activeSubTab === "timeline" && !timelineLoaded) fetchTimelineDays(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSubTab]);

  const toggleExpand = async (sid: string) => {
    const next = expandedSourceId === sid ? null : sid;
    setExpandedSourceId(next);
    if (next) await fetchSourceDetail(sid);
  };

  const togglePlay = async (s: SourceCard) => {
    if (sourcePlayingId === s.source_id) { setSourcePlayingId(null); return; }
    const detail = await fetchSourceDetail(s.source_id);
    if (detail?.play_url) setSourcePlayingId(s.source_id);
  };

  const renderSourceCard = (s: SourceCard) => {
    const isExpanded = expandedSourceId === s.source_id;
    const detail = detailCache[s.source_id];
    const isDetailLoading = !!detailLoading[s.source_id];
    return (
      <div key={s.source_id} className="hover:bg-secondary/20 transition-colors">
        <div className="p-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-14 h-10 flex-shrink-0 rounded-lg bg-primary/10 flex items-center justify-center overflow-hidden">
              {s.thumbnail_url ? (
                <img src={s.thumbnail_url} className="w-full h-full object-cover" draggable={false} />
              ) : (
                <Film size={16} className="text-primary" />
              )}
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
                <button
                  onClick={() => createProjectFromSource(s.source_id)}
                  disabled={creatingFor === s.source_id}
                  className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 hover:bg-emerald-500/25 transition-colors flex-shrink-0 disabled:opacity-50"
                >
                  {creatingFor === s.source_id ? "생성 중…" : "+ 신규 프로젝트 생성"}
                </button>
              </div>
              <div className="flex items-center gap-2.5 text-[11px] text-muted-foreground/60 mt-1">
                {s.shot_date && (
                  <>
                    <span className="flex items-center gap-1 text-foreground/70 font-semibold"><Calendar size={10} /> {s.shot_date}</span>
                    <span>·</span>
                  </>
                )}
                {s.shot_date_fallback && (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">업로드일 기준</span>
                )}
                <span className="flex items-center gap-1"><Clock size={10} /> {formatSecs(s.duration)}</span>
                {s.fragment_count > 0 && (
                  <>
                    <span>·</span>
                    <span className="text-foreground/70 font-semibold">조각 {s.fragment_count}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={() => togglePlay(s)}
              disabled={isDetailLoading}
              className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-[10px] font-semibold text-emerald-400 transition-colors disabled:opacity-50"
            >
              {sourcePlayingId === s.source_id ? <X size={11} /> : <Play size={11} />}
              {sourcePlayingId === s.source_id ? "닫기" : "재생"}
            </button>
            <button
              onClick={() => toggleExpand(s.source_id)}
              className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-secondary/40 hover:bg-secondary/70 text-[10px] font-semibold text-foreground/60 transition-colors"
            >
              상세 {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            </button>
            <button
              onClick={() => setSrcDelete({ id: s.source_id, title: s.title })}
              className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-red-500/10 hover:bg-red-500/20 text-[10px] font-semibold text-red-400 transition-colors"
            >
              <Trash2 size={11} /> 삭제
            </button>
          </div>
        </div>

        {sourcePlayingId === s.source_id && detail?.play_url && (
          <div className="px-4 pb-4 pl-[68px]">
            <video src={videoSrc(detail.play_url)} controls autoPlay className="w-[360px] max-w-full aspect-video rounded-lg bg-black" />
          </div>
        )}

        {isExpanded && (
          <div className="px-4 pb-4 pl-[68px] space-y-3">
            {isDetailLoading && !detail ? (
              <div className="text-[11px] text-muted-foreground/76 animate-pulse">상세 불러오는 중...</div>
            ) : detail ? (
              <>
                {detail.notes.length > 0 && (
                  <p className="text-[11px] text-primary/70">“{detail.notes[0].text}”</p>
                )}
                {detail.usage.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-black tracking-widest uppercase text-muted-foreground/76">사용 프로젝트 {detail.usage.length}</p>
                    {detail.usage.map(u => (
                      <button
                        key={u.program_id}
                        onClick={() => onNavigateToProject?.(u.program_id)}
                        className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-secondary/20 hover:bg-secondary/40 transition-colors group"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Box size={12} className="text-blue-400 flex-shrink-0" />
                          <span className="text-xs font-medium text-foreground/80 truncate group-hover:text-primary transition-colors">
                            {u.name || u.program_id}{u.label ? <span className="text-blue-400/60">-{u.label}</span> : null}
                          </span>
                        </div>
                        <span className="text-[10px] text-muted-foreground/70 flex-shrink-0">
                          {u.used_at && new Date(u.used_at).toLocaleString()}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
                {detail.fragments.length > 0 && (
                  <div>
                    <p className="text-[10px] font-black tracking-widest uppercase text-muted-foreground/76 mb-1.5">
                      조각 파노라마 — 최종 수정 기준 · 클릭하면 크게 봅니다
                    </p>
                    <div className="flex gap-1.5 overflow-x-auto pb-2">
                      {detail.fragments.map((f: any) => (
                        <button
                          key={`${f.start_ds}_${f.end_ds}`}
                          onClick={() => {
                            setViewerFrag({
                              fragment_id: f.fragment_id,
                              fragment_uid: f.fragment_id,
                              source_id: s.source_id,
                              source_video: "",
                              display_name: f.display_name,
                              start_time: f.eff_start, end_time: f.eff_end,
                              start_frame: Math.round((f.eff_start ?? 0) * 30),
                              end_frame: Math.round((f.eff_end ?? 0) * 30),
                              duration: Math.max(1, Math.round(((f.eff_end ?? 0) - (f.eff_start ?? 0)) * 30)),
                              selection_state: "S", status: "committed",
                            });
                            setViewerOpen(true);
                          }}
                          title={`${f.display_name}${f.edited ? " · 편집됨" : ""}`}
                          className={`relative flex-shrink-0 w-[104px] rounded-lg overflow-hidden border transition-colors text-left group
                            ${f.edited ? "border-amber-400/50" : "border-border/20"} hover:border-primary/60
                            ${f.excluded ? "opacity-40" : ""}`}
                        >
                          <div className="aspect-video bg-black/50">
                            {f.thumbnail_url ? (
                              <img src={f.thumbnail_url} className="w-full h-full object-cover" draggable={false} />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-[9px] text-muted-foreground/76">미리보기 없음</div>
                            )}
                          </div>
                          <div className="px-1.5 py-1 bg-black/40">
                            <p className="text-[9px] text-white/80 truncate">{f.display_name?.split(" · ")[1] ?? ""}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {detail.exports.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[10px] font-black tracking-widest uppercase text-muted-foreground/76">내보낸 영상 {detail.exports.length}</p>
                    {detail.exports.map(ex => (
                      <div key={ex.id} className="text-[11px] text-foreground/70 px-2 py-1 rounded bg-secondary/15">
                        {ex.display_name || ex.id} <span className="text-muted-foreground/70">· {ex.status}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : null}
          </div>
        )}
      </div>
    );
  };

  // [국장지시 2026-07-06] 작업대는 아카이브 작업공간 — 통계 카드·제목·원본검색을 걷어내고
  // 얇은 헤더 1줄 + 본문 최대. 다른 탭(원본리스트/연대기/내보낸영상)은 기존 경험 유지.
  const isWb = activeSubTab === "workbench";

  return (
    <div className={`flex flex-col h-full bg-[hsl(228_10%_9%)] px-4 pt-3 pb-2 gap-2 ${isWb ? "overflow-hidden" : "overflow-y-auto"}`}>
      {/* Header — 모든 탭 공통 compact 1줄 (국장지시 2026-07-06: 상단 일관성) */}
      <div className="flex items-center justify-between flex-shrink-0">
        <p className="text-[13px] text-foreground/75">
          <span className="font-bold text-primary">CCUT 아카이브</span>
          <span className="text-muted-foreground/76">
            {" · "}원본 {summary?.source_count ?? 0} · 프로젝트 {summary?.program_count ?? 0} · 최근 촬영 {summary?.latest_shot_date ?? "—"}
          </span>
        </p>
        <button
          onClick={() => { fetchSummary(); fetchSourcesPage(true); }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/80 hover:bg-secondary text-xs text-foreground/80 transition-colors border border-border/20 flex-shrink-0"
        >
          <RotateCcw size={12} />
          새로고침
        </button>
      </div>

      {/* [국장지시 2026-07-06] 통계 카드 3개 제거 — 필요한 숫자는 compact 헤더 1줄로 충분 */}

      {/* Tabs (+ 검색 — 작업대에선 숨김) */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-card/15 p-3 rounded-xl border border-border/10 flex-shrink-0">
        <div className="flex items-center gap-1.5 bg-secondary/30 rounded-lg p-0.5">
          {(["workbench", "sources", "timeline", "exports"] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveSubTab(tab)}
              className={`px-4 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeSubTab === tab ? "bg-primary/20 text-primary" : "text-muted-foreground/60 hover:text-foreground/80"
              }`}
            >
              {tab === "workbench" ? "작업대" : tab === "sources" ? "원본 리스트" : tab === "timeline" ? "연대기" : "내보낸 영상"}
            </button>
          ))}
        </div>
        {!isWb && (
        <div className="relative w-full md:w-72">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/70" />
          <Input
            placeholder="검색"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-8 bg-secondary/30 border-border/10 text-xs focus-visible:ring-primary/40 rounded-lg"
          />
        </div>
        )}
      </div>

      {/* Content Area — 작업대일 때 남은 높이 전체 사용, 그 외엔 기존 스크롤 */}
      <div className={isWb ? "flex-1 min-h-0" : "flex-1 min-h-[300px]"}>
        <div className={isWb ? "h-full" : "space-y-3"}>

          {/* ── 원본 리스트 탭 (hydrate 분리: summary + sources 페이징) ── */}
          {activeSubTab === "sources" && (
            <>
              <div className="flex items-center gap-1.5 mb-2">
                {([["shot_date_desc", "촬영일순"], ["created_desc", "최신 업로드순"]] as const).map(([v, l]) => (
                  <button key={v} onClick={() => setSrcSort(v)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-all ${srcSort === v ? "bg-primary/20 text-primary" : "bg-secondary/30 text-muted-foreground/60 hover:text-foreground/80"}`}>
                    {l}
                  </button>
                ))}
              </div>
              {sourcesLoading ? (
                <div className="flex flex-col items-center justify-center h-64 text-muted-foreground/70 text-xs gap-2">
                  <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                  원본 목록 로드 중...
                </div>
              ) : (
                <>
                  <div className="bg-card/20 rounded-xl border border-border/10 overflow-hidden divide-y divide-border/10">
                    {sourceCards.length > 0 ? sourceCards.map(renderSourceCard) : (
                      <div className="p-8 text-center text-xs text-muted-foreground/70">검색 조건에 맞는 원본 영상이 없습니다.</div>
                    )}
                  </div>
                  {sourcesCursor && (
                    <div className="flex justify-center pt-3">
                      <button
                        onClick={() => fetchSourcesPage(false)}
                        disabled={sourcesLoadingMore}
                        className="px-4 py-2 rounded-lg bg-secondary/40 hover:bg-secondary/70 text-xs font-semibold text-foreground/70 transition-colors disabled:opacity-50"
                      >
                        {sourcesLoadingMore ? "불러오는 중..." : "더보기"}
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}

          {/* ── 연대기 탭 (shot_date 기반 day 페이징) ── */}
          {activeSubTab === "timeline" && (
            <>
              {timelineLoading && timelineDays.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-64 text-muted-foreground/70 text-xs gap-2">
                  <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                  연대기 로드 중...
                </div>
              ) : (
                <div className="bg-card/20 rounded-xl border border-border/10 overflow-hidden divide-y divide-border/10">
                  {timelineDays.length > 0 ? timelineDays.map(d => (
                    <div key={d.date_key}>
                      <button
                        onClick={() => openDay(d.date_key)}
                        className="w-full flex items-center gap-3 p-4 hover:bg-secondary/20 transition-colors text-left"
                      >
                        <div className="w-14 h-10 flex-shrink-0 rounded-lg bg-primary/10 flex items-center justify-center overflow-hidden">
                          {d.thumbnail_url ? (
                            <img src={d.thumbnail_url} className="w-full h-full object-cover" draggable={false} />
                          ) : (
                            <Calendar size={16} className="text-primary" />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-foreground/90">{d.date_key}</span>
                            {d.has_fallback && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">업로드일 기준 포함</span>
                            )}
                          </div>
                          <p className="text-[11px] text-muted-foreground/60 mt-0.5">원본 {d.source_count}개</p>
                        </div>
                        {selectedDay === d.date_key ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                      {selectedDay === d.date_key && (
                        <div className="px-4 pb-4 pl-[68px]">
                          {dayLoading ? (
                            <div className="text-[11px] text-muted-foreground/76 animate-pulse">불러오는 중...</div>
                          ) : dayDetail ? (
                            <div className="space-y-2">
                              {dayDetail.sources.map(s => renderSourceCard(s))}
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  )) : (
                    <div className="p-8 text-center text-xs text-muted-foreground/70">연대기 데이터가 없습니다.</div>
                  )}
                </div>
              )}
              {timelineCursor && (
                <div className="flex justify-center pt-3">
                  <button
                    onClick={() => fetchTimelineDays(false)}
                    disabled={timelineLoading}
                    className="px-4 py-2 rounded-lg bg-secondary/40 hover:bg-secondary/70 text-xs font-semibold text-foreground/70 transition-colors disabled:opacity-50"
                  >
                    {timelineLoading ? "불러오는 중..." : "더보기"}
                  </button>
                </div>
              )}
            </>
          )}


          {/* ── 내보낸 영상 탭 (exports 탭 클릭 시 lazy 조회) ── */}
          {/* ── 작업대 탭 (조각 조회·수집 — read-only, project_sources 무변경) ── */}
          {activeSubTab === "workbench" && <ArchiveWorkbench />}

          {activeSubTab === "exports" && (
            exportsLoading ? (
              <div className="flex flex-col items-center justify-center h-64 text-muted-foreground/70 text-xs gap-2">
                <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                내보낸 영상 로드 중...
              </div>
            ) : exports.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 gap-3 text-muted-foreground/65">
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
                    <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center overflow-hidden">
                      {ex.thumbnail_url ? (
                        <img src={ex.thumbnail_url} className="w-full h-full object-cover" draggable={false} />
                      ) : (
                        <Film size={18} className="text-primary" />
                      )}
                    </div>
                    <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-primary/80 text-[9px] font-black text-white flex items-center justify-center">
                      {idx + 1}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[15px] font-bold text-foreground/90 truncate">
                      {ex.display_name || ex.program_title || "내보낸 영상"}
                    </p>
                    <div className="flex items-center gap-3 mt-1 text-[11px] text-muted-foreground/76">
                      {ex.duration != null && <span className="flex items-center gap-1"><Clock size={10} />{formatSecs(ex.duration)}</span>}
                      {ex.file_size != null && <span>{(ex.file_size / 1024 / 1024).toFixed(1)} MB</span>}
                      {ex.created_at && <span className="flex items-center gap-1"><Calendar size={10} />{new Date(ex.created_at).toLocaleString()}</span>}
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
                        onClick={() => onNavigateToProject?.(ex.program_id!, true)}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-foreground/70 text-xs font-medium transition-colors border border-border/15"
                      >
                        <Edit3 size={13} />
                        다시 편집
                      </button>
                    )}
                    {/* [LAB-21] 즉시 파기가 아니라 storage/trash 로 옮긴다 — 원본 삭제와 같은 방식. */}
                    <button
                      onClick={() => setDeleteTarget(ex)}
                      disabled={deletingId === ex.id}
                      title="휴지통으로 이동"
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 hover:bg-red-500/15 text-foreground/60 hover:text-red-300 text-xs font-medium transition-colors border border-border/15 disabled:opacity-40"
                    >
                      <Trash2 size={13} />
                      {deletingId === ex.id ? "삭제 중" : "삭제"}
                    </button>
                  </div>
                </div>

                {playingId === ex.id && (
                  <div className="mx-5 mb-3 rounded-xl overflow-hidden bg-black w-[360px] aspect-video">
                    <video
                      src={videoSrc(ex.output_url)}
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
                </div>
              </div>
            ))
          )}

        </div>
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

      {/* [조각 뷰어] 프로젝트의 정밀편집창과 동일 — 단 보기 전용 (수정은 새 프로젝트에서) */}
      <SingleFragmentEditor
        open={viewerOpen}
        onOpenChange={setViewerOpen}
        fragment={viewerFrag}
        projectName="아카이브"
        readOnly
      />

      {/* [LAB-25] 산출물 삭제 확인·결과 — 브라우저 기본창 대신 앱 대화상자 */}
      <AppDialog
        open={!!deleteTarget}
        message={deleteTarget
          ? `"${deleteTarget.display_name || deleteTarget.program_title || "내보낸 영상"}" 을(를) 휴지통으로 보냅니다.\n목록에서 사라지지만 파일은 보관됩니다.`
          : ""}
        confirmText="삭제"
        cancelText="취소"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          const target = deleteTarget;
          setDeleteTarget(null);
          if (target) void runDeleteExport(target);
        }}
      />
      <AppDialog
        open={!!deleteNotice}
        message={deleteNotice ?? ""}
        confirmText="OK"
        onConfirm={() => setDeleteNotice(null)}
      />
    </div>
  );
};
