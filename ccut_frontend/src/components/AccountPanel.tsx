import React, { useEffect, useState } from "react";
import { User, Film, Clock, Scissors, Upload, Users, Youtube, RefreshCw, Pencil } from "lucide-react";

/* [ACCOUNT] 다른 편집 프로그램(CapCut/Descript 등) 계정 화면 골격 분석 반영:
   프로필 / 사용 통계 / 연결된 채널. 전부 실데이터 — 가짜 로그인·결제 시뮬레이션 제거. */

interface Stats {
  projects: number;
  sources: number;
  total_video_sec: number;
  fragments: number;
  exports: number;
  published: number;
  named_persons: number;
  person_names: string[];
}

const fmtDur = (s: number) => {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}시간 ${m}분`;
  return `${m}분 ${Math.round(s % 60)}초`;
};

export const AccountPanel: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [yt, setYt] = useState<{ configured: boolean; connected: boolean; channel_title: string | null } | null>(null);
  const [name, setName] = useState<string>(() => localStorage.getItem("ccut_profile_name") || "국장님");
  const [editingName, setEditingName] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const s = await fetch("/api/account/stats").then((r) => r.json());
      if (s?.status === "OK") setStats(s.stats);
      const y = await fetch("/api/sns/youtube/status").then((r) => r.json());
      setYt(y);
    } catch { /* 백엔드 꺼짐 */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const saveName = (v: string) => {
    const n = v.trim() || "국장님";
    setName(n);
    localStorage.setItem("ccut_profile_name", n);
    setEditingName(false);
  };

  const statCards = stats ? [
    { icon: Film, label: "프로젝트", value: `${stats.projects}개` },
    { icon: Upload, label: "원본 영상", value: `${stats.sources}개 · ${fmtDur(stats.total_video_sec)}` },
    { icon: Scissors, label: "의미 조각", value: `${stats.fragments.toLocaleString()}개` },
    { icon: Clock, label: "내보낸 영상", value: `${stats.exports}개` },
    { icon: Youtube, label: "SNS 발행", value: `${stats.published}회` },
    { icon: Users, label: "기억하는 사람", value: stats.named_persons > 0 ? `${stats.named_persons}명 (${stats.person_names.join(", ")})` : "아직 없음" },
  ] : [];

  return (
    <div className="h-full w-full overflow-y-auto bg-[hsl(228,14%,8%)] text-foreground">
      <div className="max-w-[720px] mx-auto px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-[18px] font-bold flex items-center gap-2">
            <User size={18} className="text-primary" /> 내 계정
          </h1>
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-border/30 text-foreground/70 hover:text-foreground hover:bg-secondary/40 transition-colors"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> 새로고침
          </button>
        </div>

        {/* 프로필 */}
        <div className="flex items-center gap-4 rounded-xl border border-border/15 bg-[hsl(228,12%,10%)] px-5 py-4 mb-6">
          <div className="w-14 h-14 rounded-full bg-primary/15 flex items-center justify-center text-primary text-xl font-black">
            {name.slice(0, 1)}
          </div>
          <div className="flex-1">
            {editingName ? (
              <input
                autoFocus
                defaultValue={name}
                onBlur={(e) => saveName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") saveName((e.target as HTMLInputElement).value); }}
                className="text-[16px] font-bold bg-transparent border-b border-primary/50 outline-none"
              />
            ) : (
              <button onClick={() => setEditingName(true)} className="flex items-center gap-1.5 text-[16px] font-bold hover:text-primary transition-colors">
                {name} <Pencil size={12} className="opacity-40" />
              </button>
            )}
            <p className="text-[12px] text-muted-foreground/60 mt-0.5">이 PC의 CCUT 작업실 (모든 데이터는 내 컴퓨터에만 저장)</p>
          </div>
        </div>

        {/* 사용 통계 (실데이터) */}
        <h2 className="text-[14px] font-bold mb-3">작업 기록</h2>
        <div className="grid grid-cols-2 gap-3 mb-8">
          {statCards.map(({ icon: Icon, label, value }) => (
            <div key={label} className="rounded-xl border border-border/15 bg-[hsl(228,12%,10%)] px-4 py-3.5 flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Icon size={15} className="text-primary" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] text-muted-foreground/60">{label}</p>
                <p className="text-[13px] font-bold text-foreground truncate">{value}</p>
              </div>
            </div>
          ))}
          {!stats && !loading && (
            <p className="col-span-2 text-[12px] text-muted-foreground/50">통계를 불러오지 못했습니다 — 백엔드 상태를 확인하세요.</p>
          )}
        </div>

        {/* 연결된 채널 */}
        <h2 className="text-[14px] font-bold mb-3">연결된 채널</h2>
        <div className="rounded-xl border border-border/15 bg-[hsl(228,12%,10%)] px-5 py-4 flex items-center gap-3">
          <Youtube size={18} className="text-red-500" />
          {yt?.connected ? (
            <span className="text-[13px] text-foreground">YouTube — <b>{yt.channel_title}</b> 연결됨</span>
          ) : yt?.configured ? (
            <span className="text-[13px] text-muted-foreground/70">YouTube — 설정됨, 미연결 (SNS 업로드 탭에서 연결)</span>
          ) : (
            <span className="text-[13px] text-muted-foreground/50">YouTube — 미설정 (SNS 업로드 탭에 준비 안내)</span>
          )}
        </div>
      </div>
    </div>
  );
};

export default AccountPanel;
