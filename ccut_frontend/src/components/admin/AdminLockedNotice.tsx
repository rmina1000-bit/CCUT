import React from "react";
import { Lock, Info } from "lucide-react";
import { LOCKED_PAGES, STRUCTURAL_EMPTY } from "./adminLocks";

// [LOCK-1 2026-08-01] 잠긴 페이지 상단 고지. 문구는 adminLocks 하나에서만 읽는다.
//   페이지를 막지 않는다 — 열리고, 왜 비어 있는지만 먼저 말한다.
//   "데이터가 없다"와 "조건이 아직 안 왔다"는 다른 사실이고, 화면이 그걸 구분해 말해야 한다.
export const AdminLockedNotice: React.FC<{ tab: string }> = ({ tab }) => {
  const locked = LOCKED_PAGES[tab];
  const structural = STRUCTURAL_EMPTY[tab];
  if (!locked && !structural) return null;

  if (structural) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-sky-500/20 bg-sky-500/[0.06] px-3 py-2.5 text-[11.5px] leading-relaxed text-sky-100/75">
        <Info size={13} className="mt-0.5 flex-shrink-0 text-sky-300/70" />
        <span>{structural}</span>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2 rounded-lg border border-border/25 bg-secondary/15 px-3 py-2.5 text-[11.5px] leading-relaxed text-muted-foreground/70">
      <Lock size={13} className="mt-0.5 flex-shrink-0 text-muted-foreground/73" />
      <span>
        <b className="font-semibold text-foreground/70">아직 열리지 않았습니다.</b>{" "}
        {locked} 아래 화면은 그때를 위해 남겨둔 것입니다.
      </span>
    </div>
  );
};

export default AdminLockedNotice;
