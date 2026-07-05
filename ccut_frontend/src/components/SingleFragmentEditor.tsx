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
import { getUid, displayName } from "@/lib/fragmentIdentity";

const LocalDialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & {
    position: { x: number; y: number } | null;
    size?: { width: number; height: number } | null;
  }
>(({ className, children, position, size, ...props }, ref) => {
  const inlineStyle: React.CSSProperties = {
    ...(position
      ? {
          position: "fixed",
          left: `${position.x}px`,
          top: `${position.y}px`,
          transform: "none",
          margin: 0,
        }
      : {}),
    // [PBE-RESIZE] 리사이즈된 경우에만 명시 크기 적용. 가로/세로 모두 뷰포트 밖 금지.
    ...(size
      ? {
          width: `${size.width}px`,
          height: `${size.height}px`,
          maxWidth: "100vw",
          maxHeight: "100vh",
        }
      : {}),
  };

  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Content
        ref={ref}
        style={inlineStyle}
        className={cn(
          "fixed left-[50%] top-[50%] z-50 flex flex-col overflow-hidden w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-2 border bg-background px-5 py-3 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",
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
  // [UI-⑩] 헤더 표기용 프로젝트명 — "{프로젝트명} · {A2} · 조각 정밀 편집"
  projectName?: string;
  // [아카이브 보기전용] 수정 불가 모드 — 적용/초기화/경계조작/프레임삭제 봉인.
  // 수정하려면 원본에서 '신규 프로젝트 생성'으로 가야 한다 (국장 지시)
  readOnly?: boolean;
  onApply?: (payload: {
    fragmentUid: string;
    newStartSec: number;
    newEndSec: number;
    origStart: number;
    origEnd: number;
    // [PBE-⑦] 중간 삭제 시 살아남는 구간들 (1개면 기존 trim과 동일)
    segments?: Array<{ startSec: number; endSec: number }>;
  }) => void;
}

export const SingleFragmentEditor: React.FC<SingleFragmentEditorProps> = ({
  open,
  onOpenChange,
  fragment,
  projectName,
  readOnly = false,
  onApply,
}) => {
  const [leftCut, setLeftCut] = useState(0);
  const [rightCut, setRightCut] = useState(12);
  // [PBE-DENSITY] 파노라마 프레임 수 (기본 12). 12가 아니면 백엔드가 P_{fid}_d{n}_{i}.jpg 로 생성.
  const [frameCount, setFrameCount] = useState(12);
  const frameSuffix = frameCount === 12 ? "" : `_d${frameCount}`;
  // [PBE-⑦] 중간 프레임 삭제 — 우클릭 메뉴로 토글, 적용 시 살아남는 연속 구간으로 분할
  const [deletedFrames, setDeletedFrames] = useState<Set<number>>(new Set());
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; index: number } | null>(null);
  const [loadedFrames, setLoadedFrames] = useState<Record<number, boolean>>({});
  const [imageErrorAttempts, setImageErrorAttempts] = useState<Record<number, number>>({});
  const [frameCacheBuster, setFrameCacheBuster] = useState<Record<number, number>>({});
  const [dragging, setDragging] = useState<'left' | 'right' | null>(null);
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  // [PBE-RACE FIX 2026-07-05] ready를 불리언이 아니라 '어느 조각·밀도가 준비됐나'로.
  // 단일 불리언이던 시절: 이전 밀도의 COMPLETED(또는 실패 catch)가 다른 밀도
  // 이미지를 개방 → 존재하지 않는 d{n} 프레임 404 폭풍 (국장 실측 37건).
  const [readyKey, setReadyKey] = useState<string | null>(null);
  const [extractFailed, setExtractFailed] = useState(false);
  const wantKey = fragment ? `${fragment.fragment_id}_d${frameCount}` : "";
  const wantKeyRef = useRef(wantKey);
  wantKeyRef.current = wantKey;
  const extractReady = readyKey === wantKey;
  // 늦게 도착한 응답/프로브가 현재 요청을 덮지 않게 — 자기 키가 아직 유효할 때만 개방
  const openGate = (key: string) => {
    if (wantKeyRef.current === key) setReadyKey(key);
  };

  const containerRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const dragRafRef = useRef<number | null>(null);
  const resizeRafRef = useRef<number | null>(null);

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
    setReadyKey(null);
    setExtractFailed(false);
    setFrameCount(12); // [PBE-DENSITY] 열 때는 항상 기본 밀도
    setDeletedFrames(new Set());
    setCtxMenu(null);
    setPosition(null);
    // [PBE-RESIZE] 열 때 확정 높이를 부여 → flex 세로 분배가 안정적으로 동작(레일 항상 노출).
    setSize({
      width: Math.min(720, Math.round(window.innerWidth * 0.92)),
      height: Math.min(640, Math.round(window.innerHeight * 0.9)),
    });
    setCurrentIndex(0);
    setIsPlaying(false);

    if (startSec === undefined || endSec === undefined) return;

    // [PBE-SPEED 2026-07-05] 캐시 프로브 — 첫 프레임이 이미 디스크에 있으면(재방문)
    // 추출 왕복을 기다리지 않고 즉시 개방. 열기 체감을 왕복 1장 확인으로 단축.
    const key = `${fragment.fragment_id}_d12`;
    const probe = new Image();
    probe.onload = () => openGate(key);
    probe.src = `/static/thumbnails/P_${fragment.fragment_id}_0.jpg`;

    requestExtract(fragment, 12, startSec, endSec);
  }, [open, fragment, startSec, endSec]);

  // [PBE-RACE FIX] 추출 요청 단일 경로 — 응답이 '내가 요청한 (조각,밀도)'일 때만 개방.
  // 실패 시 게이트를 열지 않는다(구버전 catch가 열어서 404 폭풍의 방아쇠였음) —
  // 실패 배너 + 다시 시도 버튼으로 정직하게.
  const requestExtract = (frag: any, n: number, s?: number, e?: number) => {
    const key = `${frag.fragment_id}_d${n}`;
    setExtractFailed(false);
    fetch("/api/pbe/extract-panoramas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        num_frames: n,
        fragments: [{
          source_id: frag.source_id,
          fragment_id: frag.fragment_id,
          start_time: s,
          end_time: e,
        }],
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data && data.status === "COMPLETED") {
          openGate(key);
        } else if (wantKeyRef.current === key) {
          setExtractFailed(true);
        }
      })
      .catch(() => { if (wantKeyRef.current === key) setExtractFailed(true); });
  };

  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const percentage = Math.max(0, Math.min(1, x / rect.width));
      const index = Math.round(percentage * frameCount);

      if (dragging === 'left') {
        setLeftCut(Math.max(0, Math.min(rightCut - 1, index)));
      } else if (dragging === 'right') {
        setRightCut(Math.max(leftCut + 1, Math.min(frameCount, index)));
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
  }, [dragging, leftCut, rightCut, frameCount]);

  const durationSec =
    typeof startSec === "number" && typeof endSec === "number"
      ? Math.max(0, endSec - startSec)
      : undefined;

  useEffect(() => {
    if (!isPlaying) return;

    const frameDuration = durationSec && durationSec > 0
      ? (durationSec / frameCount) * 1000
      : 200;

    const interval = setInterval(() => {
      setCurrentIndex((prev) => {
        let next = prev + 1;
        while (next < frameCount && deletedFrames.has(next)) next++; // [PBE-⑦] 삭제 프레임 건너뜀
        if (next >= frameCount) {
          setIsPlaying(false);
          return prev;
        }
        return next;
      });
    }, frameDuration);

    return () => clearInterval(interval);
  }, [isPlaying, durationSec, frameCount, deletedFrames]);

  // [PBE-RESIZE] 브라우저 창 크기가 줄어들면 모달 크기/위치를 뷰포트 안으로 다시 가둔다.
  useEffect(() => {
    const clampToViewport = () => {
      setSize((prev) =>
        prev
          ? {
              width: Math.min(prev.width, window.innerWidth),
              height: Math.min(prev.height, window.innerHeight),
            }
          : prev
      );
      setPosition((prev) => {
        if (!prev || !dialogRef.current) return prev;
        const rect = dialogRef.current.getBoundingClientRect();
        return {
          x: Math.max(0, Math.min(prev.x, window.innerWidth - rect.width)),
          y: Math.max(0, Math.min(prev.y, window.innerHeight - rect.height)),
        };
      });
    };
    window.addEventListener("resize", clampToViewport);
    return () => window.removeEventListener("resize", clampToViewport);
  }, []);

  if (!fragment) return null;

  const formatSec = (value: number | undefined) =>
    typeof value === "number" ? `${value.toFixed(1)}s` : "—";

  const handleImageError = (index: number) => {
    // [PBE 404 완화 2026-07-05] 10회/1s → 3회/2s. 게이트가 (조각,밀도) 키에 결속돼
    // 이제 존재하지 않는 밀도로는 열리지 않으므로, 재시도는 파일 쓰기 직후의
    // 짧은 창만 메우면 된다 (404 폭풍 37건 사건의 증폭기 제거).
    const attempts = imageErrorAttempts[index] || 0;
    if (attempts < 3) {
      setTimeout(() => {
        setImageErrorAttempts(prev => ({ ...prev, [index]: attempts + 1 }));
        setFrameCacheBuster(prev => ({ ...prev, [index]: Date.now() }));
      }, 2000);
    }
  };

  const handleMouseDown = (type: 'left' | 'right') => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(type);
  };

  const handleReset = () => {
    setLeftCut(0);
    setRightCut(frameCount);
    setCurrentIndex(0);
    setIsPlaying(false);
    setDeletedFrames(new Set());
    setCtxMenu(null);
  };

  // [PBE-DENSITY] 프레임 밀도 변경 — 컷 위치는 비율 보존 환산, 프레임은 백엔드 재추출.
  const changeDensity = (n: number) => {
    if (!fragment || n === frameCount) return;
    const clamped = Math.max(4, Math.min(48, n));
    const scale = clamped / frameCount;
    let lc = Math.round(leftCut * scale);
    let rc = Math.round(rightCut * scale);
    lc = Math.max(0, Math.min(clamped - 1, lc));
    rc = Math.max(lc + 1, Math.min(clamped, rc));
    setLeftCut(lc);
    setRightCut(rc);
    setCurrentIndex((ci) => Math.max(0, Math.min(clamped - 1, Math.round(ci * scale))));
    setIsPlaying(false);
    setLoadedFrames({});
    setImageErrorAttempts({});
    setFrameCacheBuster({});
    setDeletedFrames(new Set()); // 밀도가 바뀌면 프레임 인덱스 의미가 바뀌므로 삭제 표시는 초기화
    setCtxMenu(null);
    setFrameCount(clamped);
    // 이 밀도 캐시가 이미 있으면 즉시 개방 (프로브), 없으면 추출 완료 응답으로만 개방
    const key = `${fragment.fragment_id}_d${clamped}`;
    const suffix = clamped === 12 ? "" : `_d${clamped}`;
    const probe = new Image();
    probe.onload = () => openGate(key);
    probe.src = `/static/thumbnails/P_${fragment.fragment_id}${suffix}_0.jpg`;
    requestExtract(fragment, clamped, startSec, endSec);
  };

  // 밀도 프리셋: 초 단위 간격 → 프레임 수 (전체 길이 기준)
  const densityPresets = (() => {
    const d = durationSec && durationSec > 0 ? durationSec : 12;
    const byInterval = (sec: number) => Math.max(4, Math.min(48, Math.round(d / sec)));
    return [
      { label: "0.5s", n: byInterval(0.5) },
      { label: "1s", n: byInterval(1) },
      { label: "기본", n: 12 },
      { label: "2s", n: byInterval(2) },
    ];
  })();

  // [PBE-⑦] 살아남는 프레임 = [leftCut, rightCut) 중 삭제되지 않은 것
  const aliveFrameCount = (() => {
    let n = 0;
    for (let i = leftCut; i < rightCut; i++) if (!deletedFrames.has(i)) n++;
    return n;
  })();
  const activeRatio = aliveFrameCount / frameCount;
  const aliveDuration = baseDuration !== undefined ? baseDuration * activeRatio : 0;

  // 살아남는 연속 구간(세그먼트) — 적용 시 분할의 원천
  const keptSegments = (() => {
    const segs: Array<{ from: number; to: number }> = []; // [from, to) 프레임 인덱스
    let runStart: number | null = null;
    for (let i = leftCut; i <= rightCut; i++) {
      const kept = i < rightCut && !deletedFrames.has(i);
      if (kept && runStart === null) runStart = i;
      if (!kept && runStart !== null) {
        segs.push({ from: runStart, to: i });
        runStart = null;
      }
    }
    return segs;
  })();

  const handlePlayToggle = () => {
    setIsPlaying((prev) => {
      if (!prev) {
        setCurrentIndex((curr) => (curr >= frameCount - 1 ? 0 : curr));
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
    const newStartSec = origStart + (leftCut / frameCount) * duration;
    const newEndSec   = origStart + (rightCut / frameCount) * duration;
    // [PBE-⑦] 중간 삭제가 있으면 살아남는 구간들을 초 단위 세그먼트로 전달 (분할)
    const segments = keptSegments.map((s) => ({
      startSec: origStart + (s.from / frameCount) * duration,
      endSec:   origStart + (s.to / frameCount) * duration,
    }));
    onApply?.({
      fragmentUid: getUid(fragment),
      newStartSec,
      newEndSec,
      origStart,
      origEnd,
      segments,
    });
    onOpenChange(false);
  };

  const updateIndexFromX = (clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const percentage = Math.max(0, Math.min(1, x / rect.width));
    const index = Math.floor(percentage * frameCount);
    setCurrentIndex(Math.max(0, Math.min(frameCount - 1, index)));
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

  // [PBE-RESIZE] 우하단 핸들 드래그로 크기 조절. 가로/세로 모두 뷰포트(브라우저) 밖으로 못 나가게 clamp.
  const MIN_W = 360;
  const MIN_H = 320;
  const handleResizeMouseDown = (e: React.MouseEvent) => {
    if (!dialogRef.current) return;
    e.preventDefault();
    e.stopPropagation();

    const rect = dialogRef.current.getBoundingClientRect();
    const startX = e.clientX;
    const startY = e.clientY;
    const initialW = rect.width;
    const initialH = rect.height;
    const fixedLeft = rect.left;
    const fixedTop = rect.top;

    // 리사이즈 중에는 위치를 현재 좌상단에 고정(센터 변환 해제) → 우하단으로만 확장.
    if (dialogRef.current) {
      dialogRef.current.style.left = `${fixedLeft}px`;
      dialogRef.current.style.top = `${fixedTop}px`;
      dialogRef.current.style.transform = "none";
      dialogRef.current.style.margin = "0";
    }

    let latestW = initialW;
    let latestH = initialH;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      // 우/하단 가장자리가 뷰포트를 넘지 못하도록 좌상단 기준 최대치 계산
      const maxW = Math.max(MIN_W, window.innerWidth - fixedLeft);
      const maxH = Math.max(MIN_H, window.innerHeight - fixedTop);

      latestW = Math.max(MIN_W, Math.min(maxW, initialW + deltaX));
      latestH = Math.max(MIN_H, Math.min(maxH, initialH + deltaY));

      if (resizeRafRef.current === null) {
        resizeRafRef.current = requestAnimationFrame(() => {
          resizeRafRef.current = null;
          if (dialogRef.current) {
            dialogRef.current.style.width = `${latestW}px`;
            dialogRef.current.style.height = `${latestH}px`;
            dialogRef.current.style.maxWidth = "100vw";
            dialogRef.current.style.maxHeight = "100vh";
          }
        });
      }
    };

    const handleMouseUp = () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      if (resizeRafRef.current !== null) {
        cancelAnimationFrame(resizeRafRef.current);
        resizeRafRef.current = null;
      }
      // 위치도 함께 고정(센터 변환 → 좌표 고정 전환 유지)
      setPosition({ x: fixedLeft, y: fixedTop });
      setSize({ width: latestW, height: latestH });
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} modal={false}>
      <LocalDialogContent
        ref={dialogRef}
        position={position}
        size={size}
        className="sm:max-w-[720px] w-[90vw] max-h-[100vh] bg-[hsl(228,12%,10%)] border-border/15 text-foreground"
      >
        <DialogHeader className="mb-1 select-none cursor-move flex-shrink-0" onMouseDown={handleTitleMouseDown}>
          <div className="flex items-center gap-2 min-w-0">
            {/* [UI-⑩ 국장지시 v2] "{프로젝트명} · {A2} · 조각 정밀 편집" — 배지 대신 같은
                글줄, 모든 요소를 우측 주이름과 같은 폰트 사이즈로 (부담 제거) */}
            <DialogTitle className="text-[12px] font-bold text-foreground truncate">
              {[
                projectName,
                (fragment as any).display_id && !String((fragment as any).display_id).startsWith("SF_")
                  ? (fragment as any).display_id : null,
                "조각 정밀 편집 (1단계 파노라마)",
              ].filter(Boolean).join(" · ")}
            </DialogTitle>
            {/* [DISPLAY-NAME] 주이름 = 단일 진실원("원본제목 · m:ss–m:ss") — 우측,
                내부 id는 title 툴팁으로만(UI-⑧ 유지). 닫기 ✕와 겹치지 않게 mr-8(UI-⑨) */}
            <span
              title={fragment.fragment_id}
              className="ml-auto mr-8 flex-shrink-0 text-[12px] text-foreground/80 font-bold truncate max-w-[280px]"
            >
              {displayName(fragment as any)}
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

        {/* [PBE-RESIZE] 본문 = flex 세로 분배. 미리보기는 남는 공간에서 줄고, 레일은 고정(절대 안 가려짐) */}
        <div className="flex-1 min-h-0 flex flex-col gap-2 overflow-hidden">

        {/* Playback Preview Box */}
        {startSec !== undefined && endSec !== undefined && (
          <div className="relative flex-1 min-h-0 w-full bg-[hsl(228,12%,6%)] border border-border/10 rounded-md overflow-hidden flex items-center justify-center">
            {extractReady ? (
              <img
                src={`/static/thumbnails/P_${fragment.fragment_id}${frameSuffix}_${currentIndex}.jpg` +
                  (frameCacheBuster[currentIndex] ? `?t=${frameCacheBuster[currentIndex]}` : "")}
                alt="Preview"
                className="w-full h-full object-contain"
              />
            ) : extractFailed ? (
              /* [PBE-RACE FIX] 실패를 숨기고 게이트를 열던 구코드 대신 — 정직한 배너 */
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/70 z-10">
                <span className="text-[12px] text-red-300">프레임 추출에 실패했어요 (네트워크/서버)</span>
                <button
                  type="button"
                  onClick={() => fragment && requestExtract(fragment, frameCount, startSec, endSec)}
                  className="px-3 py-1 rounded-md bg-primary/20 text-primary text-[11px] font-bold hover:bg-primary/35"
                >다시 시도</button>
              </div>
            ) : (
              <div className="absolute inset-0 flex items-center justify-center bg-black/70 z-10">
                <svg className="animate-spin h-6 w-6 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </div>
            )}
            <div className="absolute top-2 right-2 bg-black/75 px-2 py-1 rounded text-white text-[11px] font-mono shadow-md">
              {((currentIndex / frameCount) * (durationSec || 0)).toFixed(1)}s / {durationSec !== undefined ? `${durationSec.toFixed(1)}s` : "—"}
            </div>
          </div>
        )}

        {/* Play / Pause Toggle Button */}
        {startSec !== undefined && endSec !== undefined && (
          <div className="flex items-center justify-center flex-shrink-0">
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

        {/* Panorama Rail (프레임 수 = frameCount, 기본 12) */}
        {startSec !== undefined && endSec !== undefined ? (
          <div className="space-y-1.5 flex-shrink-0">
            {/* [PBE-DENSITY] 프레임 간격 조그 — 촘촘히/듬성듬성 */}
            <div className="flex items-center justify-between px-1">
              <span className="text-[10px] text-muted-foreground/60 font-mono">
                프레임 간격 {durationSec ? (durationSec / frameCount).toFixed(2) : "—"}s · {frameCount}장
              </span>
              <div className="flex items-center gap-1">
                {densityPresets.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => changeDensity(p.n)}
                    className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all ${
                      frameCount === p.n
                        ? "bg-primary text-primary-foreground"
                        : "bg-secondary/40 text-muted-foreground hover:text-foreground hover:bg-secondary/60"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
                <button
                  type="button"
                  title="더 듬성듬성"
                  onClick={() => changeDensity(frameCount - 4)}
                  disabled={frameCount <= 4}
                  className="px-1.5 py-0.5 rounded text-[11px] font-bold bg-secondary/40 text-muted-foreground hover:text-foreground disabled:opacity-30"
                >−</button>
                <button
                  type="button"
                  title="더 촘촘히"
                  onClick={() => changeDensity(frameCount + 4)}
                  disabled={frameCount >= 48}
                  className="px-1.5 py-0.5 rounded text-[11px] font-bold bg-secondary/40 text-muted-foreground hover:text-foreground disabled:opacity-30"
                >+</button>
              </div>
            </div>
            <div className="relative pt-3">
              {/* [PBE-RAIL] 프레임 폭 고정 → 좁으면 가로 스크롤바로 이동, 넓으면 더 많이 보임 */}
              <div className="overflow-x-auto pbe-rail-scroll">
              <div
                ref={containerRef}
                onMouseDown={readOnly ? undefined : handleRailMouseDown}
                onContextMenu={(e) => {
                  // [PBE-⑦] 프레임 우클릭 → 삭제/복원 메뉴 (보기전용은 봉인)
                  e.preventDefault();
                  if (readOnly) return;
                  if (!containerRef.current) return;
                  const rect = containerRef.current.getBoundingClientRect();
                  const pct = Math.max(0, Math.min(0.999, (e.clientX - rect.left) / rect.width));
                  const idx = Math.floor(pct * frameCount);
                  setCtxMenu({ x: e.clientX, y: e.clientY, index: idx });
                }}
                className="relative w-max h-[84px] bg-[hsl(228,12%,6%)] border border-border/10 rounded-md overflow-hidden flex select-none cursor-pointer"
              >
                {Array.from({ length: frameCount }).map((_, index) => {
                  const isDeleted = deletedFrames.has(index);
                  const isGrayscale = index < leftCut || index >= rightCut || isDeleted;
                  const isLoaded = loadedFrames[index];
                  const src = `/static/thumbnails/P_${fragment.fragment_id}${frameSuffix}_${index}.jpg` +
                    (frameCacheBuster[index] ? `?t=${frameCacheBuster[index]}` : "");

                  return (
                    <div
                      key={index}
                      className="relative w-[56px] flex-shrink-0 h-full border-r border-border/10 last:border-r-0 overflow-hidden bg-black/40 flex items-center justify-center pointer-events-none"
                    >
                      {(!extractReady || !isLoaded) && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/70 z-10">
                          <svg className="animate-spin h-5 w-5 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                        </div>
                      )}
                      {extractReady && (
                        <img
                          src={src}
                          alt={`Frame ${index}`}
                          className={`w-full h-full object-cover transition-all duration-200 ${isGrayscale ? "grayscale brightness-[0.35]" : ""}`}
                          onLoad={() => setLoadedFrames(prev => ({ ...prev, [index]: true }))}
                          onError={() => handleImageError(index)}
                        />
                      )}
                      <span className="absolute bottom-1 right-1 text-[8px] bg-black/60 px-1 rounded text-white font-mono z-20">
                        {index}
                      </span>
                      {isDeleted && (
                        <span className="absolute top-1 left-1 text-[9px] bg-red-600/80 px-1 rounded text-white font-bold z-20">✕</span>
                      )}
                    </div>
                  );
                })}

                {/* Playhead Handle & Line */}
                <div
                  className="absolute top-0 bottom-0 w-1 bg-yellow-400 z-20 pointer-events-none"
                  style={{
                    left: `calc(${(currentIndex + 0.5) * (100 / frameCount)}%)`,
                    transform: "translateX(-50%)",
                  }}
                >
                  <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-yellow-400 rounded-full border border-black shadow" />
                </div>

                {/* Left Handle */}
                <div
                  onMouseDown={readOnly ? undefined : handleMouseDown("left")}
                  className={`absolute top-0 bottom-0 w-4 ${readOnly ? "cursor-default opacity-50" : "cursor-ew-resize"} flex items-center justify-center z-30`}
                  style={{
                    left: `calc(${leftCut * (100 / frameCount)}% - 8px)`,
                  }}
                >
                  <div className="w-1.5 h-full bg-primary flex flex-col justify-center items-center rounded-sm">
                    <div className="w-[1px] h-4 bg-white/60 my-0.5" />
                    <span className="absolute -top-6 bg-primary text-white text-[8px] px-1 rounded font-bold whitespace-nowrap shadow-md">앞컷</span>
                  </div>
                </div>

                {/* Right Handle */}
                <div
                  onMouseDown={readOnly ? undefined : handleMouseDown("right")}
                  className={`absolute top-0 bottom-0 w-4 ${readOnly ? "cursor-default opacity-50" : "cursor-ew-resize"} flex items-center justify-center z-30`}
                  style={{
                    left: `calc(${rightCut * (100 / frameCount)}% - 8px)`,
                  }}
                >
                  <div className="w-1.5 h-full bg-blue-500 flex flex-col justify-center items-center rounded-sm">
                    <div className="w-[1px] h-4 bg-white/60 my-0.5" />
                    <span className="absolute -top-6 bg-blue-500 text-white text-[8px] px-1 rounded font-bold whitespace-nowrap shadow-md">뒤컷</span>
                  </div>
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
            <div className="flex justify-between items-center text-[10px] text-muted-foreground/80 mt-1 px-1">
              <span className={leftCut > 0 ? "text-red-400 font-medium" : "opacity-30"}>앞 버림</span>
              <span className="text-primary font-bold">살아남는 구간</span>
              <span className={rightCut < frameCount ? "text-blue-400 font-medium" : "opacity-30"}>뒤 버림</span>
            </div>
          </div>
        ) : (
          <div className="p-8 text-center text-red-400 font-semibold border border-dashed border-red-500/30 rounded-lg my-6 bg-red-950/10">
            시간 정보가 유효하지 않아 편집을 시작할 수 없습니다.
          </div>
        )}

        </div>

        <DialogFooter className="gap-1.5 border-t border-border/10 pt-2 flex items-center justify-end flex-shrink-0">
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            className="text-xs h-8 text-muted-foreground hover:text-foreground hover:bg-secondary/40"
          >
            닫기
          </Button>
          {readOnly ? (
            /* [보기전용] 수정 봉인 — 수정은 새 프로젝트에서 */
            <span className="text-[11px] text-muted-foreground/70 self-center px-2">
              보기 전용 — 수정하려면 원본에서 '신규 프로젝트 생성'
            </span>
          ) : (
            <>
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
            </>
          )}
        </DialogFooter>

        {/* [PBE-⑦] 프레임 우클릭 컨텍스트 메뉴 */}
        {ctxMenu && (
          <>
            <div className="fixed inset-0 z-[90]" onClick={() => setCtxMenu(null)} onContextMenu={(e) => { e.preventDefault(); setCtxMenu(null); }} />
            <div
              className="fixed z-[100] bg-[hsl(228,12%,12%)] border border-border/30 rounded-md shadow-xl py-1 min-w-[120px]"
              style={{ left: Math.min(ctxMenu.x, window.innerWidth - 140), top: Math.min(ctxMenu.y, window.innerHeight - 80) }}
            >
              <div className="px-3 py-1 text-[10px] text-muted-foreground/60 font-mono border-b border-border/20">프레임 {ctxMenu.index}</div>
              <button
                type="button"
                className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-secondary/50"
                onClick={() => {
                  setDeletedFrames((prev) => {
                    const next = new Set(prev);
                    if (next.has(ctxMenu.index)) next.delete(ctxMenu.index);
                    else next.add(ctxMenu.index);
                    return next;
                  });
                  setCtxMenu(null);
                }}
              >
                {deletedFrames.has(ctxMenu.index) ? "복원" : "삭제"}
              </button>
            </div>
          </>
        )}

        {/* [PBE-RESIZE] 우하단 리사이즈 핸들 */}
        <div
          onMouseDown={handleResizeMouseDown}
          title="크기 조절"
          className="absolute bottom-0 right-0 w-5 h-5 cursor-nwse-resize z-50 flex items-end justify-end p-0.5 text-muted-foreground/50 hover:text-foreground"
          style={{ touchAction: "none" }}
        >
          <svg viewBox="0 0 10 10" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="1.2">
            <path d="M9 3 L3 9 M9 6.5 L6.5 9" strokeLinecap="round" />
          </svg>
        </div>
      </LocalDialogContent>
    </Dialog>
  );
};
