import React, { useEffect, useState } from "react";
import { fetcher } from "@/services/api";

// [War Room v1] 행동 분석 — 실 원장 created_at 일별 집계만.
// 세그먼트/지역/연령 분석은 원장 미도입 — 정직 표기.

interface ActivityDay {
  date: string;
  sources: number;
  proposals: number;
  exports: number;
}

export const AdminAnalyticsPanel: React.FC = () => {
  const [days, setDays] = useState<ActivityDay[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetcher("/admin/analytics/activity?days=14")
      .then(r => { setDays(r.days ?? []); setNote(r.note ?? ""); })
      .catch(e => setError(String(e)));
  }, []);

  if (error) return <p className="text-xs text-red-400">analytics 조회 실패: {error}</p>;

  const max = Math.max(1, ...days.map(d => d.sources + d.proposals + d.exports));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold text-foreground/90">행동 분석</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">{note}</p>
      </div>

      <div className="rounded-lg border border-border/15 bg-card/20 p-4">
        <div className="flex items-end gap-1 h-32">
          {days.map(d => {
            const total = d.sources + d.proposals + d.exports;
            return (
              <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group"
                title={`${d.date} — 원본 ${d.sources} · 제안 ${d.proposals} · 내보내기 ${d.exports}`}>
                <div className="w-full flex flex-col justify-end" style={{ height: "100px" }}>
                  {total > 0 && (
                    <>
                      {d.exports > 0 && <div className="w-full bg-emerald-500/60" style={{ height: `${(d.exports / max) * 100}px` }} />}
                      {d.proposals > 0 && <div className="w-full bg-primary/60" style={{ height: `${(d.proposals / max) * 100}px` }} />}
                      {d.sources > 0 && <div className="w-full bg-blue-400/60" style={{ height: `${(d.sources / max) * 100}px` }} />}
                    </>
                  )}
                </div>
                <span className="text-[8px] text-muted-foreground/40 rotate-0">{d.date.slice(5)}</span>
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-4 mt-3 text-[10px] text-muted-foreground/50">
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-blue-400/60 rounded-sm" /> 원본 업로드</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-primary/60 rounded-sm" /> 편집 제안</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-emerald-500/60 rounded-sm" /> 내보내기</span>
        </div>
      </div>

      <div className="rounded-lg border border-border/15 overflow-hidden">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="bg-secondary/20 text-muted-foreground/50 text-left">
              <th className="px-3 py-2 font-semibold">날짜</th>
              <th className="px-3 py-2 font-semibold text-right">원본</th>
              <th className="px-3 py-2 font-semibold text-right">제안</th>
              <th className="px-3 py-2 font-semibold text-right">내보내기</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/10">
            {[...days].reverse().map(d => (
              <tr key={d.date} className="hover:bg-secondary/10">
                <td className="px-3 py-1.5 font-mono text-muted-foreground/60">{d.date}</td>
                <td className="px-3 py-1.5 text-right text-foreground/80">{d.sources || "—"}</td>
                <td className="px-3 py-1.5 text-right text-foreground/80">{d.proposals || "—"}</td>
                <td className="px-3 py-1.5 text-right text-foreground/80">{d.exports || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] text-muted-foreground/40">
        세그먼트(지역/연령/그룹) 분석은 해당 원장 미도입 — 대규모화 단계에서 연결됩니다.
      </p>
    </div>
  );
};
