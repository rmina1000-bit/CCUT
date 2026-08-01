import React, { useState, useRef, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { fetcher } from "@/services/api";
import { Send, Film, Clock, Plus, Check, X, ShoppingBasket, Search as SearchIcon, Layers, Play, FolderOpen, ChevronDown, ChevronUp } from "lucide-react";
import { ArchivePreviewModal, PreviewItem } from "@/components/ArchivePreviewModal";
import {
  workbenchStore, useWorkbenchStore,
  FragmentCard, SourceFragment, SourceDetail, SourceSlot, BasketItem,
} from "@/lib/archiveWorkbenchStore";

// [아카이브 작업대 2026-07-06] read-only 조각 조회·수집 작업대.
// 좌: 아카이브와 대화(채팅) · 우: 원본맵(A/B/C…) + 활성 원본 조각맵 + Basket + 구간 미리보기.
// [B] 작업 상태(검색·원본맵·바구니·export결과)는 module store — 메뉴/탭 이동에도 유지, 새로고침만 초기화.
// 절대 금지: proposal_engine/route-edit/project_sources 변경. read-only 두 API만 호출.

const RESULT_TYPE_LABEL: Record<string, string> = {
  person: "인물 검색 결과",
  place: "장소 검색 결과",
  scene: "장면 검색 결과",
  person_place: "인물+장소 검색 결과",
  person_scene: "인물+장면 검색 결과",
  person_keyword: "인물+키워드 검색 결과",
  keyword: "키워드 검색 결과",
  unmatched: "일치하는 결과를 찾지 못했습니다",
};

const RESULT_INTRO: Record<string, string> = {
  person: "인물로 찾았어요",
  place: "장소로 찾았어요",
  scene: "장면으로 찾았어요",
  person_place: "인물과 장소를 함께 찾았어요",
  person_scene: "인물과 장면을 함께 찾았어요",
  person_keyword: "인물과 내용을 함께 찾았어요",
  keyword: "키워드로 찾았어요",
  unmatched: "조건에 맞는 조각을 찾지 못했어요. 다르게 말씀해 주시겠어요?",
};

const fmt = (sec: number | null) => {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

const dur = (a: number | null, b: number | null) =>
  a != null && b != null ? Math.max(0, b - a) : 0;

export const ArchiveWorkbench: React.FC = () => {
  // ── 유지 상태 (store) ──
  const { messages, slots, activeSourceId, matchedIds, basket, exportResult } = useWorkbenchStore();

  // ── 임시 UI 상태 (로컬 — 재마운트 시 리셋돼도 무해) ──
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingSource, setLoadingSource] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewItem | null>(null);
  const [exporting, setExporting] = useState(false);
  const [failOpen, setFailOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // [LAYOUT] 아카이브 채팅 컬럼 폭 — 기본 30%↓, 드래그 리사이즈 + localStorage 저장
  const wbRef = useRef<HTMLDivElement | null>(null);
  const [chatWidth, setChatWidth] = useState<number>(() => {
    if (typeof window !== "undefined") {
      const v = Number(window.localStorage.getItem("ccut_archive_chat_width"));
      if (Number.isFinite(v) && v > 0) return v;
      return Math.round(Math.min(520, Math.max(280, window.innerWidth * 0.24)));
    }
    return 360;
  });
  const [isChatDragging, setIsChatDragging] = useState(false);
  useEffect(() => {
    localStorage.setItem("ccut_archive_chat_width", String(chatWidth));
  }, [chatWidth]);
  useEffect(() => {
    if (!isChatDragging) return;
    const onMove = (e: MouseEvent) => {
      if (!wbRef.current) return;
      const rect = wbRef.current.getBoundingClientRect();
      setChatWidth(Math.max(240, Math.min(rect.width - 340, e.clientX - rect.left)));
    };
    const onUp = () => setIsChatDragging(false);
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isChatDragging]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const query = input.trim();
    if (!query || loading) return;
    setInput("");
    workbenchStore.update(s => ({ messages: [...s.messages, { id: `u_${Date.now()}`, role: "user", text: query }] }));
    setLoading(true);
    try {
      const r = await fetcher("/archive/chat", {
        method: "POST", body: JSON.stringify({ query }),
      }) as { result_set_id: string | null; result_type: string; results: FragmentCard[] };
      workbenchStore.update(s => ({
        messages: [...s.messages, { id: `a_${Date.now()}`, role: "assistant", resultType: r.result_type, results: r.results }],
        matchedIds: (r.results ?? []).map(x => x.fragment_id),
      }));
    } catch (e) {
      console.error("[ArchiveWorkbench] 조회 실패:", e);
      workbenchStore.update(s => ({ messages: [...s.messages, { id: `a_${Date.now()}`, role: "assistant", text: "조회 중 오류가 발생했어요. 잠시 후 다시 말씀해 주세요." }] }));
    } finally {
      setLoading(false);
    }
  };

  const addSourceToMap = async (sourceId: string) => {
    if (slots.some(s => s.detail.source_id === sourceId)) { workbenchStore.setState({ activeSourceId: sourceId }); return; }
    setLoadingSource(sourceId);
    try {
      const detail = await fetcher(`/archive/source/${encodeURIComponent(sourceId)}`) as SourceDetail;
      workbenchStore.update(s => s.slots.some(x => x.detail.source_id === sourceId)
        ? { activeSourceId: sourceId }
        : { slots: [...s.slots, { label: labelFor(s.slots.length), detail }], activeSourceId: sourceId });
    } catch (e) {
      console.error("[ArchiveWorkbench] 원본 조회 실패:", e);
    } finally {
      setLoadingSource(null);
    }
  };

  const removeSource = (sourceId: string) => {
    workbenchStore.update(s => {
      const next = s.slots.filter(x => x.detail.source_id !== sourceId).map((x, i) => ({ ...x, label: labelFor(i) }));
      return { slots: next, activeSourceId: s.activeSourceId === sourceId ? (next.length ? next[next.length - 1].detail.source_id : null) : s.activeSourceId };
    });
  };

  const inBasket = (fid: string) => !!basket[fid];
  const toggleBasket = (item: BasketItem) => {
    workbenchStore.update(s => {
      const next = { ...s.basket };
      if (next[item.fragment_id]) delete next[item.fragment_id];
      else next[item.fragment_id] = item;
      return { basket: next, exportResult: null };
    });
  };

  const cardToItem = (c: FragmentCard): BasketItem => ({
    fragment_id: c.fragment_id, source_id: c.source_id,
    source_title: (c.display_name || "").split(" · ")[0] || c.source_id,
    thumbnail_url: c.thumbnail_url, video_url: c.video_url, start: c.start, end: c.end, display_name: c.display_name,
  });

  const fragToItem = (f: SourceFragment, d: SourceDetail): BasketItem => ({
    fragment_id: f.fragment_id, source_id: d.source_id, source_title: d.title,
    thumbnail_url: f.thumbnail_url, video_url: d.play_url, start: f.start, end: f.end, display_name: f.display_name,
  });

  const addWholeSource = (slot: SourceSlot) => {
    workbenchStore.update(s => {
      const next = { ...s.basket };
      slot.detail.fragments.forEach(f => { next[f.fragment_id] = fragToItem(f, slot.detail); });
      return { basket: next, exportResult: null };
    });
  };

  const toPreview = (b: BasketItem): PreviewItem => ({
    fragment_id: b.fragment_id, display_name: b.display_name, video_url: b.video_url,
    start: b.start, end: b.end, source_title: b.source_title,
  });

  const basketItems = Object.values(basket);
  const basketTotal = basketItems.reduce((s, b) => s + dur(b.start, b.end), 0);

  const exportBasket = async () => {
    if (exporting || basketItems.length === 0) return null;
    setExporting(true);
    workbenchStore.setState({ exportResult: null });
    setFailOpen(false);
    try {
      const r = await fetcher("/archive/basket/export", {
        method: "POST",
        body: JSON.stringify({ items: basketItems.map(b => ({ fragment_id: b.fragment_id })) }),
      }) as { status: string; ok_count: number; duration_sec: number; export_dir: string; failed: { fragment_id: string; reason: string }[]; message?: string };
      if (r.status === "OK") {
        const result = { ok_count: r.ok_count, duration_sec: r.duration_sec, export_dir: r.export_dir, failed: r.failed ?? [] };
        workbenchStore.setState({ exportResult: result });
        return result;
      } else {
        const result = { ok_count: 0, duration_sec: 0, export_dir: "", failed: [{ fragment_id: "-", reason: r.message || "내보내기 실패" }] };
        workbenchStore.setState({ exportResult: result });
        return result;
      }
    } catch (e) {
      const result = { ok_count: 0, duration_sec: 0, export_dir: "", failed: [{ fragment_id: "-", reason: String(e) }] };
      workbenchStore.setState({ exportResult: result });
      return result;
    } finally {
      setExporting(false);
    }
  };

  const openExportFolder = async (dir?: string) => {
    const exportDir = dir || exportResult?.export_dir;
    if (!exportDir) return;
    try {
      await fetcher("/archive/basket/export/open-folder", { method: "POST", body: JSON.stringify({ export_dir: exportDir }) });
    } catch (e) {
      console.warn("[ArchiveWorkbench] 폴더 열기 실패:", e);
    }
  };

  const prepareAndOpenFolder = async () => {
    if (exporting || basketItems.length === 0) return;
    if (exportResult?.export_dir && exportResult.ok_count > 0) {
      await openExportFolder(exportResult.export_dir);
      return;
    }
    const result = await exportBasket();
    if (result?.export_dir && result.ok_count > 0) {
      await openExportFolder(result.export_dir);
    }
  };

  const activeSlot = slots.find(s => s.detail.source_id === activeSourceId) ?? null;

  return (
    <div ref={wbRef} className="flex gap-2 h-[calc(100vh-118px)] min-h-[480px]">

      {/* ══ 좌: 아카이브와 대화(채팅) ══ */}
      <div style={{ width: chatWidth }} className="flex flex-col rounded-xl border border-border/15 bg-card/20 overflow-hidden min-h-0 flex-shrink-0">
        <div className="px-4 py-2.5 border-b border-border/10 flex items-center gap-2 flex-shrink-0">
          <SearchIcon size={12} className="text-primary" />
          <p className="text-[11px] font-bold text-foreground/80">아카이브와 대화</p>
        </div>
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
          {messages.length === 0 && (
            <div className="flex justify-start">
              <div className="max-w-[90%] px-3 py-2 rounded-2xl rounded-tl-sm bg-secondary/30 text-foreground/75 text-[12px] leading-relaxed">
                무엇을 찾아드릴까요? "실내 장면 보여줘", "해변 나오는 조각", "정은한 나온 장면"처럼 말씀하시면 조각을 찾아드려요.
                찾은 카드를 누르면 그 원본이 오른쪽 원본맵에 담깁니다.
              </div>
            </div>
          )}
          {messages.map(m => (
            <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              {m.role === "user" ? (
                <div className="max-w-[80%] px-3 py-2 rounded-2xl rounded-tr-sm bg-primary/25 text-foreground/90 text-sm">{m.text}</div>
              ) : (
                <div className="max-w-[92%] space-y-2">
                  <div className="px-3 py-2 rounded-2xl rounded-tl-sm bg-secondary/30 text-foreground/80 text-[13px] inline-block">
                    {m.text ?? (RESULT_INTRO[m.resultType ?? ""] ?? "찾았어요")}
                    {m.results && m.resultType !== "unmatched" && m.results.length > 0 && (
                      <span className="text-muted-foreground/76"> — 조각 {m.results.length}개</span>
                    )}
                  </div>
                  {m.results && m.results.length > 0 && (
                    <div className="space-y-1.5">
                      {m.results.map(r => {
                        const onMap = slots.some(s => s.detail.source_id === r.source_id);
                        return (
                          <div key={r.fragment_id} className="flex items-center gap-2 p-2 rounded-lg bg-card/40 border border-border/10 hover:border-border/25 transition-colors">
                            <button onClick={() => addSourceToMap(r.source_id)}
                              className="relative w-14 h-10 flex-shrink-0 rounded-md bg-primary/10 flex items-center justify-center overflow-hidden hover:ring-2 hover:ring-primary/40 transition-all"
                              title="이 원본을 원본맵에 담기">
                              {r.thumbnail_url ? <img src={r.thumbnail_url} className="w-full h-full object-cover" draggable={false} /> : <Film size={14} className="text-primary" />}
                            </button>
                            <button onClick={() => addSourceToMap(r.source_id)} className="min-w-0 flex-1 text-left">
                              <p className="text-xs font-semibold text-foreground/85 truncate">{r.display_name || r.fragment_id}</p>
                              <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/76">
                                {(r.start != null || r.end != null) && <span className="flex items-center gap-0.5"><Clock size={9} />{fmt(r.start)}–{fmt(r.end)}</span>}
                                {onMap && <span className="text-primary/70">원본맵에 있음</span>}
                              </div>
                            </button>
                            <button onClick={() => setPreview({ fragment_id: r.fragment_id, display_name: r.display_name, video_url: r.video_url, start: r.start, end: r.end, source_title: (r.display_name || "").split(" · ")[0] })}
                              className="flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center bg-secondary/50 text-muted-foreground/60 hover:bg-blue-500/20 hover:text-blue-400 transition-colors"
                              title="이 구간 미리보기">
                              <Play size={12} />
                            </button>
                            <button onClick={() => toggleBasket(cardToItem(r))}
                              className={`flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center transition-colors ${inBasket(r.fragment_id) ? "bg-emerald-500/25 text-emerald-400" : "bg-secondary/50 text-muted-foreground/60 hover:bg-primary/20 hover:text-primary"}`}
                              title={inBasket(r.fragment_id) ? "바구니에서 빼기" : "이 조각만 바구니에 담기"}>
                              {inBasket(r.fragment_id) ? <Check size={13} /> : <Plus size={13} />}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          {loading && <div className="flex justify-start"><div className="px-3 py-2 rounded-2xl rounded-tl-sm bg-secondary/30 text-muted-foreground/76 text-xs animate-pulse">찾는 중...</div></div>}
        </div>
        <div className="px-4 py-3 border-t border-border/10 flex items-center gap-2 flex-shrink-0">
          <Input value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") send(); }}
            placeholder="예: 실내 장면 보여줘" className="h-9 bg-secondary/30 border-border/10 text-sm" disabled={loading} />
          <button onClick={send} disabled={loading || !input.trim()}
            className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/20 hover:bg-primary/30 text-primary disabled:opacity-40 transition-colors flex-shrink-0">
            <Send size={14} />
          </button>
        </div>
      </div>

      {/* [LAYOUT] 아카이브 채팅/작업대 경계 리사이즈 핸들 */}
      <div
        className={`flex-shrink-0 flex items-center justify-center cursor-col-resize group transition-colors ${isChatDragging ? "bg-primary/15" : "hover:bg-primary/8"}`}
        style={{ width: 6 }}
        onMouseDown={(e) => { e.preventDefault(); setIsChatDragging(true); }}
      >
        <div className={`w-[2px] h-10 rounded-full transition-all duration-150 ${isChatDragging ? "bg-primary/60 h-16" : "bg-border/40 group-hover:bg-primary/40 group-hover:h-14"}`} />
      </div>

      {/* ══ 우: 확인/수집 작업대 ══ */}
      <div className="flex flex-col gap-3 min-h-0 flex-1 min-w-0">
        {/* 원본맵 */}
        <div className="rounded-xl border border-border/15 bg-card/20 px-4 py-2.5 flex-shrink-0 max-h-[130px] overflow-y-auto">
          <div className="flex items-center gap-2 mb-2">
            <Layers size={13} className="text-primary" />
            <p className="text-[10px] font-black tracking-widest uppercase text-muted-foreground/76">원본맵</p>
            <span className="text-[10px] text-muted-foreground/70">{slots.length ? `${slots.length}개 원본 · 배지를 눌러 전환` : "검색 결과의 원본을 담아보세요"}</span>
          </div>
          {slots.length === 0 ? (
            <p className="text-[11px] text-muted-foreground/70">왼쪽 채팅에서 찾은 조각·썸네일을 누르면 그 원본이 여기 A·B·C…로 쌓입니다.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {slots.map(s => {
                const on = s.detail.source_id === activeSourceId;
                const thumb = s.detail.fragments?.[0]?.thumbnail_url;
                return (
                  <div key={s.detail.source_id}
                    className={`flex flex-shrink-0 items-center gap-2 p-1.5 rounded-lg border transition-colors ${on ? "bg-primary/20 border-primary/50" : "bg-secondary/30 border-border/15 hover:border-border/40"}`}>
                    <button onClick={() => workbenchStore.setState({ activeSourceId: s.detail.source_id })} className="flex items-center gap-2 min-w-0" title={s.detail.title}>
                      <span className="relative w-12 h-8 flex-shrink-0 rounded overflow-hidden bg-primary/10 flex items-center justify-center">
                        {thumb ? <img src={thumb} className="w-full h-full object-cover" draggable={false} /> : <Film size={12} className="text-primary" />}
                        <span className={`absolute top-0 left-0 px-1 rounded-br text-[9px] font-black leading-tight ${on ? "bg-primary/70 text-primary-foreground" : "bg-black/60 text-white/85"}`}>{s.label}</span>
                      </span>
                      <span className="min-w-0 max-w-[160px] text-left">
                        <span className="block text-[11px] font-semibold text-foreground/85 truncate">{s.detail.title}</span>
                        <span className="block text-[9px] text-muted-foreground/76">{s.detail.fragments?.length ?? 0}조각</span>
                      </span>
                    </button>
                    <button onClick={() => addWholeSource(s)} title="이 원본 전체를 바구니에 담기"
                      className="flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/30 transition-colors">
                      <ShoppingBasket size={11} />
                    </button>
                    <button onClick={() => removeSource(s.detail.source_id)} title="원본맵에서 빼기"
                      className="flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-muted-foreground/76 hover:bg-red-500/20 hover:text-red-400 transition-colors">
                      <X size={11} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 조각맵 — 가장 큰 영역 */}
        <div className="flex-1 rounded-xl border border-border/15 bg-card/20 overflow-y-auto p-3 min-h-0">
          {loadingSource ? (
            <p className="text-[11px] text-muted-foreground/76 animate-pulse">원본 조각맵 불러오는 중...</p>
          ) : activeSlot && activeSlot.detail.fragments?.length ? (
            <>
              <p className="text-[10px] font-black tracking-widest uppercase text-muted-foreground/76 mb-2 sticky top-0 bg-card/60 backdrop-blur py-1">
                조각맵 · {activeSlot.label} {activeSlot.detail.title} — 파란 테두리=검색결과 · ▶=미리보기 · 클릭=바구니
              </p>
              <div className="flex flex-wrap items-start content-start gap-2">
                {activeSlot.detail.fragments.map(f => {
                  const matched = matchedIds.includes(f.fragment_id);
                  const picked = inBasket(f.fragment_id);
                  const item = fragToItem(f, activeSlot.detail);
                  return (
                    <div key={f.fragment_id}
                      className={`relative w-[176px] flex-shrink-0 rounded-lg overflow-hidden border-2 transition-all cursor-pointer ${picked ? "border-emerald-400/70" : matched ? "border-primary/70" : "border-border/15 hover:border-border/40"}`}
                      onClick={() => toggleBasket(item)} title={f.display_name || f.fragment_id}>
                      <div className="aspect-video bg-black/50">
                        {f.thumbnail_url ? <img src={f.thumbnail_url} className="w-full h-full object-cover" draggable={false} /> : <div className="w-full h-full flex items-center justify-center"><Film size={14} className="text-muted-foreground/70" /></div>}
                      </div>
                      <button onClick={(e) => { e.stopPropagation(); setPreview(toPreview(item)); }}
                        className="absolute top-1 left-1 w-6 h-6 rounded-full bg-black/60 hover:bg-blue-500/70 text-white/90 flex items-center justify-center transition-colors"
                        title="이 구간 미리보기">
                        <Play size={11} />
                      </button>
                      {picked && <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-emerald-500/90 flex items-center justify-center"><Check size={11} className="text-white" /></div>}
                      {matched && !picked && <div className="absolute top-1 right-1 px-1 rounded bg-primary/80 text-[8px] font-bold text-white">검색</div>}
                      <div className="px-1.5 py-1 bg-black/40">
                        <p className="text-[9px] text-white/80 truncate">{f.display_name?.split(" · ")[1] ?? fmt(f.start)}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="h-full flex items-center justify-center">
              <p className="text-[11px] text-muted-foreground/70 text-center whitespace-pre-line">
                {slots.length ? "원본맵에서 배지를 눌러 그 원본의 조각맵을 펼치세요." : "왼쪽에서 조각을 찾아 원본을 담으면\n여기에 조각맵이 크게 펼쳐집니다."}
              </p>
            </div>
          )}
        </div>

        {/* 바구니 — 하단, 독립 스크롤 (완료 배너 있을 때 살짝 키움) */}
        <div className={`rounded-xl border border-border/15 bg-card/20 flex-shrink-0 flex flex-col ${exportResult ? "h-[270px]" : "h-[200px]"}`}>
          <div className="px-4 py-2.5 border-b border-border/10 flex items-center justify-between flex-shrink-0">
            <div className="flex items-center gap-2">
              <ShoppingBasket size={14} className="text-primary" />
              <p className="text-xs font-bold text-foreground/90">바구니</p>
              <span className="text-[11px] text-muted-foreground/76">{basketItems.length}개 · {basketTotal.toFixed(1)}초</span>
            </div>
            <div className="flex items-center gap-2">
              {!exporting && exportResult && exportResult.ok_count > 0 && (
                <span className="text-[11px] font-bold text-emerald-400">완료 {exportResult.ok_count}개{exportResult.failed.length > 0 ? ` · 실패 ${exportResult.failed.length}` : ""}</span>
              )}
              <button onClick={prepareAndOpenFolder} disabled={exporting || basketItems.length === 0}
                className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/20 text-emerald-400 text-[11px] font-bold hover:bg-emerald-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                <FolderOpen size={12} className={exporting ? "animate-pulse" : ""} />
                {exporting ? "폴더 준비 중..." : "폴더 열기"}
              </button>
            </div>
          </div>

          {/* 완료 피드백 — 스크롤 밖·헤더 바로 아래 고정 */}
          {exportResult && (
            <div className={`px-3 py-2 border-b flex-shrink-0 ${exportResult.ok_count > 0 ? "bg-emerald-500/10 border-emerald-500/20" : "bg-red-500/10 border-red-500/20"}`}>
              {exportResult.ok_count > 0 ? (
                <>
                  <p className="text-[11px] font-bold text-emerald-300">폴더 준비 완료 · {exportResult.ok_count}개 / {exportResult.duration_sec}초</p>
                  {exportResult.failed.length > 0 && (
                    <div className="mt-1">
                      <button onClick={() => setFailOpen(v => !v)}
                        className="flex items-center gap-1 text-[10px] text-amber-400/90 hover:text-amber-300">
                        {failOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />} 실패 {exportResult.failed.length}개
                      </button>
                      {failOpen && (
                        <ul className="mt-1 space-y-0.5 pl-3">
                          {exportResult.failed.map((f, i) => (
                            <li key={i} className="text-[10px] text-amber-400/70">· {f.reason}{f.fragment_id !== "-" ? ` (${f.fragment_id})` : ""}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-[11px] font-bold text-red-300">내보내기 실패 — {exportResult.failed.map(f => f.reason).join(", ")}</p>
              )}
            </div>
          )}

          <div className="flex-1 overflow-y-auto px-3 py-2 min-h-0">
            {basketItems.length === 0 ? (
              <p className="text-[11px] text-muted-foreground/70">담은 조각이 없습니다. 조각맵에서 조각을 담거나, 원본맵 배지의 바구니 아이콘으로 원본 전체를 담아보세요.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {basketItems.map(b => (
                  <div key={b.fragment_id} className="flex flex-shrink-0 items-center gap-2 p-1.5 rounded-lg bg-card/40 border border-border/10">
                    <button onClick={() => setPreview(toPreview(b))}
                      className="relative w-12 h-8 flex-shrink-0 rounded bg-primary/10 overflow-hidden flex items-center justify-center hover:ring-2 hover:ring-blue-400/50 transition-all group"
                      title="이 구간 미리보기">
                      {b.thumbnail_url ? <img src={b.thumbnail_url} className="w-full h-full object-cover" draggable={false} /> : <Film size={12} className="text-primary" />}
                      <span className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"><Play size={11} className="text-white" /></span>
                    </button>
                    <div className="min-w-0 max-w-[160px]">
                      <p className="text-[11px] font-semibold text-foreground/85 truncate">{b.display_name || b.fragment_id}</p>
                      <p className="text-[9px] text-muted-foreground/76 truncate">{b.source_title} · {fmt(b.start)}–{fmt(b.end)}</p>
                    </div>
                    <button onClick={() => toggleBasket(b)} title="바구니에서 빼기"
                      className="flex-shrink-0 w-6 h-6 rounded-md bg-secondary/50 hover:bg-red-500/20 text-muted-foreground/60 hover:text-red-400 flex items-center justify-center transition-colors">
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <ArchivePreviewModal item={preview} onClose={() => setPreview(null)} />
    </div>
  );
};

// 원본맵 라벨: 추가 순서대로 A, B, C … Z, AA …
function labelFor(idx: number) {
  let s = "", n = idx;
  while (true) { s = String.fromCharCode(65 + (n % 26)) + s; n = Math.floor(n / 26) - 1; if (n < 0) return s; }
}
