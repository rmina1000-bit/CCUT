import React from "react";
import { LayoutDashboard, Users, Wallet, Sparkles, ScrollText, ArrowLeft } from "lucide-react";

export type AdminTab = "overview" | "users" | "revenue" | "insights" | "audit";

const MENU: { key: AdminTab; label: string; icon: React.ReactNode }[] = [
  { key: "overview", label: "운영 대시보드", icon: <LayoutDashboard size={14} /> },
  { key: "users", label: "사용자 운영", icon: <Users size={14} /> },
  { key: "revenue", label: "수익/정산", icon: <Wallet size={14} /> },
  { key: "insights", label: "세분 분석실", icon: <Sparkles size={14} /> },
  { key: "audit", label: "감사 로그", icon: <ScrollText size={14} /> },
];

export const AdminLeftNav: React.FC<{
  active: AdminTab;
  onNavigate: (tab: AdminTab) => void;
}> = ({ active, onNavigate }) => (
  <nav className="w-52 flex-shrink-0 border-r border-border/15 bg-[hsl(228_12%_9%)] flex flex-col">
    <div className="px-4 py-4 border-b border-border/15">
      <p className="text-sm font-black tracking-wide text-foreground/90">CCUT 관제실</p>
      <p className="text-[10px] text-muted-foreground/50 mt-0.5">중앙 관리자 콘솔 v0</p>
    </div>
    <div className="flex-1 py-2">
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
