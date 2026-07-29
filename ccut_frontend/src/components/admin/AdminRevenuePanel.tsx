import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { fetcher } from "@/services/api";
import { AppDialog } from "@/components/AppDialog";

// [War Room v1] 수익/구독/포인트 — 구독 요약(v0 유지) + 포인트 원장 + 상품 카탈로그.
// provider 연동 전 원장은 "준비 중" 정직 표시. 상품 공개는 승인(approved) 전이 필수.

interface RevenueSummary {
  status: string;
  total?: number | null;
  message?: string;
  metrics?: { metric_key: string; days: number; total: number }[];
  metric_days_recorded?: number;
}

interface PointsSummary {
  status: string;
  total?: number | null;
  message?: string;
  by_type?: { event_type: string; count: number; points: number }[];
}

interface Product {
  product_id: string;
  kind: string;
  name: string;
  status: string;
  price: number | null;
  currency: string | null;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-secondary/40 text-muted-foreground/70",
  approved: "bg-amber-500/15 text-amber-400",
  published: "bg-emerald-500/15 text-emerald-400",
  retired: "bg-secondary/20 text-muted-foreground/40",
};

export const AdminRevenuePanel: React.FC = () => {
  const [summary, setSummary] = useState<RevenueSummary | null>(null);
  const [points, setPoints] = useState<PointsSummary | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ product_id: "", kind: "subscription", name: "", price: "" });
  const [showForm, setShowForm] = useState(false);
  const [publishConfirm, setPublishConfirm] = useState<{ id: string; status: string } | null>(null);

  const load = () => {
    fetcher("/admin/revenue/summary").then(setSummary).catch(e => setError(String(e)));
    fetcher("/admin/revenue/points").then(setPoints).catch(e => setError(String(e)));
    fetcher("/admin/revenue/products").then(r => setProducts(r.products ?? [])).catch(e => setError(String(e)));
  };
  useEffect(load, []);

  const create = async () => {
    if (!form.product_id.trim() || !form.name.trim()) return;
    const r = await fetcher("/admin/revenue/products", {
      method: "POST",
      body: JSON.stringify({ ...form, price: form.price ? Number(form.price) : null }),
    }).catch(e => ({ error: String(e) }));
    if (r.error) { setError(r.error); return; }
    setForm({ product_id: "", kind: "subscription", name: "", price: "" });
    setShowForm(false);
    load();
  };

  const runTransition = async (id: string, status: string) => {
    const r = await fetcher(`/admin/revenue/products/${encodeURIComponent(id)}/status`, {
      method: "POST", body: JSON.stringify({ status }),
    }).catch(e => ({ error: String(e) }));
    if (r.error) setError(r.error);
    load();
  };

  const transition = async (id: string, status: string) => {
    if (status === "published") {
      setPublishConfirm({ id, status });
      return;
    }
    await runTransition(id, status);
  };

  return (
    <div className="space-y-6">
      <AppDialog
        open={!!publishConfirm}
        message={publishConfirm ? `상품 "${publishConfirm.id}"을(를) 공개(published)합니다. 진행할까요?` : ""}
        confirmText="OK"
        cancelText="Cancel"
        onCancel={() => setPublishConfirm(null)}
        onConfirm={() => {
          const next = publishConfirm;
          setPublishConfirm(null);
          if (next) runTransition(next.id, next.status);
        }}
      />
      <div>
        <h1 className="text-lg font-bold text-foreground/90">수익/구독/포인트</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">
          구독·포인트 원장 + 상품 카탈로그 (공개는 승인 전이 필수)
        </p>
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {/* 구독 요약 */}
      <div>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">구독 요약</h2>
        {!summary ? (
          <p className="text-[11px] text-muted-foreground/50 animate-pulse">집계 중...</p>
        ) : summary.status === "준비 중" ? (
          <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-4">
            <p className="text-sm font-bold text-amber-300">구독 데이터 준비 중</p>
            <p className="text-[11px] text-muted-foreground/60 mt-1">{summary.message}</p>
          </div>
        ) : (
          <div className="rounded-lg border border-border/15 divide-y divide-border/10">
            {(summary.metrics ?? []).map(m => (
              <div key={m.metric_key} className="px-4 py-2.5 flex items-center justify-between text-xs">
                <span className="font-mono text-foreground/80">{m.metric_key}</span>
                <span className="font-bold text-foreground/90">{m.total?.toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 포인트 */}
      <div>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">포인트 원장</h2>
        {!points ? (
          <p className="text-[11px] text-muted-foreground/50 animate-pulse">집계 중...</p>
        ) : points.status === "준비 중" ? (
          <p className="text-[11px] text-muted-foreground/40">{points.message}</p>
        ) : (
          <div className="rounded-lg border border-border/15 divide-y divide-border/10">
            {(points.by_type ?? []).map(p => (
              <div key={p.event_type} className="px-4 py-2.5 flex items-center justify-between text-xs">
                <span className="font-mono text-foreground/80">{p.event_type}</span>
                <span className="text-muted-foreground/50">{p.count}건</span>
                <span className="font-bold text-foreground/90">{p.points.toLocaleString()}P</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 상품 카탈로그 */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50">상품 카탈로그</h2>
          <button onClick={() => setShowForm(v => !v)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-400 text-[11px] font-bold hover:bg-emerald-500/25 transition-colors">
            <Plus size={11} /> 상품 초안
          </button>
        </div>

        {showForm && (
          <div className="rounded-lg border border-border/15 bg-card/20 p-4 grid grid-cols-2 gap-2 mb-3">
            <input value={form.product_id} onChange={e => setForm(f => ({ ...f, product_id: e.target.value }))}
              placeholder="product_id (예: plan_pro_m)"
              className="h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="상품명"
              className="h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
            <select value={form.kind} onChange={e => setForm(f => ({ ...f, kind: e.target.value }))}
              className="h-8 rounded-md bg-secondary/30 border border-border/15 px-2 text-xs text-foreground/90 outline-none">
              <option value="subscription">subscription</option>
              <option value="point_pack">point_pack</option>
              <option value="addon">addon</option>
            </select>
            <div className="flex gap-2">
              <input value={form.price} onChange={e => setForm(f => ({ ...f, price: e.target.value }))}
                placeholder="가격(숫자)"
                className="flex-1 h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
              <button onClick={create}
                className="px-3 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors">
                초안 등록
              </button>
            </div>
          </div>
        )}

        {products.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">상품 카탈로그가 비어 있습니다.</p>
        ) : (
          <div className="rounded-lg border border-border/15 divide-y divide-border/10">
            {products.map(p => (
              <div key={p.product_id} className="px-3 py-2.5 flex items-center gap-3 text-xs">
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-black ${STATUS_STYLE[p.status] ?? STATUS_STYLE.draft}`}>
                  {p.status}
                </span>
                <span className="font-mono text-muted-foreground/50">{p.product_id}</span>
                <span className="text-foreground/85 truncate flex-1">{p.name}</span>
                <span className="text-muted-foreground/50">{p.kind}</span>
                {p.price != null && <span className="font-bold text-foreground/80">{p.price.toLocaleString()}{p.currency ?? ""}</span>}
                {p.status === "draft" && (
                  <button onClick={() => transition(p.product_id, "approved")}
                    className="px-2 py-1 rounded-md bg-amber-500/15 text-amber-400 text-[10px] font-bold hover:bg-amber-500/25 transition-colors">승인</button>
                )}
                {p.status === "approved" && (
                  <button onClick={() => transition(p.product_id, "published")}
                    className="px-2 py-1 rounded-md bg-emerald-500/15 text-emerald-400 text-[10px] font-bold hover:bg-emerald-500/25 transition-colors">공개</button>
                )}
                {p.status !== "retired" && (
                  <button onClick={() => transition(p.product_id, "retired")}
                    className="px-2 py-1 rounded-md bg-secondary/40 text-muted-foreground/60 text-[10px] font-bold hover:bg-secondary/70 transition-colors">종료</button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
