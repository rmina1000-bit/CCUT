import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AdminShell } from "@/components/admin/AdminShell";
import { AdminTab } from "@/components/admin/AdminLeftNav";
import { AdminSituationPanel } from "@/components/admin/AdminSituationPanel";
import { AdminSupportPanel } from "@/components/admin/AdminSupportPanel";
import { AdminSecurityPanel } from "@/components/admin/AdminSecurityPanel";
import { AdminDesignPanel } from "@/components/admin/AdminDesignPanel";
import { AdminLegalPanel } from "@/components/admin/AdminLegalPanel";
import { AdminAnalyticsPanel } from "@/components/admin/AdminAnalyticsPanel";
import { AdminUsersPanel } from "@/components/admin/AdminUsersPanel";
import { AdminRevenuePanel } from "@/components/admin/AdminRevenuePanel";
import { AdminAIOpsPanel } from "@/components/admin/AdminAIOpsPanel";
import { AdminAuditPanel } from "@/components/admin/AdminAuditPanel";
import { AdminEditLabPanel } from "@/components/admin/AdminEditLabPanel";

// [War Room v1] /admin/* 진입점 — URL 경로가 탭의 단일 진실원.
// /admin → 상황실. 나머지는 /admin/{tab}.
const TABS: AdminTab[] = [
  "situation", "users", "support", "revenue", "analytics",
  "design", "ai", "security", "legal", "audit",
  "edit-lab",
];

const LABELS: Record<AdminTab, string> = {
  situation: "상황실",
  users: "사용자 360",
  support: "지원/문의",
  revenue: "수익/구독/포인트",
  analytics: "행동 분석",
  design: "디자인 제어",
  ai: "AI 운영실",
  security: "보안 관제",
  legal: "법무/수사공조",
  audit: "감사/작업기록",
  "edit-lab": "편집연구실",
};


const AdminIndex: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const seg = location.pathname.replace(/^\/admin\/?/, "").split("/")[0];
  const active: AdminTab = (TABS as string[]).includes(seg) ? (seg as AdminTab) : "situation";

  const onNavigate = (tab: AdminTab) =>
    navigate(tab === "situation" ? "/admin" : `/admin/${tab}`);

  return (
    <AdminShell
      active={active}
      screenLabel={LABELS[active]}
      onNavigate={onNavigate}
      aiContext={active === "edit-lab" ? "lab" : undefined}
    >
      {active === "situation" && <AdminSituationPanel />}
      {active === "users" && <AdminUsersPanel />}
      {active === "support" && <AdminSupportPanel />}
      {active === "revenue" && <AdminRevenuePanel />}
      {active === "analytics" && <AdminAnalyticsPanel />}
      {active === "design" && <AdminDesignPanel />}
      {active === "ai" && <AdminAIOpsPanel />}
      {active === "security" && <AdminSecurityPanel />}
      {active === "legal" && <AdminLegalPanel />}
      {active === "audit" && <AdminAuditPanel />}
      {active === "edit-lab" && <AdminEditLabPanel />}
    </AdminShell>
  );
};

export default AdminIndex;
