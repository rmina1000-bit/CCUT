import React from "react";
import { AdminLeftNav, AdminTab } from "./AdminLeftNav";
import { AdminAIPanel } from "./AdminAIPanel";

// [War Room v1] 관리자 셸 — 3열: 좌 내비(10메뉴) · 중앙 본문 · 우측 공통 AI 보조 패널.
// 사용자 작업실(Index.tsx)과 완전 분리. 조용하고 밀도 높은 운영 도구.
export const AdminShell: React.FC<{
  active: AdminTab;
  screenLabel: string;
  onNavigate: (tab: AdminTab) => void;
  children: React.ReactNode;
}> = ({ active, screenLabel, onNavigate, children }) => (
  <div className="flex h-screen bg-[hsl(228_10%_7%)] text-foreground">
    <AdminLeftNav active={active} onNavigate={onNavigate} />
    <main className="flex-1 overflow-y-auto p-6 min-w-0">{children}</main>
    <AdminAIPanel screen={screenLabel} />
  </div>
);
