import React from "react";
import { Loader2, Package } from "lucide-react";

interface ExportPanelSectionProps {
  committedProposalId?: string | null;
  isExporting: boolean;
  renderStatus: string;
  exportError: string | null;
  onExport: () => void;
}

export const ExportPanelSection: React.FC<ExportPanelSectionProps> = ({
  committedProposalId,
  isExporting,
  renderStatus,
  exportError,
  onExport,
}) => {
  if (!committedProposalId) return null;

  return (
    <div className="flex flex-col items-center gap-2 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <button
        onClick={onExport}
        disabled={isExporting}
        className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary/90 text-primary-foreground text-[12px] font-bold hover:bg-primary disabled:opacity-40 transition-all shadow-lg shadow-primary/15"
      >
        {isExporting ? (
          <>
            <Loader2 size={13} className="animate-spin" />
            <span>{renderStatus || "처리 중..."}</span>
          </>
        ) : (
          <>
            <Package size={13} />
            <span>{renderStatus === "완료" ? `${committedProposalId}안 다시 내보내기` : `${committedProposalId}안 내보내기`}</span>
          </>
        )}
      </button>
      {renderStatus === "완료" && (
        <p className="text-[11px] text-primary/70 font-medium">아카이브에 저장되었습니다.</p>
      )}
      {exportError && <p className="text-[11px] text-red-400/80">{exportError}</p>}
    </div>
  );
};
