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

export const SettingsPanel: React.FC = () => {
  const [diag, setDiag] = useState<SystemDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
  }, []);

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
      </div>
    </div>
  );
};

export default SettingsPanel;
