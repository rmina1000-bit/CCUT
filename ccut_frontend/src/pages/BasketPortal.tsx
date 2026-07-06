import React, { useState, useEffect, useRef } from "react";
import { ShoppingBasket, X, Film, FolderInput } from "lucide-react";
import type { BasketItem } from "@/lib/archiveWorkbenchStore";

/**
 * [바구니 새창 국장지시 2026-07-06 C] 휴지통 전용창(TrashPortal) 구조 참조.
 * 메인 작업대 바구니와 BroadcastChannel("ccut_basket_sync")로 동기화.
 * 프로젝트 이동(드래그)은 이번엔 껍데기만 — 실제 연결은 다음 단계.
 */
const fmt = (sec: number | null) => {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

const BasketPortal: React.FC = () => {
  const [items, setItems] = useState<BasketItem[]>([]);
  const [connected, setConnected] = useState(false);
  const bcRef = useRef<BroadcastChannel | null>(null);

  useEffect(() => {
    const bc = new BroadcastChannel("ccut_basket_sync");
    bcRef.current = bc;
    bc.onmessage = (e) => {
      if (e.data?.type === "UPDATE_BASKET") {
        setItems(e.data.items ?? []);
        setConnected(true);
      }
    };
    bc.postMessage({ type: "REQUEST_BASKET" });      // 초기 상태 요청
    return () => bc.close();
  }, []);

  const remove = (fid: string) => {
    bcRef.current?.postMessage({ type: "REMOVE_ITEM", fragment_id: fid });
  };

  const total = items.reduce((s, b) => s + (b.start != null && b.end != null ? Math.max(0, b.end - b.start) : 0), 0);

  return (
    <div className="min-h-screen bg-[hsl(228,12%,8%)] text-foreground flex flex-col font-sans">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border/15 bg-card/10">
        <div className="flex items-center gap-3">
          <ShoppingBasket size={22} className="text-primary" />
          <h1 className="text-lg font-bold tracking-tight">바구니 전용창</h1>
          <span className="text-xs bg-primary/10 text-primary/80 px-2 py-0.5 rounded-full">
            {items.length}개 · {total.toFixed(1)}초
          </span>
          {!connected && <span className="text-[11px] text-muted-foreground/40">메인 창과 연결 대기…</span>}
        </div>
        <button disabled title="다음 단계에서 제공됩니다 — 바구니 조각을 프로젝트로 이동"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/40 text-muted-foreground/40 text-xs font-bold opacity-60 cursor-not-allowed">
          <FolderInput size={13} /> 프로젝트로 이동 (다음)
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {items.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-3 text-muted-foreground/30">
            <ShoppingBasket size={40} strokeWidth={1} />
            <p className="text-sm">담긴 조각이 없습니다.</p>
            <p className="text-[11px] text-muted-foreground/40">메인 작업대에서 조각을 담으면 여기 실시간으로 나타납니다.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {items.map(b => (
              <div key={b.fragment_id} className="rounded-lg border border-border/15 bg-card/20 overflow-hidden group">
                <div className="aspect-video bg-black/50 relative">
                  {b.thumbnail_url ? <img src={b.thumbnail_url} className="w-full h-full object-cover" draggable={false} /> : <div className="w-full h-full flex items-center justify-center"><Film size={18} className="text-muted-foreground/40" /></div>}
                  <button onClick={() => remove(b.fragment_id)} title="바구니에서 빼기"
                    className="absolute top-1.5 right-1.5 w-6 h-6 rounded-md bg-black/60 hover:bg-red-500/70 text-white/90 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <X size={13} />
                  </button>
                </div>
                <div className="px-2.5 py-2">
                  <p className="text-[11px] font-semibold text-foreground/85 truncate">{b.display_name || b.fragment_id}</p>
                  <p className="text-[10px] text-muted-foreground/50 truncate">{b.source_title} · {fmt(b.start)}–{fmt(b.end)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default BasketPortal;
