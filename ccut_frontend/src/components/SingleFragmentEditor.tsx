import React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Fragment } from "@/data/fragmentData";

interface SingleFragmentEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  fragment: Fragment | null;
  onApply?: () => void;
}

export const SingleFragmentEditor: React.FC<SingleFragmentEditorProps> = ({
  open,
  onOpenChange,
  fragment,
  onApply,
}) => {
  if (!fragment) return null;

  const readNumber = (...values: unknown[]) => {
    for (const value of values) {
      if (typeof value === "number" && Number.isFinite(value)) return value;
    }
    return undefined;
  };

  const formatSec = (value: number | undefined) =>
    typeof value === "number" ? `${value.toFixed(1)}s` : "—";

  const startSec = readNumber((fragment as any).start_sec, (fragment as any).start, (fragment as any).start_time);
  const endSec   = readNumber((fragment as any).end_sec,   (fragment as any).end,   (fragment as any).end_time);
  const durationSec =
    typeof startSec === "number" && typeof endSec === "number"
      ? Math.max(0, endSec - startSec)
      : undefined;

  const handleApplyClick = () => {
    onApply?.();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px] bg-[hsl(228,12%,12%)] border-border/20 text-foreground">
        <DialogHeader>
          <DialogTitle className="text-base font-bold text-foreground">단일 조각 편집</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            선택한 조각 1개의 정보를 확인합니다. 앞컷/뒤컷 기능은 다음 단계에서 연결됩니다.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4 text-xs">
          <div className="grid grid-cols-3 items-center gap-4">
            <span className="text-muted-foreground font-medium">조각 ID</span>
            <span className="col-span-2 font-mono break-all">{fragment.fragment_id}</span>
          </div>
          <div className="grid grid-cols-3 items-center gap-4">
            <span className="text-muted-foreground font-medium">시작 시간</span>
            <span className="col-span-2">{formatSec(startSec)}</span>
          </div>
          <div className="grid grid-cols-3 items-center gap-4">
            <span className="text-muted-foreground font-medium">끝 시간</span>
            <span className="col-span-2">{formatSec(endSec)}</span>
          </div>
          <div className="grid grid-cols-3 items-center gap-4">
            <span className="text-muted-foreground font-medium">길이</span>
            <span className="col-span-2">{formatSec(durationSec)}</span>
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            className="hover:bg-secondary/50"
          >
            닫기
          </Button>
          <Button
            type="button"
            disabled
            onClick={handleApplyClick}
            className="bg-primary hover:bg-primary-hover text-white"
          >
            적용
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
