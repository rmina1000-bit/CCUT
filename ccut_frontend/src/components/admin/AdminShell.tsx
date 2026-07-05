import React from "react";
import { AdminLeftNav, AdminTab } from "./AdminLeftNav";

// [Admin v0] 관리자 셸 — 사용자 작업실(Index.tsx)과 완전 분리된 운영자 레이아웃.
// 조용하고 밀도 높은 운영 도구: 감성 UI 금지, 데이터 우선.
export const AdminShell: React.FC<{
  active: AdminTab;
  onNavigate: (tab: AdminTab) => void;
  children: React.ReactNode;
}> = ({ active, onNavigate, children }) => (
  <div className="flex h-screen bg-[hsl(228_10%_7%)] text-foreground">
    <AdminLeftNav active={active} onNavigate={onNavigate} />
    <main className="flex-1 overflow-y-auto p-6">{children}</main>
  </div>
);
