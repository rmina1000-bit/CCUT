import React, { useEffect, useState, useCallback } from "react";
import { RefreshCw, CheckCircle2, XCircle, AlertTriangle, Cpu } from "lucide-react";
import { videoService, SystemDiagnostics } from "@/services/videoService";

// [FIX-RUNTIME-1b] GPU ASR 런타임 환경진단 화면 (베타 최소 표시).
// 백엔드 /system/diagnostics 를 소비·표시만 한다(read 전용).

const STATUS_META: Record<string, { label: string; cls: string; icon: React.ReactNode }> = {
  ok: { label: "정상", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30", icon: <CheckCircle2 size={16} /> },
  warning: { label: "주의", cls: "bg-amber-500/15 text-amber-400 border-amber-500/30", icon: <AlertTriangle size={16} /> },
  fail: { label: "실패", cls: "bg-red-500/15 text-red-400 border-red-500/30", icon: <XCircle size={16} /> },
};

const BoolDot: React.FC<{ ok: boolean }> = ({ ok }) =>
  ok ? (
    <span className="inline-flex items-center gap-1 text-emerald-400 text-[13px]">
      <CheckCircle2 size={14} /> 정상
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-red-400 text-[13px]">
      <XCircle size={14} /> 없음
    </span>
  );

const fmtBytes = (b?: number | null) => {
  if (b == null) return "—";
  if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(1)} GB`;
  if (b >= 1024 ** 2) return `${(b / 1024 ** 2).toFixed(0)} MB`;
  return `${Math.ceil(b / 1024)} KB`;
};

// [SETTINGS] 다른 편집 프로그램(CapCut/Premiere/Descript) 공통 골격 분석 반영:
// 저장 공간 관리 / 엔진(AI) 상태 / 기능 스위치 상태 — 전부 실데이터, 가짜 토글 없음.
export const SettingsPanel: React.FC = () => {
  const [diag, setDiag] = useState<SystemDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [storage, setStorage] = useState<{ items: Array<{ label: string; bytes: number }>; disk_free_bytes: number | null } | null>(null);
  const [gates, setGates] = useState<Record<string, string> | null>(null);
  const [cleaning, setCleaning] = useState<string | null>(null);
  const [cleanNote, setCleanNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await videoService.getSystemDiagnostics();
      setDiag(d);
    } catch (e) {
      setError("진단 정보를 불러올 수 없습니다. 백엔드 서버(127.0.0.1:8000) 상태를 확인하세요.");
      setDiag(null);
    } finally {
      setLoading(false);
    }
    try {
      const s = await fetch("/api/settings/storage").then((r) => r.json());
      if (s?.status === "OK") setStorage(s);
      const g = await fetch("/api/settings/gates").then((r) => r.json());
      if (g?.status === "OK") setGates(g.gates);
    } catch { /* 표시만 생략 */ }
  }, []);

  const cleanup = async (target: string, label: string) => {
    if (!window.confirm(`${label}을(를) 비울까요?\n(전부 자동으로 다시 만들어지는 캐시입니다)`)) return;
    setCleaning(target);
    try {
      const r = await fetch("/api/settings/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target }),
      }).then((x) => x.json());
      if (r?.status === "OK") {
        setCleanNote(`${label}: 파일 ${r.removed}개, ${fmtBytes(r.freed_bytes)} 비웠습니다.`);
        load();
      }
    } finally {
      setCleaning(null);
    }
  };

  useEffect(() => {
    load();
  }, [load]);

  const rows: Array<{ label: string; node: React.ReactNode }> = diag
    ? [
        { label: "음성분석 엔진", node: <span className="text-[13px] text-foreground font-medium">{diag.current_asr_provider}</span> },
        { label: "GPU 가속 (Vulkan)", node: <BoolDot ok={!!diag.whisper_vulkan_health?.ok} /> },
        { label: "실행기 (whisper-cli)", node: <BoolDot ok={diag.cli_path_exists} /> },
        { label: "음성모델 (small)", node: <BoolDot ok={diag.model_path_exists} /> },
        { label: "예비 모델 (base)", node: <BoolDot ok={diag.fallback_model_path_exists} /> },
        { label: "영상처리 (ffmpeg)", node: <BoolDot ok={diag.ffmpeg_available} /> },
        { label: "런타임 폴더", node: <BoolDot ok={diag.runtime_dir_exists} /> },
        {
          label: "저장공간 여유",
          node: (
            <span className="text-[13px] text-foreground">
              {diag.storage_free_gb != null ? `${diag.storage_free_gb} GB` : "—"}
            </span>
          ),
        },
        { label: "CPU 폴백 가능", node: <BoolDot ok={diag.cpu_fallback_available} /> },
      ]
    : [];

  const sm = diag ? STATUS_META[diag.status] ?? STATUS_META.warning : null;

  return (
    <div className="h-full w-full overflow-y-auto bg-[hsl(228,14%,8%)] text-foreground">
      <div className="max-w-[720px] mx-auto px-8 py-8">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-[18px] font-bold flex items-center gap-2">
            <Cpu size={18} className="text-primary" /> 환경 진단
          </h1>
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-border/30 text-foreground/70 hover:text-foreground hover:bg-secondary/40 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> 다시 확인
          </button>
        </div>
        <p className="text-[12px] text-muted-foreground mb-5">GPU 음성분석(whisper.cpp Vulkan) 런타임 상태</p>

        {loading && !diag && (
          <div className="text-[13px] text-muted-foreground py-10 text-center">진단 중…</div>
        )}

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-[13px] text-red-400">
            {error}
          </div>
        )}

        {diag && (
          <>
            {sm && (
              <div className={`inline-flex items-center gap-1.5 text-[13px] font-semibold px-3 py-1.5 rounded-lg border mb-5 ${sm.cls}`}>
                {sm.icon} 종합 상태: {sm.label}
              </div>
            )}
            <div className="rounded-xl border border-border/15 bg-[hsl(228,12%,10%)] divide-y divide-border/10 overflow-hidden">
              {rows.map((r) => (
                <div key={r.label} className="flex items-center justify-between px-4 py-3">
                  <span className="text-[13px] text-foreground/70">{r.label}</span>
                  {r.node}
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── 저장 공간 (실측) ───────────────────────────────── */}
        {storage && (
          <div className="mt-8">
            <h2 className="text-[15px] font-bold mb-1">저장 공간</h2>
            <p className="text-[12px] text-muted-foreground mb-3">
              디스크 여유 {fmtBytes(storage.disk_free_bytes)} · 아래는 CCUT이 실제로 쓰고 있는 용량입니다.
            </p>
            <div className="rounded-xl border border-border/15 bg-[hsl(228,12%,10%)] divide-y divide-border/10 overflow-hidden">
              {storage.items.map((it) => (
                <div key={it.label} className="flex items-center justify-between px-4 py-2.5">
                  <span className="text-[13px] text-foreground/70">{it.label}</span>
                  <span className="text-[13px] text-foreground font-mono">{fmtBytes(it.bytes)}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={() => cleanup("previews", "제안 미리보기 캐시")}
                disabled={cleaning !== null}
                className="text-[12px] px-3 py-1.5 rounded-lg border border-border/30 text-foreground/70 hover:text-foreground hover:bg-secondary/40 transition-colors disabled:opacity-50"
              >
                {cleaning === "previews" ? "비우는 중…" : "미리보기 캐시 비우기"}
              </button>
              <button
                onClick={() => cleanup("panorama", "파노라마 프레임 캐시")}
                disabled={cleaning !== null}
                className="text-[12px] px-3 py-1.5 rounded-lg border border-border/30 text-foreground/70 hover:text-foreground hover:bg-secondary/40 transition-colors disabled:opacity-50"
              >
                {cleaning === "panorama" ? "비우는 중…" : "파노라마 캐시 비우기"}
              </button>
            </div>
            {cleanNote && <p className="text-[12px] text-emerald-400 mt-2">{cleanNote}</p>}
            <p className="text-[11px] text-muted-foreground/50 mt-1.5">
              두 캐시 모두 필요할 때 자동으로 다시 생성됩니다. 원본 영상·프로젝트는 건드리지 않습니다.
            </p>
          </div>
        )}

        {/* ── 기능 스위치 상태 (읽기 전용 — 검증 게이트) ─────────── */}
        {gates && (
          <div className="mt-8 mb-10">
            <h2 className="text-[15px] font-bold mb-1">기능 스위치</h2>
            <p className="text-[12px] text-muted-foreground mb-3">
              편집 판단 엔진의 켜짐/꺼짐 상태입니다. (안정성 검증을 거친 것만 켜져 있습니다)
            </p>
            <div className="rounded-xl border border-border/15 bg-[hsl(228,12%,10%)] divide-y divide-border/10 overflow-hidden">
              {Object.entries({
                CCUT_HUB_PLAN: "지시 이해 엔진 (허브 판단)",
                CCUT_AUTO_REINDEX: "장면 자동 재분석",
                CCUT_SINGLE_CACHE: "판단 결과 기억 (속도)",
                CCUT_LEGACY_NARRATIVE: "구형 해석기 (차단 권장)",
                CCUT_REVISION: "수정 명령 (베타)",
                CCUT_QUALITY_LOG: "품질 신호 수집 (베타)",
                CCUT_PERSON_REQUERY: "인물 재확인 (베타)",
              }).map(([k, label]) => {
                const on = ["1", "true", "True"].includes(gates[k] ?? "");
                const good = k === "CCUT_LEGACY_NARRATIVE" ? !on : on;
                return (
                  <div key={k} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-[13px] text-foreground/70">{label}</span>
                    <span className={`text-[12px] font-bold ${on ? (good ? "text-emerald-400" : "text-amber-400") : (good ? "text-muted-foreground/50" : "text-muted-foreground/50")}`}>
                      {on ? "켜짐" : "꺼짐"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPanel;
