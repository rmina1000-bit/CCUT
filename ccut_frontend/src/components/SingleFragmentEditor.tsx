import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
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
import { STORY_GATE_COPY } from "@/lib/storyGateCopy";
import { SoundRoleControl } from "@/components/SoundRoleControl";
import type { SoundRole, SoundRoleItem } from "@/utils/soundRoleClient";

// [R3 G1] 편집기 단일 진실(ms 구간) 연산 — 순수 함수. 격자 인덱스는 여기 없다.
type MsRange = [number, number];
function mergeRangeMs(list: MsRange[], range: MsRange): MsRange[] {
  const [s, e] = range;
  if (e <= s) return list;
  const all = [...list, [s, e] as MsRange].sort((a, b) => a[0] - b[0]);
  const out: MsRange[] = [];
  for (const r of all) {
    const last = out[out.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else out.push([r[0], r[1]]);
  }
  return out;
}
function subtractRangeMs(list: MsRange[], range: MsRange): MsRange[] {
  const [s, e] = range;
  if (e <= s) return list;
  const out: MsRange[] = [];
  for (const [rs, re] of list) {
    if (re <= s || rs >= e) { out.push([rs, re]); continue; }
    if (rs < s) out.push([rs, s]);
    if (re > e) out.push([e, re]);
  }
  return out;
}
/** trim 창에서 excluded를 뺀 생존 span (compile과 동일 산식) */
function aliveSpansOf(trimStart: number, trimEnd: number, excluded: MsRange[]): MsRange[] {
  if (trimEnd <= trimStart) return [];
  let spans: MsRange[] = [[trimStart, trimEnd]];
  for (const r of excluded) spans = subtractRangeMs(spans, r);
  return spans.filter(([s, e]) => e - s >= 1);
}
/** 두 구간의 겹침 [s,e] 또는 null */
function overlapMs(a: MsRange, b: MsRange): MsRange | null {
  const s = Math.max(a[0], b[0]);
  const e = Math.min(a[1], b[1]);
  return e - s >= 1 ? [s, e] : null;
}

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
  // [EDIT-CONTRACT-B0 IMPL-2b] 게이트 ON 재진입 — Edit State로 프레임 상태 복원 (단일 창 역산 대체)
  contractState?: {
    anchor_start_ms: number; anchor_end_ms: number;
    trim_start_ms: number; trim_end_ms: number;
    excluded_ranges: Array<[number, number]>; removed: boolean;
  } | null;
  precisionContext?: {
    programId: string;
    fragmentId: string;
    sourceId: string;
    text: string;
    words: Array<{ w: string; s_ms: number; e_ms: number; p?: number | null; excluded?: boolean }>;
  } | null;
  soundRole?: SoundRoleItem | null;
  soundRoleSaving?: boolean;
  onSoundRoleChange?: (item: SoundRoleItem, role: SoundRole) => void | Promise<void>;
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
  contractState = null,
  precisionContext = null,
  soundRole = null,
  soundRoleSaving = false,
  onSoundRoleChange,
  onApply,
}) => {
  // [R3 G1 — 국장 승인 2026-07-17] 편집기의 단일 진실 = ms 구간 (anchor 절대좌표).
  // 격자 인덱스(leftCut/rightCut/deletedFrames)는 폐지 — 격자는 표시 파생일 뿐 저장을 오염시키지 않는다.
  const [trimStartMs, setTrimStartMs] = useState(0);
  const [trimEndMs, setTrimEndMs] = useState(0);
  const [excludedMs, setExcludedMs] = useState<MsRange[]>([]);
  const [alignedWords, setAlignedWords] = useState<Array<{ text: string; start_ms: number; end_ms: number }>>([]);
  const [isAligning, setIsAligning] = useState(false);
  const [alignmentError, setAlignmentError] = useState<string | null>(null);
  // [PBE-DENSITY] 파노라마 프레임 수 (기본 12). 12가 아니면 백엔드가 P_{fid}_d{n}_{i}.jpg 로 생성.
  const [frameCount, setFrameCount] = useState(12);
  const frameSuffix = frameCount === 12 ? "" : `_d${frameCount}`;
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
  // [R3 G1] anchor 절대좌표(ms 정수) — 격자·표시의 유일한 환산 기준
  const anchorStartMsVal = typeof baseStartSec === "number" ? Math.round(baseStartSec * 1000) : 0;
  const anchorEndMsVal = typeof baseEndSec === "number" ? Math.round(baseEndSec * 1000) : 0;
  const anchorDurMs = Math.max(0, anchorEndMsVal - anchorStartMsVal);

  useEffect(() => {
    if (!open || !fragment) return;

    // [R3 G1] 열기 초기값 = 타일 좌표의 ms 정확값 (격자 양자화 폐지).
    // excluded는 타일 동봉 spans_ms(05723b0f)의 간극에서 파생. contractState가 있으면
    // 아래 복원 effect가 저장 원본으로 덮는다 (선언 순서 보장 — 기존 규약 유지).
    const aS = typeof baseStartSec === "number" ? Math.round(baseStartSec * 1000) : 0;
    const aE = typeof baseEndSec === "number" ? Math.round(baseEndSec * 1000) : 0;
    const ts = currentStartSec !== undefined ? Math.round(currentStartSec * 1000) : aS;
    const te = currentEndSec !== undefined ? Math.round(currentEndSec * 1000) : aE;
    setTrimStartMs(Math.max(aS, Math.min(ts, aE)));
    setTrimEndMs(Math.max(aS, Math.min(te, aE)));
    const spans: MsRange[] | null = Array.isArray((fragment as any).spans_ms) && (fragment as any).spans_ms.length > 0
      ? (fragment as any).spans_ms : null;
    if (spans && spans.length > 1) {
      const gaps: MsRange[] = [];
      for (let i = 0; i < spans.length - 1; i++) gaps.push([spans[i][1], spans[i + 1][0]]);
      setExcludedMs(gaps);
    } else {
      setExcludedMs([]);
    }
    setLoadedFrames({});
    setImageErrorAttempts({});
    setFrameCacheBuster({});
    setReadyKey(null);
    setExtractFailed(false);
    setFrameCount(12); // [PBE-DENSITY] 열 때는 항상 기본 밀도
    setCtxMenu(null);
    setPosition(null);
    // [PBE-RESIZE] 열 때 확정 높이를 부여 → flex 세로 분배가 안정적으로 동작(레일 항상 노출).
    setSize({
      width: Math.min(720, Math.round(window.innerWidth * 0.92)),
      height: Math.min(640, Math.round(window.innerHeight * 0.9)),
    });
    setCurrentIndex(0);
    setIsPlaying(false);
    setAlignedWords([]);
    setIsAligning(false);
    setAlignmentError(null);

    if (startSec === undefined || endSec === undefined) return;

    // [PBE-SPEED 2026-07-05] 캐시 프로브 — 첫 프레임이 이미 디스크에 있으면(재방문)
    // 추출 왕복을 기다리지 않고 즉시 개방. 열기 체감을 왕복 1장 확인으로 단축.
    const key = `${fragment.fragment_id}_d12`;
    const probe = new Image();
    probe.onload = () => openGate(key);
    probe.src = `/static/thumbnails/P_${fragment.fragment_id}_0.jpg`;

    // [#21 단일 좌표계] 파노라마는 항상 뿌리(anchor) 전 구간에서 추출 — 컷·비활성·복원과
    // 같은 좌표계. anchor는 불변이므로 캐시 키(P_{fid})와도 영원히 정합.
    requestExtract(fragment, 12, baseStartSec, baseEndSec);
  }, [open, fragment, startSec, endSec, baseStartSec, baseEndSec]);

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
      // [R3 G1] 드래그는 격자 스냅 UI지만 저장 좌표는 그 칸 경계의 ms 정수 — 사용자의 신규 지정만 저장을 바꾼다.
      const index = Math.round(percentage * frameCount);
      const cellW = anchorDurMs / frameCount;
      const ms = Math.round(anchorStartMsVal + index * cellW);
      const minGap = Math.max(1, Math.round(cellW)); // 최소 1칸 보장 (기존 규약)
      if (dragging === 'left') {
        setTrimStartMs(Math.max(anchorStartMsVal, Math.min(trimEndMs - minGap, ms)));
      } else if (dragging === 'right') {
        setTrimEndMs(Math.max(trimStartMs + minGap, Math.min(anchorEndMsVal, ms)));
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
  }, [dragging, trimStartMs, trimEndMs, frameCount, anchorStartMsVal, anchorEndMsVal, anchorDurMs]);

  // [#21 단일 좌표계] 레일·재생·밀도·시간표시의 기준 길이 = 뿌리(anchor) 전체.
  // 구판은 현재 타일 길이(durationSec)를 쓰는 곳과 anchor를 쓰는 곳이 섞여 있었다(좌표 혼합 결함).
  const railDuration =
    typeof baseStartSec === "number" && typeof baseEndSec === "number"
      ? Math.max(0, baseEndSec - baseStartSec)
      : undefined;

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
    // [R3 G1] 초기화 = 단일 진실을 anchor 전체·제외 없음으로
    setTrimStartMs(anchorStartMsVal);
    setTrimEndMs(anchorEndMsVal);
    setExcludedMs([]);
    setCurrentIndex(0);
    setIsPlaying(false);
    setCtxMenu(null);
  };

  // [R3 G3] 밀도 변경 = 표시 해상도 변경일 뿐 — 저장 진실(trim·excluded ms) 무접촉.
  // 구판의 deletedFrames 초기화(편집 소거 벡터, #33 실측 [[6350,7620]]→[])와 컷 비율 환산 폐지.
  const changeDensity = (n: number) => {
    if (!fragment || n === frameCount) return;
    const clamped = Math.max(4, Math.min(48, n)); // [G5] 상한 48 — 전 프레임 전개 금지
    setCurrentIndex((ci) => Math.max(0, Math.min(clamped - 1, Math.round(ci * (clamped / frameCount)))));
    setIsPlaying(false);
    setLoadedFrames({});
    setImageErrorAttempts({});
    setFrameCacheBuster({});
    setCtxMenu(null);
    setFrameCount(clamped);
    // 이 밀도 캐시가 이미 있으면 즉시 개방 (프로브), 없으면 추출 완료 응답으로만 개방
    const key = `${fragment.fragment_id}_d${clamped}`;
    const suffix = clamped === 12 ? "" : `_d${clamped}`;
    const probe = new Image();
    probe.onload = () => openGate(key);
    probe.src = `/static/thumbnails/P_${fragment.fragment_id}${suffix}_0.jpg`;
    requestExtract(fragment, clamped, baseStartSec, baseEndSec); // [#21] anchor 좌표
  };

  // 밀도 프리셋: 초 단위 간격 → 프레임 수 (뿌리 전체 길이 기준)
  const densityPresets = (() => {
    const d = railDuration && railDuration > 0 ? railDuration : 12;
    const byInterval = (sec: number) => Math.max(4, Math.min(48, Math.round(d / sec)));
    return [
      { label: "0.5s", n: byInterval(0.5) },
      { label: "1s", n: byInterval(1) },
      { label: "기본", n: 12 },
      { label: "2s", n: byInterval(2) },
    ];
  })();

  // [R3 G1·G2] 생존 span = 단일 진실(ms)의 순수 파생 — 적용·표시·미리보기 전부 이것에서.
  const aliveSpans = aliveSpansOf(trimStartMs, trimEndMs, excludedMs);
  const aliveMs = aliveSpans.reduce((acc, [s, e]) => acc + (e - s), 0);
  const aliveDuration = aliveMs / 1000; // 격자 비율 근사 폐지 — ms 정확값
  const cellWidthMs = frameCount > 0 ? anchorDurMs / frameCount : 0;
  /** 칸 i의 anchor 절대 ms 구간 (표시용 — 저장 시에는 round된 정수 사용) */
  const cellRangeMs = (i: number): MsRange => [
    anchorStartMsVal + i * cellWidthMs,
    anchorStartMsVal + (i + 1) * cellWidthMs,
  ];
  /** 칸 i 안의 제외 구간들(칸 좌표 겹침) — G2 부분 표시의 원천 */
  const cellExcludedOverlaps = (i: number): MsRange[] => {
    const cell = cellRangeMs(i);
    const out: MsRange[] = [];
    for (const r of excludedMs) {
      const ov = overlapMs(cell, r);
      if (ov) out.push(ov);
    }
    return out;
  };
  /** 칸 판정: 제외와의 겹침 정도 (full = 사실상 전체, partial = 일부 걸침) */
  const cellExclusionState = (i: number): "full" | "partial" | "none" => {
    const ovs = cellExcludedOverlaps(i);
    if (ovs.length === 0) return "none";
    const covered = ovs.reduce((acc, [s, e]) => acc + (e - s), 0);
    return covered >= cellWidthMs - 1 ? "full" : "partial";
  };
  /** 칸 중심이 생존 span 안인가 — 미리보기 재생 스킵용 파생 */
  const isKeptFrame = (i: number): boolean => {
    const mid = anchorStartMsVal + (i + 0.5) * cellWidthMs;
    return aliveSpans.some(([s, e]) => mid >= s && mid < e);
  };

  // 살아남는 연속 칸 구간(미리보기 재생 진행용) — 표시 파생, 저장과 무관
  const keptSegments = (() => {
    const segs: Array<{ from: number; to: number }> = []; // [from, to) 프레임 인덱스
    let runStart: number | null = null;
    for (let i = 0; i <= frameCount; i++) {
      const kept = i < frameCount && isKeptFrame(i);
      if (kept && runStart === null) runStart = i;
      if (!kept && runStart !== null) {
        segs.push({ from: runStart, to: i });
        runStart = null;
      }
    }
    return segs;
  })();

  const findKeptFrameAtOrAfter = (index: number) => {
    for (const seg of keptSegments) {
      if (index < seg.from) return seg.from;
      if (index >= seg.from && index < seg.to) return index;
    }
    return null;
  };

  useEffect(() => {
    if (!isPlaying) return;

    const frameDuration = railDuration && railDuration > 0
      ? (railDuration / frameCount) * 1000
      : 200;

    const interval = setInterval(() => {
      setCurrentIndex((prev) => {
        const next = findKeptFrameAtOrAfter(prev + 1);
        if (next === null) {
          setIsPlaying(false);
          return prev;
        }
        return next;
      });
    }, frameDuration);

    return () => clearInterval(interval);
  }, [isPlaying, railDuration, frameCount, keptSegments]);

  const handlePlayToggle = () => {
    setIsPlaying((prev) => {
      if (!prev) {
        const firstKept = keptSegments[0]?.from;
        if (firstKept === undefined) return false;
        setCurrentIndex((curr) => {
          const hasNextKept = findKeptFrameAtOrAfter(curr + 1) !== null;
          return isKeptFrame(curr) && hasNextKept ? curr : firstKept;
        });
        return true;
      }
      return false;
    });
  };

  // [R3 G2] 재진입 복원 — 저장 원본(ms)을 그대로 단일 진실에 대입. 격자 양자화(12칸 역산·
  // mid-포함 검사) 폐지: 격자보다 짧은 원고발 정밀 excluded도 소거 없이 살아난다.
  useEffect(() => {
    if (!open || !fragment || !contractState) return;
    const aMs = contractState.anchor_start_ms;
    const eMs = contractState.anchor_end_ms;
    if (eMs - aMs <= 0) return;
    setTrimStartMs(Math.max(aMs, Math.min(contractState.trim_start_ms, eMs)));
    setTrimEndMs(Math.max(aMs, Math.min(contractState.trim_end_ms, eMs)));
    setExcludedMs(contractState.excluded_ranges.map(([s, e]) => [s, e] as MsRange));
  }, [open, fragment, contractState]);

  if (!fragment) return null;

  const handleApply = () => {
    if (!fragment) return;
    const origStart = baseStartSec ?? 0;
    const origEnd   = baseEndSec ?? 0;
    // [R3 G1] 적용 = 단일 진실(ms)의 생존 span 그대로 — 격자 환산 없음.
    const segments = aliveSpans.map(([s, e]) => ({ startSec: s / 1000, endSec: e / 1000 }));
    onApply?.({
      fragmentUid: getUid(fragment),
      newStartSec: trimStartMs / 1000,
      newEndSec: trimEndMs / 1000,
      origStart,
      origEnd,
      segments,
    });
    onOpenChange(false);
  };

  const handlePrecisionAlign = async () => {
    if (!fragment || !precisionContext || isAligning || excludedMs.length === 0) return;
    setIsAligning(true);
    setAlignmentError(null);
    try {
      const response = await fetch("/api/precision-align", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          program_id: precisionContext.programId,
          fragment_id: precisionContext.fragmentId,
          source_id: precisionContext.sourceId,
          text: precisionContext.text,
          words: precisionContext.words,
          anchor_start_ms: anchorStartMsVal,
          anchor_end_ms: anchorEndMsVal,
          excluded_ranges: excludedMs,
        }),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok || !result?.ok) {
        throw new Error(result?.message || result?.error || "Precision alignment failed.");
      }
      const nextRanges = (result.excluded_ranges ?? [])
        .map((span: number[]) => [Number(span[0]), Number(span[1])] as MsRange)
        .filter(([start, end]: MsRange) => Number.isFinite(start) && Number.isFinite(end) && end > start);
      setExcludedMs(nextRanges);
      setAlignedWords(
        (result.aligned_words ?? [])
          .map((word: any) => ({
            text: String(word.text ?? ""),
            start_ms: Number(word.start_ms),
            end_ms: Number(word.end_ms),
          }))
          .filter((word: any) => word.text && Number.isFinite(word.start_ms) && Number.isFinite(word.end_ms)),
      );
    } catch (error) {
      setAlignmentError(error instanceof Error ? error.message : "Precision alignment failed.");
    } finally {
      setIsAligning(false);
    }
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
  type ResizeEdge = "top" | "bottom" | "left" | "right" | "top-left" | "top-right" | "bottom-left" | "bottom-right";
  const handleResizeMouseDown = (e: React.MouseEvent, edge: ResizeEdge) => {
    if (!dialogRef.current) return;
    e.preventDefault();
    e.stopPropagation();

    const rect = dialogRef.current.getBoundingClientRect();
    const startX = e.clientX;
    const startY = e.clientY;
    const initialW = rect.width;
    const initialH = rect.height;
    const initialLeft = rect.left;
    const initialTop = rect.top;

    if (dialogRef.current) {
      dialogRef.current.style.left = `${initialLeft}px`;
      dialogRef.current.style.top = `${initialTop}px`;
      dialogRef.current.style.transform = "none";
      dialogRef.current.style.margin = "0";
    }

    let latestW = initialW;
    let latestH = initialH;
    let latestLeft = initialLeft;
    let latestTop = initialTop;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      const affectsLeft = edge.includes("left");
      const affectsRight = edge.includes("right");
      const affectsTop = edge.includes("top");
      const affectsBottom = edge.includes("bottom");

      if (affectsLeft) {
        const maxW = Math.max(MIN_W, initialLeft + initialW);
        latestW = Math.max(MIN_W, Math.min(maxW, initialW - deltaX));
        latestLeft = initialLeft + (initialW - latestW);
      } else if (affectsRight) {
        const maxW = Math.max(MIN_W, window.innerWidth - initialLeft);
        latestW = Math.max(MIN_W, Math.min(maxW, initialW + deltaX));
        latestLeft = initialLeft;
      }

      if (affectsTop) {
        const maxH = Math.max(MIN_H, initialTop + initialH);
        latestH = Math.max(MIN_H, Math.min(maxH, initialH - deltaY));
        latestTop = initialTop + (initialH - latestH);
      } else if (affectsBottom) {
        const maxH = Math.max(MIN_H, window.innerHeight - initialTop);
        latestH = Math.max(MIN_H, Math.min(maxH, initialH + deltaY));
        latestTop = initialTop;
      }

      if (resizeRafRef.current === null) {
        resizeRafRef.current = requestAnimationFrame(() => {
          resizeRafRef.current = null;
          if (dialogRef.current) {
            dialogRef.current.style.width = `${latestW}px`;
            dialogRef.current.style.height = `${latestH}px`;
            dialogRef.current.style.left = `${latestLeft}px`;
            dialogRef.current.style.top = `${latestTop}px`;
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
      setPosition({ x: latestLeft, y: latestTop });
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
        className="sm:max-w-[720px] w-[90vw] max-h-[100vh] bg-[hsl(228,12%,17%)] border-2 border-border text-foreground"
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

        {soundRole && (
          <div data-sound-detail="true" className="flex flex-shrink-0 items-center gap-3 border-y border-border/15 py-1.5">
            <div className="min-w-[108px] px-1">
              <p className="text-[11px] font-semibold text-foreground">{STORY_GATE_COPY.sound.detailHeading}</p>
              <p className="text-[9px] text-muted-foreground">{STORY_GATE_COPY.sound.handlingLabel}</p>
            </div>
            <SoundRoleControl
              item={soundRole}
              saving={soundRoleSaving}
              onChange={readOnly ? undefined : onSoundRoleChange}
              className="!w-full !flex-1 border-b-0 px-0"
            />
          </div>
        )}

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
              {((currentIndex / frameCount) * (railDuration || 0)).toFixed(1)}s / {railDuration !== undefined ? `${railDuration.toFixed(1)}s` : "—"}
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
                프레임 간격 {railDuration ? (railDuration / frameCount).toFixed(2) : "—"}s · {frameCount}장
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
                  // [R3 G2] 칸 상태 = 단일 진실(ms)의 파생 — full(전체 제외)·partial(부분 걸침)·트림 밖
                  const [cellS, cellE] = cellRangeMs(index);
                  const exState = cellExclusionState(index);
                  const overlaps = exState === "partial" ? cellExcludedOverlaps(index) : [];
                  const outsideTrim = cellE <= trimStartMs + 1 || cellS >= trimEndMs - 1;
                  const isGrayscale = outsideTrim || exState === "full";
                  const isLoaded = loadedFrames[index];
                  const src = `/static/thumbnails/P_${fragment.fragment_id}${frameSuffix}_${index}.jpg` +
                    (frameCacheBuster[index] ? `?t=${frameCacheBuster[index]}` : "");

                  return (
                    <div
                      key={index}
                      // [R3 G4] hover = 이 칸의 초 범위 표기 (브라우저 툴팁). 이벤트는 레일로 버블링.
                      title={`${((cellS - anchorStartMsVal) / 1000).toFixed(1)}~${((cellE - anchorStartMsVal) / 1000).toFixed(1)}s · ${(cellWidthMs / 1000).toFixed(2)}s`}
                      className="relative w-[56px] flex-shrink-0 h-full border-r border-border/10 last:border-r-0 overflow-hidden bg-black/40 flex items-center justify-center"
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
                          className={`w-full h-full object-cover transition-all duration-200 pointer-events-none ${isGrayscale ? "grayscale brightness-[0.35]" : ""}`}
                          onLoad={() => setLoadedFrames(prev => ({ ...prev, [index]: true }))}
                          onError={() => handleImageError(index)}
                        />
                      )}
                      {/* [R3 G2] 부분 걸침 = 걸친 ms 구간만 칸 안에서 정확한 위치·폭으로 표시 (자동 확대·축소 없음) */}
                      {exState === "full" && (
                        <div className="absolute inset-0 bg-red-600/80 border-x-2 border-red-300 pointer-events-none z-10" />
                      )}
                      {overlaps.map(([os, oe], k) => (
                        <div
                          key={k}
                          className="absolute top-0 bottom-0 bg-red-600/80 border-x-2 border-red-300 pointer-events-none z-10"
                          style={{
                            left: `${(((os - cellS) / cellWidthMs) * 100).toFixed(2)}%`,
                            width: `${(((oe - os) / cellWidthMs) * 100).toFixed(2)}%`,
                          }}
                        />
                      ))}
                      <span className="absolute bottom-1 right-1 text-[8px] bg-black/60 px-1 rounded text-white font-mono z-20 pointer-events-none">
                        {index}
                      </span>
                      {exState !== "none" && (readOnly ? (
                        <span className="absolute top-1 left-1 text-[9px] bg-red-600/80 px-1 rounded text-white font-bold z-20">✕</span>
                      ) : (
                        /* [X-복원 + R3 G1] X 클릭 = 이 칸과 겹치는 제외 구간을 뺀다(subtract) —
                           부분 걸침 칸이면 걸친 부분만 되살아난다. 레일 mousedown 전파 차단. */
                        <button
                          type="button"
                          title="이 칸 되살리기"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => {
                            e.stopPropagation();
                            setExcludedMs((prev) => subtractRangeMs(prev, [Math.round(cellS), Math.round(cellE)]));
                          }}
                          className="absolute top-1 left-1 text-[9px] bg-red-600/80 hover:bg-red-500 px-1 rounded text-white font-bold z-20 pointer-events-auto cursor-pointer"
                        >✕</button>
                      ))}
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
                    // [R3 G1] 핸들 위치 = ms 진실의 비율 파생 — 비격자 저장값도 정확한 위치에 선다
                    left: `calc(${anchorDurMs > 0 ? (((trimStartMs - anchorStartMsVal) / anchorDurMs) * 100).toFixed(3) : 0}% - 8px)`,
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
                    left: `calc(${anchorDurMs > 0 ? (((trimEndMs - anchorStartMsVal) / anchorDurMs) * 100).toFixed(3) : 100}% - 8px)`,
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
              <span>{formatSec(railDuration)}</span>
            </div>

            {precisionContext && (
              <div className="relative h-9 border-y border-border/10 overflow-hidden">
                {(alignedWords.length > 0
                  ? alignedWords
                  : precisionContext.words.map((word) => ({
                      text: word.w,
                      start_ms: word.s_ms,
                      end_ms: word.e_ms,
                    }))
                ).map((word, index) => {
                  const start = Math.max(anchorStartMsVal, word.start_ms);
                  const end = Math.min(anchorEndMsVal, word.end_ms);
                  if (end <= start || anchorDurMs <= 0) return null;
                  const excluded = excludedMs.some(([s, e]) => end > s && start < e);
                  return (
                    <div
                      key={`${index}-${word.text}-${start}`}
                      title={`${word.text} ${start}–${end}ms`}
                      className={`absolute inset-y-1 flex items-center justify-center border-x px-0.5 text-[9px] leading-none overflow-hidden ${
                        excluded
                          ? "border-red-300/80 bg-red-600/70 text-white"
                          : "border-border/20 bg-secondary/30 text-muted-foreground"
                      }`}
                      style={{
                        left: `${(((start - anchorStartMsVal) / anchorDurMs) * 100).toFixed(3)}%`,
                        width: `${Math.max(0.6, ((end - start) / anchorDurMs) * 100).toFixed(3)}%`,
                      }}
                    >
                      {word.text}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Inactive Zone Labels */}
            <div className="flex justify-between items-center text-[10px] text-muted-foreground/80 mt-1 px-1">
              <span className={trimStartMs > anchorStartMsVal ? "text-red-400 font-medium" : "opacity-30"}>앞 버림</span>
              <span className="text-primary font-bold">살아남는 구간</span>
              <span className={trimEndMs < anchorEndMsVal ? "text-blue-400 font-medium" : "opacity-30"}>뒤 버림</span>
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
              {precisionContext && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handlePrecisionAlign}
                  disabled={isAligning || excludedMs.length === 0}
                  className="text-xs h-8 text-foreground hover:bg-secondary/40"
                >
                  {isAligning ? "정밀 맞춤 중…" : "대사 정밀 맞춤"}
                </Button>
              )}
              {alignmentError && (
                <span role="alert" className="text-[11px] text-red-400 max-w-[220px]">
                  {alignmentError}
                </span>
              )}
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
        {ctxMenu && createPortal(
          <>
            <div className="fixed inset-0 z-[90]" onClick={() => setCtxMenu(null)} onContextMenu={(e) => { e.preventDefault(); setCtxMenu(null); }} />
            <div
              className="fixed z-[100] bg-[hsl(228,12%,12%)] border border-border/30 rounded-md shadow-xl py-1 min-w-[120px]"
              style={{ left: Math.min(ctxMenu.x, window.innerWidth - 140), top: Math.min(ctxMenu.y, window.innerHeight - 80) }}
            >
              <div className="px-3 py-1 text-[10px] text-muted-foreground/60 font-mono border-b border-border/20">
                {/* [R3 G4] 메뉴에도 칸의 초 범위 병기 */}
                프레임 {ctxMenu.index} · {((cellRangeMs(ctxMenu.index)[0] - anchorStartMsVal) / 1000).toFixed(1)}~{((cellRangeMs(ctxMenu.index)[1] - anchorStartMsVal) / 1000).toFixed(1)}s
              </div>
              <button
                type="button"
                className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-secondary/50"
                onClick={() => {
                  // [R3 G1] 삭제 = 이 칸의 정확한 ms 구간을 excluded에 더한다 / 복원 = 겹치는 구간을 뺀다.
                  const [cs, ce] = cellRangeMs(ctxMenu.index);
                  const cell: MsRange = [Math.round(cs), Math.round(ce)];
                  if (cellExclusionState(ctxMenu.index) !== "none") {
                    setExcludedMs((prev) => subtractRangeMs(prev, cell));
                  } else {
                    setExcludedMs((prev) => mergeRangeMs(prev, cell));
                  }
                  setCtxMenu(null);
                }}
              >
                {cellExclusionState(ctxMenu.index) !== "none" ? "복원" : "삭제"}
              </button>
            </div>
          </>,
          document.body
        )}

        {/* [PBE-RESIZE] 우하단 리사이즈 핸들 */}
        <div
          data-pbe-resize-edge="top"
          onMouseDown={(e) => handleResizeMouseDown(e, "top")}
          className="absolute left-3 right-3 top-0 h-2 cursor-ns-resize z-50"
          style={{ touchAction: "none" }}
        />
        <div
          data-pbe-resize-edge="bottom"
          onMouseDown={(e) => handleResizeMouseDown(e, "bottom")}
          className="absolute left-3 right-3 bottom-0 h-2 cursor-ns-resize z-50"
          style={{ touchAction: "none" }}
        />
        <div
          data-pbe-resize-edge="left"
          onMouseDown={(e) => handleResizeMouseDown(e, "left")}
          className="absolute left-0 top-3 bottom-3 w-2 cursor-ew-resize z-50"
          style={{ touchAction: "none" }}
        />
        <div
          data-pbe-resize-edge="right"
          onMouseDown={(e) => handleResizeMouseDown(e, "right")}
          className="absolute right-0 top-3 bottom-3 w-2 cursor-ew-resize z-50"
          style={{ touchAction: "none" }}
        />
        <div
          data-pbe-resize-edge="top-left"
          onMouseDown={(e) => handleResizeMouseDown(e, "top-left")}
          className="absolute left-0 top-0 h-3 w-3 cursor-nwse-resize z-50"
          style={{ touchAction: "none" }}
        />
        <div
          data-pbe-resize-edge="top-right"
          onMouseDown={(e) => handleResizeMouseDown(e, "top-right")}
          className="absolute right-0 top-0 h-3 w-3 cursor-nesw-resize z-50"
          style={{ touchAction: "none" }}
        />
        <div
          data-pbe-resize-edge="bottom-left"
          onMouseDown={(e) => handleResizeMouseDown(e, "bottom-left")}
          className="absolute bottom-0 left-0 h-3 w-3 cursor-nesw-resize z-50"
          style={{ touchAction: "none" }}
        />
        <div
          data-pbe-resize-edge="bottom-right"
          onMouseDown={(e) => handleResizeMouseDown(e, "bottom-right")}
          className="absolute bottom-0 right-0 h-3 w-3 cursor-nwse-resize z-50"
          style={{ touchAction: "none" }}
        />
      </LocalDialogContent>
    </Dialog>
  );
};
