import React, { useState } from "react";
import {
  Radar, Users, LifeBuoy, Wallet, BarChart3, Paintbrush,
  Sparkles, ShieldAlert, Scale, ScrollText, FlaskConical, ArrowLeft, Activity,
  Workflow, Lock, ChevronDown, ChevronRight,
} from "lucide-react";
import { ANATOMY_MENU_ENABLED } from "./adminAnatomyConfig";
import { isLocked } from "./adminLocks";

// [War Room v1] 최상위 메뉴 — IA 확정본(CCUT_ADMIN_WAR_ROOM_IA_FINAL.md)이 단일 진실원.
// [NERVE-1] 제작신경계 추가 — 상황실·편집연구실의 요약 진입점(두 탭은 그대로 유지).
// [NAME-1 2026-08-01] 표시명을 **질문 또는 답**으로 바꾼다. 비유 금지.
//   왜: 주제별 13탭은 주제마다 담당 팀이 있을 때 성립하는 구조다. 지금 관제실을 보는
//   사람은 한 명이고, "생체 관제실"과 "제작신경계"는 이름만으로 안이 구분되지 않았다
//   (비유가 앞서 뜻을 가렸다). 이름이 질문이면 어디를 열지가 바로 정해진다.
//     제작신경계 -> 오늘    (지금 CCUT 괜찮은가)
//     생체 관제실 -> 흐름도  (어디서 멈췄나)
//     편집연구실 -> 능력표  (뭐가 되고 뭐가 잠겼나)
//     감사/작업기록 -> 기록  (언제 뭘 했나)
//     AI 운영실 -> AI 설정   (키·모델)
//   상황실은 이번에 두지 않는다 — 3단계에서 '오늘'과 통합 예정이라 지금 바꾸면 두 번 바꾼다.
//   ★ key(=URL)는 바꾸지 않는다. 표시명만 바꾼다 — 링크가 깨지고 이득이 없다.
export type AdminTab =
  | "anatomy" | "nerve" | "situation" | "users" | "support" | "revenue" | "analytics"
  | "design" | "ai" | "security" | "legal" | "audit" | "edit-lab";

const MENU: { key: AdminTab; label: string; icon: React.ReactNode }[] = [
  ...(ANATOMY_MENU_ENABLED
    ? [{ key: "anatomy" as const, label: "흐름도", icon: <Workflow size={14} /> }]
    : []),
  { key: "nerve", label: "오늘", icon: <Activity size={14} /> },
  { key: "situation", label: "상황실", icon: <Radar size={14} /> },
  { key: "users", label: "사용자 360", icon: <Users size={14} /> },
  { key: "support", label: "지원/문의", icon: <LifeBuoy size={14} /> },
  { key: "revenue", label: "수익/구독/포인트", icon: <Wallet size={14} /> },
  { key: "analytics", label: "행동 분석", icon: <BarChart3 size={14} /> },
  { key: "design", label: "디자인 제어", icon: <Paintbrush size={14} /> },
  { key: "ai", label: "AI 설정", icon: <Sparkles size={14} /> },
  { key: "security", label: "보안 관제", icon: <ShieldAlert size={14} /> },
  { key: "legal", label: "법무/수사공조", icon: <Scale size={14} /> },
  { key: "audit", label: "기록", icon: <ScrollText size={14} /> },
  { key: "edit-lab", label: "능력표", icon: <FlaskConical size={14} /> },
];

// [LOCK-1 2026-08-01] 활성/잠김을 갈라 놓는다. 조건이 안 온 페이지가 매일 보는 목록에
//   섞여 있으면 열 곳을 고르는 데 매번 값을 치른다. 삭제가 아니라 순서를 낮추는 것이고,
//   접힌 채로도 클릭하면 그대로 열린다(절벽 ④).
const ACTIVE_MENU = MENU.filter(m => !isLocked(m.key));
const LOCKED_MENU = MENU.filter(m => isLocked(m.key));

export const AdminLeftNav: React.FC<{
  active: AdminTab;
  onNavigate: (tab: AdminTab) => void;
}> = ({ active, onNavigate }) => {
  // 잠긴 그룹 안의 페이지를 보고 있으면 펼친 채로 둔다 — 지금 있는 자리가 목록에서
  // 사라져 보이면 어디에 있는지 알 수 없다.
  const [openLocked, setOpenLocked] = useState(() => isLocked(active));
  const itemClass = (key: AdminTab, dim = false) =>
    `w-full flex items-center gap-2.5 px-4 py-2 text-xs font-medium transition-colors text-left ${
      active === key
        ? "bg-primary/15 text-primary border-r-2 border-primary"
        : dim
          ? "text-muted-foreground/67 hover:text-foreground/60 hover:bg-secondary/20"
          : "text-muted-foreground/60 hover:text-foreground/80 hover:bg-secondary/20"
    }`;
  return (
  <nav className="w-52 flex-shrink-0 border-r border-border/15 bg-[hsl(228_12%_9%)] flex flex-col">
    <div className="px-4 py-4 border-b border-border/15">
      <p className="text-sm font-black tracking-wide text-foreground/90">CCUT 관제실</p>
      <p className="text-[10px] text-muted-foreground/76 mt-0.5">전쟁상황판 v1</p>
    </div>
    <div className="flex-1 py-2 overflow-y-auto">
      {ACTIVE_MENU.map(m => (
        <button key={m.key} onClick={() => onNavigate(m.key)} className={itemClass(m.key)}>
          {m.icon}
          {m.label}
        </button>
      ))}

      <button
        type="button"
        onClick={() => setOpenLocked(v => !v)}
        data-admin-locked-toggle={openLocked ? "open" : "closed"}
        className="mt-3 w-full flex items-center gap-2 px-4 py-2 text-[11px] font-medium text-muted-foreground/70 hover:text-muted-foreground/70 transition-colors border-t border-border/10 pt-3"
      >
        {openLocked ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Lock size={11} />
        아직 열리지 않음
        <span className="ml-auto tabular-nums">{LOCKED_MENU.length}</span>
      </button>
      {openLocked && LOCKED_MENU.map(m => (
        <button
          key={m.key}
          onClick={() => onNavigate(m.key)}
          data-admin-locked-item={m.key}
          className={itemClass(m.key, true)}
        >
          {m.icon}
          {m.label}
        </button>
      ))}
    </div>
    <a
      href="/"
      className="flex items-center gap-2 px-4 py-3 text-[11px] text-muted-foreground/76 hover:text-foreground/80 border-t border-border/15 transition-colors"
    >
      <ArrowLeft size={12} />
      사용자 작업실로
    </a>
  </nav>
  );
};
