import React from "react";
import {
  Radar, Users, LifeBuoy, Wallet, BarChart3, Paintbrush,
  Sparkles, ShieldAlert, Scale, ScrollText, FlaskConical, ArrowLeft, Activity,
} from "lucide-react";

// [War Room v1] 최상위 메뉴 — IA 확정본(CCUT_ADMIN_WAR_ROOM_IA_FINAL.md)이 단일 진실원.
// [NERVE-1] 제작신경계 추가 — 상황실·편집연구실의 요약 진입점(두 탭은 그대로 유지).
export type AdminTab =
  | "nerve" | "situation" | "users" | "support" | "revenue" | "analytics"
  | "design" | "ai" | "security" | "legal" | "audit" | "edit-lab";

const MENU: { key: AdminTab; label: string; icon: React.ReactNode }[] = [
  { key: "nerve", label: "제작신경계", icon: <Activity size={14} /> },
  { key: "situation", label: "상황실", icon: <Radar size={14} /> },
  { key: "users", label: "사용자 360", icon: <Users size={14} /> },
  { key: "support", label: "지원/문의", icon: <LifeBuoy size={14} /> },
  { key: "revenue", label: "수익/구독/포인트", icon: <Wallet size={14} /> },
  { key: "analytics", label: "행동 분석", icon: <BarChart3 size={14} /> },
  { key: "design", label: "디자인 제어", icon: <Paintbrush size={14} /> },
  { key: "ai", label: "AI 운영실", icon: <Sparkles size={14} /> },
  { key: "security", label: "보안 관제", icon: <ShieldAlert size={14} /> },
  { key: "legal", label: "법무/수사공조", icon: <Scale size={14} /> },
  { key: "audit", label: "감사/작업기록", icon: <ScrollText size={14} /> },
  { key: "edit-lab", label: "편집연구실", icon: <FlaskConical size={14} /> },
];

export const AdminLeftNav: React.FC<{
  active: AdminTab;
  onNavigate: (tab: AdminTab) => void;
}> = ({ active, onNavigate }) => (
  <nav className="w-52 flex-shrink-0 border-r border-border/15 bg-[hsl(228_12%_9%)] flex flex-col">
    <div className="px-4 py-4 border-b border-border/15">
      <p className="text-sm font-black tracking-wide text-foreground/90">CCUT 관제실</p>
      <p className="text-[10px] text-muted-foreground/50 mt-0.5">전쟁상황판 v1</p>
    </div>
    <div className="flex-1 py-2 overflow-y-auto">
      {MENU.map(m => (
        <button
          key={m.key}
          onClick={() => onNavigate(m.key)}
          className={`w-full flex items-center gap-2.5 px-4 py-2 text-xs font-medium transition-colors text-left ${
            active === m.key
              ? "bg-primary/15 text-primary border-r-2 border-primary"
              : "text-muted-foreground/60 hover:text-foreground/80 hover:bg-secondary/20"
          }`}
        >
          {m.icon}
          {m.label}
        </button>
      ))}
    </div>
    <a
      href="/"
      className="flex items-center gap-2 px-4 py-3 text-[11px] text-muted-foreground/50 hover:text-foreground/80 border-t border-border/15 transition-colors"
    >
      <ArrowLeft size={12} />
      사용자 작업실로
    </a>
  </nav>
);
