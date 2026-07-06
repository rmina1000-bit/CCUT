import React, { useState, useRef, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { fetcher } from "@/services/api";
import { Send, Film, Clock, Plus, Check, X, ShoppingBasket, Search as SearchIcon } from "lucide-react";
import { videoService } from "@/services/videoService";

// [아카이브 작업대 MVP 2026-07-06] read-only 조각 조회·수집 작업대.
// 좌: 자연어 검색(/archive/chat 재사용) · 우: 선택 원본 파노라마(/archive/source 재사용)
//   + 검색결과 강조 조각맵 + Basket(세션 state, DB 미저장).
// 절대 금지: proposal_engine/route-edit/project_sources 변경. read-only 두 API만 호출.

interface FragmentCard {
  fragment_id: string;
  source_id: string;
  display_name: string | null;
  thumbnail_url: string | null;
  video_url: string | null;
  start: number | null;
  end: number | null;
  people: string | null;
  places: string | null;
  evidence: Record<string, any> | null;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text?: string;
  resultType?: string;
  results?: FragmentCard[];
}

interface SourceFragment {
  fragment_id: string;
  display_name: string | null;
  thumbnail_url: string | null;
  start: number | null;
  end: number | null;
  eff_start: number | null;
  eff_end: number | null;
}

interface SourceDetail {
  source_id: string;
  title: string;
  shot_date: string | null;
  play_url: string | null;
  fragments: SourceFragment[];
}

interface BasketItem {
  fragment_id: string;
  source_id: string;
  source_title: string;
  thumbnail_url: string | null;
  start: number | null;
  end: number | null;
  display_name: string | null;
}

const RESULT_TYPE_LABEL: Record<string, string> = {
  person: "인물 검색 결과",
  place: "장소 검색 결과",
  scene: "장면 검색 결과",
  keyword: "키워드 검색 결과",
  unmatched: "일치하는 결과를 찾지 못했습니다",
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
  // ── 좌: 검색 ──
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // ── 우: 선택 원본 파노라마 ──
  const [detail, setDetail] = useState<SourceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  // 마지막 검색에 매칭된 fragment_id 집합 — 조각맵에서 강조
  const [matchedIds, setMatchedIds] = useState<Set<string>>(new Set());

  // ── Basket (세션 state — DB 미저장) ──
  const [basket, setBasket] = useState<Record<string, BasketItem>>({});

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const query = input.trim();
    if (!query || loading) return;
    setInput("");
    setMessages(prev => [...prev, { id: `u_${Date.now()}`, role: "user", text: query }]);
    setLoading(true);
    try {
      const r = await fetcher("/archive/chat", {
        method: "POST", body: JSON.stringify({ query }),
      }) as { result_set_id: string | null; result_type: string; results: FragmentCard[] };
      setMessages(prev => [...prev, {
        id: `a_${Date.now()}`, role: "assistant",
        resultType: r.result_type, results: r.results,
      }]);
      setMatchedIds(new Set((r.results ?? []).map(x => x.fragment_id)));
    } catch (e) {
      console.error("[ArchiveWorkbench] 조회 실패:", e);
      setMessages(prev => [...prev, { id: `a_${Date.now()}`, role: "assistant", text: "조회 중 오류가 발생했습니다." }]);
    } finally {
      setLoading(false);
    }
  };

  const openSource = async (sourceId: string) => {
    setDetailLoading(true);
    try {
      const r = await fetcher(`/archive/source/${encodeURIComponent(sourceId)}`) as SourceDetail;
      setDetail(r);
    } catch (e) {
      console.error("[ArchiveWorkbench] 원본 조회 실패:", e);
    } finally {
      setDetailLoading(false);
    }
  };

  const inBasket = (fid: string) => !!basket[fid];

  const toggleBasket = (item: BasketItem) => {
    setBasket(prev => {
      const next = { ...prev };
      if (next[item.fragment_id]) delete next[item.fragment_id];
      else next[item.fragment_id] = item;
      return next;
    });
  };

  // 검색 결과 카드 → Basket 아이템
  const cardToItem = (c: FragmentCard): BasketItem => ({
    fragment_id: c.fragment_id, source_id: c.source_id,
    source_title: (c.display_name || "").split(" · ")[0] || c.source_id,
    thumbnail_url: c.thumbnail_url, start: c.start, end: c.end, display_name: c.display_name,
  });

  // 조각맵 타일 → Basket 아이템
  const fragToItem = (f: SourceFragment): BasketItem => ({
    fragment_id: f.fragment_id, source_id: detail?.source_id ?? "",
    source_title: detail?.title ?? "", thumbnail_url: f.thumbnail_url,
    start: f.start, end: f.end, display_name: f.display_name,
  });

  const basketItems = Object.values(basket);
  const basketTotal = basketItems.reduce((s, b) => s + dur(b.start, b.end), 0);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-4 h-[calc(100vh-320px)] min-h-[420px]">

      {/* ══ 좌: 검색 ══ */}
      <div className="flex flex-col rounded-xl border border-border/15 bg-card/20 overflow-hidden">
        <div className="px-4 py-3 border-b border-border/10 flex items-center gap-2">
          <SearchIcon size={13} className="text-primary" />
          <p className="text-xs font-bold text-foreground/90">대화로 조각 찾기</p>
        </div>
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.length === 0 && (
            <p className="text-[11px] text-muted-foreground/50 leading-relaxed">
              "실내 장면 보여줘", "해변 나오는 조각", "정은한 나온 장면" 처럼 자연어로 물어보세요.<br />
              결과 카드의 <b>담기</b>로 바로 바구니에 넣거나, 카드를 눌러 원본 조각맵에서 고를 수 있어요.
            </p>
          )}
          {messages.map(m => (
            <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              {m.role === "user" ? (
                <div className="max-w-[85%] px-3 py-2 rounded-xl bg-primary/20 text-foreground/90 text-sm">{m.text}</div>
              ) : (
                <div className="w-full space-y-2">
                  {m.text && <div className="px-3 py-2 rounded-xl bg-secondary/30 text-foreground/80 text-sm inline-block">{m.text}</div>}
                  {m.resultType && (
                    <p className="text-[11px] font-semibold text-muted-foreground/60">
                      {RESULT_TYPE_LABEL[m.resultType] ?? m.resultType} {m.results?.length ? `(조각 ${m.results.length}개)` : ""}
                    </p>
                  )}
                  {m.results && m.results.length > 0 && (
                    <div className="space-y-1.5">
                      {m.results.map(r => (
                        <div key={r.fragment_id} className="flex items-center gap-2 p-2 rounded-lg bg-card/40 border border-border/10 hover:border-border/25 transition-colors">
                          <button onClick={() => openSource(r.source_id)}
                            className="w-14 h-10 flex-shrink-0 rounded-md bg-primary/10 flex items-center justify-center overflow-hidden hover:ring-2 hover:ring-primary/40 transition-all"
                            title="원본 조각맵 열기">
                            {r.thumbnail_url ? <img src={r.thumbnail_url} className="w-full h-full object-cover" draggable={false} /> : <Film size={14} className="text-primary" />}
                          </button>
                          <button onClick={() => openSource(r.source_id)} className="min-w-0 flex-1 text-left">
                            <p className="text-xs font-semibold text-foreground/85 truncate">{r.display_name || r.fragment_id}</p>
                            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/50">
                              {(r.start != null || r.end != null) && <span className="flex items-center gap-0.5"><Clock size={9} />{fmt(r.start)}–{fmt(r.end)}</span>}
                              {r.people && <span className="text-foreground/60 truncate">인물 {r.people}</span>}
                            </div>
                          </button>
                          <button onClick={() => toggleBasket(cardToItem(r))}
                            className={`flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center transition-colors ${inBasket(r.fragment_id) ? "bg-emerald-500/25 text-emerald-400" : "bg-secondary/50 text-muted-foreground/60 hover:bg-primary/20 hover:text-primary"}`}
                            title={inBasket(r.fragment_id) ? "바구니에서 빼기" : "바구니에 담기"}>
                            {inBasket(r.fragment_id) ? <Check size={13} /> : <Plus size={13} />}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          {loading && <div className="px-3 py-2 rounded-xl bg-secondary/30 text-muted-foreground/50 text-xs animate-pulse inline-block">검색 중...</div>}
        </div>
        <div className="px-4 py-3 border-t border-border/10 flex items-center gap-2">
          <Input value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") send(); }}
            placeholder="예: 실내 장면 보여줘" className="h-9 bg-secondary/30 border-border/10 text-sm" disabled={loading} />
          <button onClick={send} disabled={loading || !input.trim()}
            className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/20 hover:bg-primary/30 text-primary disabled:opacity-40 transition-colors flex-shrink-0">
            <Send size={14} />
          </button>
        </div>
      </div>

      {/* ══ 우: 파노라마 + 조각맵 + Basket ══ */}
      <div className="flex flex-col gap-4 min-h-0">
        {/* 상단: 선택 원본 */}
        <div className="rounded-xl border border-border/15 bg-card/20 px-4 py-3 flex-shrink-0">
          {detail ? (
            <div className="flex items-center gap-2">
              <Film size={14} className="text-primary" />
              <div className="min-w-0">
                <p className="text-sm font-bold text-foreground/90 truncate">{detail.title}</p>
                <p className="text-[11px] text-muted-foreground/50">{detail.shot_date ?? "촬영일 미상"} · 조각 {detail.fragments?.length ?? 0}개</p>
              </div>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground/40">검색 결과의 조각을 누르면 그 원본의 조각맵이 여기 펼쳐집니다.</p>
          )}
        </div>

        {/* 중단: 조각맵 */}
        <div className="flex-1 rounded-xl border border-border/15 bg-card/20 overflow-y-auto p-3 min-h-[140px]">
          {detailLoading ? (
            <p className="text-[11px] text-muted-foreground/50 animate-pulse">원본 조각맵 불러오는 중...</p>
          ) : detail && detail.fragments?.length ? (
            <>
              <p className="text-[10px] font-black tracking-widest uppercase text-muted-foreground/50 mb-2">
                조각맵 — 검색에 걸린 조각은 파란 테두리 · 클릭하면 바구니에 담깁니다
              </p>
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                {detail.fragments.map(f => {
                  const matched = matchedIds.has(f.fragment_id);
                  const picked = inBasket(f.fragment_id);
                  return (
                    <button key={f.fragment_id} onClick={() => toggleBasket(fragToItem(f))}
                      className={`relative rounded-lg overflow-hidden border-2 text-left transition-all ${picked ? "border-emerald-400/70" : matched ? "border-primary/70" : "border-border/15 hover:border-border/40"}`}
                      title={f.display_name || f.fragment_id}>
                      <div className="aspect-video bg-black/50">
                        {f.thumbnail_url ? <img src={f.thumbnail_url} className="w-full h-full object-cover" draggable={false} /> : <div className="w-full h-full flex items-center justify-center"><Film size={14} className="text-muted-foreground/40" /></div>}
                      </div>
                      {picked && <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-emerald-500/90 flex items-center justify-center"><Check size={11} className="text-white" /></div>}
                      {matched && !picked && <div className="absolute top-1 right-1 px-1 rounded bg-primary/80 text-[8px] font-bold text-white">검색</div>}
                      <div className="px-1.5 py-1 bg-black/40">
                        <p className="text-[9px] text-white/80 truncate">{f.display_name?.split(" · ")[1] ?? fmt(f.start)}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <p className="text-[11px] text-muted-foreground/40">아직 선택된 원본이 없습니다.</p>
          )}
        </div>

        {/* 하단: Basket */}
        <div className="rounded-xl border border-border/15 bg-card/20 flex-shrink-0 max-h-[38%] flex flex-col">
          <div className="px-4 py-2.5 border-b border-border/10 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShoppingBasket size={14} className="text-primary" />
              <p className="text-xs font-bold text-foreground/90">바구니</p>
              <span className="text-[11px] text-muted-foreground/50">{basketItems.length}개 · {basketTotal.toFixed(1)}초</span>
            </div>
            <button disabled title="다음 단계에서 제공됩니다 — 바구니 조각으로 새 프로젝트 만들기"
              className="px-2.5 py-1 rounded-md bg-secondary/40 text-muted-foreground/40 text-[10px] font-bold opacity-60 cursor-not-allowed">
              프로젝트로 보내기 (다음 단계)
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-2">
            {basketItems.length === 0 ? (
              <p className="text-[11px] text-muted-foreground/40">담은 조각이 없습니다. 검색 결과나 조각맵에서 조각을 담아보세요.</p>
            ) : (
              <div className="space-y-1.5">
                {basketItems.map(b => (
                  <div key={b.fragment_id} className="flex items-center gap-2 p-1.5 rounded-lg bg-card/40 border border-border/10">
                    <div className="w-12 h-8 flex-shrink-0 rounded bg-primary/10 overflow-hidden flex items-center justify-center">
                      {b.thumbnail_url ? <img src={b.thumbnail_url} className="w-full h-full object-cover" draggable={false} /> : <Film size={12} className="text-primary" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[11px] font-semibold text-foreground/85 truncate">{b.display_name || b.fragment_id}</p>
                      <p className="text-[9px] text-muted-foreground/50">{fmt(b.start)}–{fmt(b.end)}</p>
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
    </div>
  );
};
