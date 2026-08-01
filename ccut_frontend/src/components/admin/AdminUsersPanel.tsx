import React, { useEffect, useState } from "react";
import { AdminLockedNotice } from "./AdminLockedNotice";
import { fetcher } from "@/services/api";

// [Admin v0] 사용자 운영 — 로컬 단일 사용자 환경: 운영자 1인 + 실사용 통계.
interface AdminUser {
  user_id: string;
  display_name: string | null;
  role: string | null;
  plan: string | null;
  [k: string]: unknown;
}

const STAT_LABELS: Record<string, string> = {
  source_count: "원본",
  program_count: "프로젝트",
  proposal_count: "제안",
  vault_event_count: "조각 사건",
  fragment_vault_count: "인지 조각",
  export_success_count: "내보내기",
  person_count: "인물",
  first_activity: "첫 활동",
  last_activity: "최근 활동",
};

export const AdminUsersPanel: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [noteSaved, setNoteSaved] = useState<string | null>(null);

  useEffect(() => {
    fetcher("/admin/users")
      .then(r => setUsers(r.users ?? []))
      .catch(e => setError(String(e)));
  }, []);

  const addNote = async (userId: string) => {
    const t = noteText.trim();
    if (!t) return;
    try {
      await fetcher(`/admin/users/${encodeURIComponent(userId)}/note`, {
        method: "POST",
        body: JSON.stringify({ note: t }),
      });
      setNoteSaved(t);
      setNoteText("");
    } catch (e) {
      setError(String(e));
    }
  };

  if (error) return <p className="text-xs text-red-400">users 조회 실패: {error}</p>;

  return (
    <div className="space-y-6">
      <AdminLockedNotice tab="users" />
      <div>
        <h1 className="text-lg font-bold text-foreground/90">사용자 운영</h1>
        <p className="text-[11px] text-muted-foreground/76 mt-0.5">로컬 단일 사용자 환경</p>
      </div>

      {users.map(u => (
        <div key={u.user_id} className="rounded-lg border border-border/15 bg-card/20 p-5 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary font-black">
              {(u.display_name ?? u.user_id).slice(0, 1)}
            </div>
            <div>
              <p className="text-sm font-bold text-foreground/90">{u.display_name ?? u.user_id}</p>
              <p className="text-[11px] text-muted-foreground/76">
                {u.user_id} · {u.role} · {u.plan}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
            {Object.entries(STAT_LABELS).map(([k, label]) => {
              const v = u[k];
              if (v === undefined) return null;
              return (
                <div key={k} className="rounded-md bg-secondary/20 px-3 py-2">
                  <p className="text-[9px] font-semibold text-muted-foreground/76 uppercase">{label}</p>
                  <p className="text-xs font-bold text-foreground/80 mt-0.5 truncate">
                    {v == null ? "—" : typeof v === "number" ? v.toLocaleString()
                      : String(v).length > 16 ? new Date(String(v)).toLocaleDateString() : String(v)}
                  </p>
                </div>
              );
            })}
          </div>

          <div className="flex gap-2">
            <input
              value={noteText}
              onChange={e => setNoteText(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") addNote(u.user_id); }}
              placeholder="운영 메모 (감사 로그에 append 기록됨)"
              className="flex-1 h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40"
            />
            <button
              onClick={() => addNote(u.user_id)}
              className="px-3 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors"
            >
              메모 추가
            </button>
          </div>
          {noteSaved && (
            <p className="text-[11px] text-emerald-400">기록됨: “{noteSaved}” (감사 로그 확인 가능)</p>
          )}
        </div>
      ))}
    </div>
  );
};
