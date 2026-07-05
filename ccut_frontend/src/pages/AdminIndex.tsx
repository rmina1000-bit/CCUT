import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AdminShell } from "@/components/admin/AdminShell";
import { AdminTab } from "@/components/admin/AdminLeftNav";
import { AdminOverviewPanel } from "@/components/admin/AdminOverviewPanel";
import { AdminUsersPanel } from "@/components/admin/AdminUsersPanel";
import { AdminRevenuePanel } from "@/components/admin/AdminRevenuePanel";
import { AdminInsightsPanel } from "@/components/admin/AdminInsightsPanel";
import { AdminAuditPanel } from "@/components/admin/AdminAuditPanel";

// [Admin v0] /admin/* 진입점 — URL 경로가 탭의 단일 진실원.
// /admin → overview, /admin/users, /admin/revenue, /admin/insights, /admin/audit
const TABS: AdminTab[] = ["overview", "users", "revenue", "insights", "audit"];

const AdminIndex: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const seg = location.pathname.replace(/^\/admin\/?/, "").split("/")[0];
  const active: AdminTab = (TABS as string[]).includes(seg) ? (seg as AdminTab) : "overview";

  const onNavigate = (tab: AdminTab) =>
    navigate(tab === "overview" ? "/admin" : `/admin/${tab}`);

  return (
    <AdminShell active={active} onNavigate={onNavigate}>
      {active === "overview" && <AdminOverviewPanel />}
      {active === "users" && <AdminUsersPanel />}
      {active === "revenue" && <AdminRevenuePanel />}
      {active === "insights" && <AdminInsightsPanel />}
      {active === "audit" && <AdminAuditPanel />}
    </AdminShell>
  );
};

export default AdminIndex;
