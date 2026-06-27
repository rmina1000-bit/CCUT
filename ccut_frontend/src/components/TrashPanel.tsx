import React, { useState, useEffect, useCallback } from "react";
import { Trash2, Trash, RotateCcw, AlertTriangle, RefreshCw } from "lucide-react";
import { videoService } from "@/services/videoService";

interface TrashItem {
  program_id: string;
  name?: string | null;
  deleted_at?: string | null;
  purge_at?: string | null;
  days_left?: number;
}

export const TrashPanel: React.FC = () => {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  // 확인 모달: { kind: "purge", id } | { kind: "empty" } | null
  const [confirm, setConfirm] = useState<{ kind: "purge" | "empty"; id?: string; name?: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res: any = await videoService.listTrash();
      setItems(Array.isArray(res?.trash) ? res.trash : []);
    } catch (e) {
      console.error("[TRASH] load fail", e);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRestore = async (id: string) => {
    setBusyId(id);
    try {
      await videoService.restoreProject(id);
      await load();
    } catch (e) {
      console.error("[TRASH] restore fail", e);
    } finally {
      setBusyId(null);
    }
  };

  const handlePurge = async (id: string) => {
    setBusyId(id);
    try {
      await videoService.purgeProject(id);
      await load();
    } catch (e) {
      console.error("[TRASH] purge fail", e);
    } finally {
      setBusyId(null);
      setConfirm(null);
    }
  };

  const handleEmpty = async () => {
    const targets = items.map((i) => i.program_id);
    try {
      for (const id of targets) {
        await videoService.purgeProject(id);
      }
      await load();
    } catch (e) {
      console.error("[TRASH] empty fail", e);
    } finally {
      setConfirm(null);
    }
  };

  const fmtDate = (s?: string | null) => {
    if (!s) return "";
    try {
      const d = new Date(s);
      return `${d.getFullYear()}. ${d.getMonth() + 1}. ${d.getDate()}.`;
    } catch { return ""; }
  };

  const isEmpty = !loading && items.length === 0;

  return (
    <div className="flex flex-col h-full bg-[hsl(228_10%_9%)] p-6 space-y-5 overflow-y-auto">
      {/* 헤더 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent flex items-center gap-2">
            <Trash2 size={22} className="text-primary" /> 휴지통
          </h1>
          <p className="text-[12px] text-muted-foreground/60 mt-1">
            삭제된 프로젝트는 30일간 보관 후 자동으로 완전히 삭제됩니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium bg-card/40 hover:bg-card/60 border border-border/15 text-muted-foreground transition-colors"
          >
            <RefreshCw size={13} /> 새로고침
          </button>
          <button
            onClick={() => setConfirm({ kind: "empty" })}
            disabled={items.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold bg-red-500/15 hover:bg-red-500/25 border border-red-500/25 text-red-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Trash2 size={13} /> 휴지통 비우기
          </button>
        </div>
      </div>
      {/* 본문 */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-muted-foreground/50 text-[13px]">
          불러오는 중...
        </div>
      ) : isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center py-20">
          <Trash size={64} className="text-muted-foreground/25 mb-4" strokeWidth={1.2} />
          <p className="text-[14px] text-muted-foreground/50">휴지통이 비어 있습니다.</p>
          <p className="text-[12px] text-muted-foreground/30 mt-1">삭제한 프로젝트가 여기에 보관됩니다.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <div
              key={it.program_id}
              className="flex items-center justify-between gap-4 px-4 py-3 rounded-xl bg-card/30 border border-border/15 hover:bg-card/40 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-red-500/10 shrink-0">
                  <Trash2 size={16} className="text-red-400/70" />
                </div>
                <div className="min-w-0">
                  <div className="text-[14px] font-semibold text-foreground/90 truncate">
                    {it.name || it.program_id}
                  </div>
                  <div className="text-[11px] text-muted-foreground/50 mt-0.5">
                    삭제일 {fmtDate(it.deleted_at)} · 영구삭제까지 {Math.max(0, it.days_left ?? 0)}일
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => handleRestore(it.program_id)}
                  disabled={busyId === it.program_id}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-[12px] font-semibold text-emerald-400 transition-colors disabled:opacity-40"
                >
                  <RotateCcw size={12} /> 복원
                </button>
                <button
                  onClick={() => setConfirm({ kind: "purge", id: it.program_id, name: it.name || it.program_id })}
                  disabled={busyId === it.program_id}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/15 hover:bg-red-500/25 text-[12px] font-semibold text-red-400 transition-colors disabled:opacity-40"
                >
                  <Trash2 size={12} /> 영구삭제
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {/* 확인 모달 (자체 오버레이 — 코드베이스 관행) */}
      {confirm && (
        <div className="fixed inset-0 z-[500] bg-black/75 flex items-center justify-center p-4">
          <div className="bg-[hsl(228,12%,12%)] border border-border/20 max-w-sm w-full rounded-2xl p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-full flex items-center justify-center bg-red-500/15 shrink-0">
                <AlertTriangle size={20} className="text-red-400" />
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-foreground">
                  {confirm.kind === "empty" ? "휴지통을 비우시겠습니까?" : "영구 삭제하시겠습니까?"}
                </h3>
                <p className="text-[12px] text-muted-foreground/60 mt-0.5">이 작업은 되돌릴 수 없습니다.</p>
              </div>
            </div>
            <div className="text-[13px] text-muted-foreground/80 bg-red-500/[0.06] border border-red-500/15 rounded-lg px-3 py-2.5">
              {confirm.kind === "empty"
                ? `휴지통의 ${items.length}개 프로젝트가 영구적으로 완전히 삭제됩니다. 누구도 되살릴 수 없습니다.`
                : `"${confirm.name}" 프로젝트가 영구적으로 완전히 삭제됩니다. 누구도 되살릴 수 없습니다.`}
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setConfirm(null)}
                className="px-4 py-2 rounded-lg text-[13px] font-medium bg-card/50 hover:bg-card/70 text-muted-foreground transition-colors"
              >
                취소 (안전)
              </button>
              <button
                onClick={() => (confirm.kind === "empty" ? handleEmpty() : handlePurge(confirm.id!))}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[13px] font-semibold bg-red-500 hover:bg-red-600 text-white transition-colors"
              >
                <Trash2 size={13} /> {confirm.kind === "empty" ? "비우기" : "삭제하겠습니다"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TrashPanel;
