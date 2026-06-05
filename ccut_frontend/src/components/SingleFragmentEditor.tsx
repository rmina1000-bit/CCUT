import React, { useState, useEffect, useRef } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Fragment } from "@/data/fragmentData";
import { getUid } from "@/lib/fragmentIdentity";

const LocalDialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & {
    position: { x: number; y: number } | null;
  }
>(({ className, children, position, ...props }, ref) => {
  const inlineStyle: React.CSSProperties = position
    ? {
        position: "fixed",
        left: `${position.x}px`,
        top: `${position.y}px`,
        transform: "none",
        margin: 0,
      }
    : {};

  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Content
        ref={ref}
        style={inlineStyle}
        className={cn(
          "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",
          className
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity data-[state=open]:bg-accent data-[state=open]:text-muted-foreground hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none">
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
});
LocalDialogContent.displayName = "LocalDialogContent";

interface SingleFragmentEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  fragment: Fragment | null;
  onApply?: (payload: {
    fragmentUid: string;
    newStartSec: number;
    newEndSec: number;
    origStart: number;
    origEnd: number;
  }) => void;
}

export const SingleFragmentEditor: React.FC<SingleFragmentEditorProps> = ({
  open,
  onOpenChange,
  fragment,
  onApply,
}) => {
  const [leftCut, setLeftCut] = useState(0);
  const [rightCut, setRightCut] = useState(12);
  const [loadedFrames, setLoadedFrames] = useState<Record<number, boolean>>({});
  const [imageErrorAttempts, setImageErrorAttempts] = useState<Record<number, number>>({});
  const [frameCacheBuster, setFrameCacheBuster] = useState<Record<number, number>>({});
  const [dragging, setDragging] = useState<'left' | 'right' | null>(null);
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const dragRafRef = useRef<number | null>(null);

  const readNumber = (...values: unknown[]) => {
    for (const value of values) {
      if (typeof value === "number" && Number.isFinite(value)) return value;
    }
    return undefined;
  };

  const startSec = fragment ? readNumber((fragment as any).start_sec, (fragment as any).start, (fragment as any).start_time) : undefined;
  const endSec   = fragment ? readNumber((fragment as any).end_sec,   (fragment as any).end,   (fragment as any).end_time) : undefined;

  const baseStartSec = (fragment as any)?.orig_start_sec ?? startSec;   // 원본 전체 시작
  const baseEndSec   = (fragment as any)?.orig_end_sec   ?? endSec;     // 원본 전체 끝
  const currentStartSec = startSec;   // 현재 살아남은 시작(이미 trim 반영됨)
  const currentEndSec   = endSec;     // 현재 살아남은 끝
  const baseDuration = (baseStartSec !== undefined && baseEndSec !== undefined) ? (baseEndSec - baseStartSec) : undefined;

  useEffect(() => {
    if (!open || !fragment) return;

    if (baseDuration && baseDuration > 0 && currentStartSec !== undefined && currentEndSec !== undefined) {
      let lc = Math.round(((currentStartSec - baseStartSec) / baseDuration) * 12);
      let rc = Math.round(((currentEndSec   - baseStartSec) / baseDuration) * 12);
      lc = Math.max(0, Math.min(12, lc));
      rc = Math.max(0, Math.min(12, rc));
      if (rc <= lc) rc = Math.min(12, lc + 1);   // 최소 1칸 보장
      setLeftCut(lc);
      setRightCut(rc);
    } else {
      setLeftCut(0);
      setRightCut(12);
    }
    setLoadedFrames({});
    setImageErrorAttempts({});
    setFrameCacheBuster({});
    setPosition(null);
    setCurrentIndex(0);
    setIsPlaying(false);

    if (startSec === undefined || endSec === undefined) return;

    const payload = {
      fragments: [
        {
          source_id: fragment.source_id,
          fragment_id: fragment.fragment_id,
          start_time: startSec,
          end_time: endSec
        }
      ]
    };

    fetch("http://127.0.0.1:8000/pbe/extract-panoramas", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    })
      .then(res => res.json())
      .then(() => {
        // Response processed
      })
      .catch(() => {
        // Silent error
      });

  }, [open, fragment, startSec, endSec]);

  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const percentage = Math.max(0, Math.min(1, x / rect.width));
      const index = Math.round(percentage * 12);

      if (dragging === 'left') {
        setLeftCut(Math.max(0, Math.min(rightCut - 1, index)));
      } else if (dragging === 'right') {
        setRightCut(Math.max(leftCut + 1, Math.min(12, index)));
      }
    };

    const handleMouseUp = () => {
      setDragging(null);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragging, leftCut, rightCut]);

  const durationSec =
    typeof startSec === "number" && typeof endSec === "number"
      ? Math.max(0, endSec - startSec)
      : undefined;

  useEffect(() => {
    if (!isPlaying) return;

    const frameDuration = durationSec && durationSec > 0 
      ? (durationSec / 12) * 1000 
      : 200;

    const interval = setInterval(() => {
      setCurrentIndex((prev) => {
        if (prev >= 11) {
          setIsPlaying(false);
          return 11;
        }
        return prev + 1;
      });
    }, frameDuration);

    return () => clearInterval(interval);
  }, [isPlaying, durationSec]);

  if (!fragment) return null;

  const formatSec = (value: number | undefined) =>
    typeof value === "number" ? `${value.toFixed(1)}s` : "—";

  const handleImageError = (index: number) => {
    const attempts = imageErrorAttempts[index] || 0;
    if (attempts < 10) {
      setTimeout(() => {
        setImageErrorAttempts(prev => ({ ...prev, [index]: attempts + 1 }));
        setFrameCacheBuster(prev => ({ ...prev, [index]: Date.now() }));
      }, 1000);
    }
  };

  const handleMouseDown = (type: 'left' | 'right') => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(type);
  };

  const handleReset = () => {
    setLeftCut(0);
    setRightCut(12);
    setCurrentIndex(0);
    setIsPlaying(false);
  };

  const activeRatio = (rightCut - leftCut) / 12;
  const aliveDuration = baseDuration !== undefined ? baseDuration * activeRatio : 0;

  const handlePlayToggle = () => {
    setIsPlaying((prev) => {
      if (!prev) {
        setCurrentIndex((curr) => (curr >= 11 ? 0 : curr));
        return true;
      }
      return false;
    });
  };

  const handleApply = () => {
    if (!fragment) return;
    const origStart = baseStartSec ?? 0;
    const origEnd   = baseEndSec ?? 0;
    const duration  = origEnd - origStart;
    const newStartSec = origStart + (leftCut / 12) * duration;
    const newEndSec   = origStart + (rightCut / 12) * duration;
    onApply?.({
      fragmentUid: getUid(fragment),
      newStartSec,
      newEndSec,
      origStart,
      origEnd
    });
    onOpenChange(false);
  };

  const updateIndexFromX = (clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const percentage = Math.max(0, Math.min(1, x / rect.width));
    const index = Math.floor(percentage * 12);
    setCurrentIndex(Math.max(0, Math.min(11, index)));
  };

  const handleRailMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('.cursor-ew-resize')) {
      return;
    }
    e.preventDefault();
    updateIndexFromX(e.clientX);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      updateIndexFromX(moveEvent.clientX);
    };

    const handleMouseUp = () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  const handleTitleMouseDown = (e: React.MouseEvent) => {
    if (!dialogRef.current) return;
    
    e.preventDefault();

    const rect = dialogRef.current.getBoundingClientRect();
    const startX = e.clientX;
    const startY = e.clientY;
    const initialLeft = rect.left;
    const initialTop = rect.top;

    let latestLeft = initialLeft;
    let latestTop = initialTop;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      let newLeft = initialLeft + deltaX;
      let newTop = initialTop + deltaY;

      const minLeft = 0;
      const maxLeft = Math.max(0, window.innerWidth - rect.width);
      const minTop = 0;
      const maxTop = Math.max(0, window.innerHeight - rect.height);

      newLeft = Math.max(minLeft, Math.min(maxLeft, newLeft));
      newTop = Math.max(minTop, Math.min(maxTop, newTop));

      latestLeft = newLeft;
      latestTop = newTop;

      if (dragRafRef.current === null) {
        dragRafRef.current = requestAnimationFrame(() => {
          dragRafRef.current = null;
          if (dialogRef.current) {
            dialogRef.current.style.left = `${latestLeft}px`;
            dialogRef.current.style.top = `${latestTop}px`;
            dialogRef.current.style.transform = "none";
          }
        });
      }
    };

    const handleMouseUp = () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);

      if (dragRafRef.current !== null) {
        cancelAnimationFrame(dragRafRef.current);
        dragRafRef.current = null;
      }

      if (dialogRef.current) {
        dialogRef.current.style.left = `${latestLeft}px`;
        dialogRef.current.style.top = `${latestTop}px`;
        dialogRef.current.style.transform = "none";
      }
      setPosition({ x: latestLeft, y: latestTop });
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} modal={false}>
      <LocalDialogContent
        ref={dialogRef}
        position={position}
        className="sm:max-w-[720px] w-[90vw] bg-[hsl(228,12%,10%)] border-border/15 text-foreground p-6"
      >
        <DialogHeader className="mb-4 select-none cursor-move" onMouseDown={handleTitleMouseDown}>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-base font-bold text-foreground">조각 정밀 편집 (1단계 파노라마)</DialogTitle>
            <span className="text-[10px] text-muted-foreground/50 font-mono bg-secondary/30 px-2 py-0.5 rounded">
              ID: {fragment.fragment_id}
            </span>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            {startSec === undefined || endSec === undefined ? (
              <span className="text-red-400 font-semibold">시간 정보 없음</span>
            ) : (
              `살아남는 길이 ${aliveDuration.toFixed(1)}s / 전체 ${formatSec(baseDuration)}`
            )}
          </DialogDescription>
        </DialogHeader>

        {/* Playback Preview Box */}
        {startSec !== undefined && endSec !== undefined && (
          <div className="relative aspect-video w-full bg-[hsl(228,12%,6%)] border border-border/10 rounded-md overflow-hidden flex items-center justify-center mb-4">
            <img
              src={`http://127.0.0.1:8000/static/thumbnails/P_${fragment.fragment_id}_${currentIndex}.jpg` +
                (frameCacheBuster[currentIndex] ? `?t=${frameCacheBuster[currentIndex]}` : "")}
              alt="Preview"
              className="w-full h-full object-contain"
            />
            <div className="absolute top-2 right-2 bg-black/75 px-2 py-1 rounded text-white text-[11px] font-mono shadow-md">
              {((currentIndex / 12) * (durationSec || 0)).toFixed(1)}s / {durationSec !== undefined ? `${durationSec.toFixed(1)}s` : "—"}
            </div>
          </div>
        )}

        {/* Play / Pause Toggle Button */}
        {startSec !== undefined && endSec !== undefined && (
          <div className="flex items-center justify-center mb-4">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handlePlayToggle}
              className="h-8 px-4 text-xs flex items-center gap-1.5 hover:bg-secondary/40 text-foreground"
            >
              {isPlaying ? (
                <>
                  <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                    <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
                  </svg>
                  일시정지
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z"/>
                  </svg>
                  재생
                </>
              )}
            </Button>
          </div>
        )}

        {/* 12 Frame Panorama Rail */}
        {startSec !== undefined && endSec !== undefined ? (
          <div className="space-y-3 mb-6 mt-4">
            <div className="relative pt-6">
              <div
                ref={containerRef}
                onMouseDown={handleRailMouseDown}
                className="relative w-full h-[84px] bg-[hsl(228,12%,6%)] border border-border/10 rounded-md overflow-hidden flex select-none cursor-pointer"
              >
                {Array.from({ length: 12 }).map((_, index) => {
                  const isGrayscale = index < leftCut || index >= rightCut;
                  const isLoaded = loadedFrames[index];
                  const src = `http://127.0.0.1:8000/static/thumbnails/P_${fragment.fragment_id}_${index}.jpg` +
                    (frameCacheBuster[index] ? `?t=${frameCacheBuster[index]}` : "");

                  return (
                    <div
                      key={index}
                      className="relative flex-1 h-full border-r border-border/10 last:border-r-0 overflow-hidden bg-black/40 flex items-center justify-center pointer-events-none"
                    >
                      {!isLoaded && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/70 z-10">
                          <svg className="animate-spin h-5 w-5 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                        </div>
                      )}
                      <img
                        src={src}
                        alt={`Frame ${index}`}
                        className={`w-full h-full object-cover transition-all duration-200 ${isGrayscale ? "grayscale brightness-[0.35]" : ""}`}
                        onLoad={() => setLoadedFrames(prev => ({ ...prev, [index]: true }))}
                        onError={() => handleImageError(index)}
                      />
                      <span className="absolute bottom-1 right-1 text-[8px] bg-black/60 px-1 rounded text-white font-mono z-20">
                        {index}
                      </span>
                    </div>
                  );
                })}

                {/* Playhead Handle & Line */}
                <div
                  className="absolute top-0 bottom-0 w-1 bg-yellow-400 z-20 pointer-events-none"
                  style={{
                    left: `calc(${(currentIndex + 0.5) * (100 / 12)}%)`,
                    transform: "translateX(-50%)",
                  }}
                >
                  <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-yellow-400 rounded-full border border-black shadow" />
                </div>

                {/* Left Handle */}
                <div
                  onMouseDown={handleMouseDown("left")}
                  className="absolute top-0 bottom-0 w-4 cursor-ew-resize flex items-center justify-center z-30"
                  style={{
                    left: `calc(${leftCut * (100 / 12)}% - 8px)`,
                  }}
                >
                  <div className="w-1.5 h-full bg-primary flex flex-col justify-center items-center rounded-sm">
                    <div className="w-[1px] h-4 bg-white/60 my-0.5" />
                    <span className="absolute -top-6 bg-primary text-white text-[8px] px-1 rounded font-bold whitespace-nowrap shadow-md">앞컷</span>
                  </div>
                </div>

                {/* Right Handle */}
                <div
                  onMouseDown={handleMouseDown("right")}
                  className="absolute top-0 bottom-0 w-4 cursor-ew-resize flex items-center justify-center z-30"
                  style={{
                    left: `calc(${rightCut * (100 / 12)}% - 8px)`,
                  }}
                >
                  <div className="w-1.5 h-full bg-blue-500 flex flex-col justify-center items-center rounded-sm">
                    <div className="w-[1px] h-4 bg-white/60 my-0.5" />
                    <span className="absolute -top-6 bg-blue-500 text-white text-[8px] px-1 rounded font-bold whitespace-nowrap shadow-md">뒤컷</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Time Labels Rail */}
            <div className="flex justify-between items-center text-[10px] text-muted-foreground/60 px-1 font-mono">
              <span>0.0s</span>
              <span>{formatSec(durationSec)}</span>
            </div>

            {/* Inactive Zone Labels */}
            <div className="flex justify-between items-center text-[10px] text-muted-foreground/80 mt-2 px-1">
              <span className={leftCut > 0 ? "text-red-400 font-medium" : "opacity-30"}>앞 버림</span>
              <span className="text-primary font-bold">살아남는 구간</span>
              <span className={rightCut < 12 ? "text-blue-400 font-medium" : "opacity-30"}>뒤 버림</span>
            </div>
          </div>
        ) : (
          <div className="p-8 text-center text-red-400 font-semibold border border-dashed border-red-500/30 rounded-lg my-6 bg-red-950/10">
            시간 정보가 유효하지 않아 편집을 시작할 수 없습니다.
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-0 border-t border-border/10 pt-4 flex items-center justify-end mt-4">
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            className="text-xs h-8 text-muted-foreground hover:text-foreground hover:bg-secondary/40"
          >
            닫기
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={handleReset}
            className="text-xs h-8 text-foreground hover:bg-secondary/40"
          >
            초기화
          </Button>
          <Button
            type="button"
            onClick={handleApply}
            className="text-xs h-8 bg-primary text-white hover:bg-primary/90"
          >
            적용
          </Button>
        </DialogFooter>
      </LocalDialogContent>
    </Dialog>
  );
};
