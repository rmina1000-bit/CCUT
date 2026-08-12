import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SoundRoleControl } from "@/components/SoundRoleControl";
import type { SoundRole, SoundRoleItem } from "@/utils/soundRoleClient";

type MsRange = [number, number];

export type SoundMix = {
  key: "voice" | "ambience" | "noise";
  on: boolean;
  volume: number;
};

export type EditStatePayload = {
  fragmentUid: string;
  newStartSec: number;
  newEndSec: number;
  origStart: number;
  origEnd: number;
  segments: Array<{ startSec: number; endSec: number }>;
};

export type FragmentPanelContractState = {
  anchor_start_ms: number;
  anchor_end_ms: number;
  trim_start_ms: number;
  trim_end_ms: number;
  excluded_ranges: MsRange[];
  removed: boolean;
  revision: number;
};

export type FragmentPanelProps = {
  index: number;
  total: number;
  pos: number;
  contractState: FragmentPanelContractState;
  ids: { fragmentId: string; timelineItemId: string; sourceId: string };
  sourceLabel?: string;
  sourceStartMs?: number;
  sourceEndMs?: number;
  text: string;
  words: Array<{ w: string; s_ms: number; e_ms: number }>;
  frameUrls: string[];
  soundMix: SoundMix[];
  soundRole?: SoundRoleItem | null;
  soundRoleSaving?: boolean;
  onSoundRoleChange?: (item: SoundRoleItem, role: SoundRole) => void | Promise<void>;
  onApply: (payload: EditStatePayload) => void | Promise<unknown>;
  onSoundMix: (mix: SoundMix[]) => void;
  onSeek: (ms: number) => void;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
  onOpenBig: () => void;
  onRemoveFragment: () => void;
};

const MIN_GAP_MS = 60;
const MAX_GAP_MS = 6000;
const GAP_RATIO = 1.25;
const MIN_TRIM_MS = 300;
const WORD_LABEL_GAP_PX = 30;

const GAPS = [
  { v: 250, label: "0.25s" },
  { v: 500, label: "0.5s" },
  { v: 1000, label: "1s" },
  { v: "default" as const, label: "기본" },
  { v: 2000, label: "2s" },
] as const;

type GapChoice = number | "default";

const LANE_COLOR = {
  voice: "var(--ccut-voice, #6FB58C)",
  ambience: "#7E8FB8",
  noise: "#8A7A6E",
} as const;

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

function mergeRanges(ranges: MsRange[]): MsRange[] {
  const sorted = ranges
    .filter(([s, e]) => Number.isFinite(s) && Number.isFinite(e) && e > s)
    .sort((a, b) => a[0] - b[0]);
  const merged: MsRange[] = [];
  for (const range of sorted) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([Math.round(range[0]), Math.round(range[1])]);
  }
  return merged;
}

function subtractRange(ranges: MsRange[], removed: MsRange): MsRange[] {
  const [cutStart, cutEnd] = removed;
  const result: MsRange[] = [];
  for (const [start, end] of ranges) {
    if (end <= cutStart || start >= cutEnd) {
      result.push([start, end]);
      continue;
    }
    if (start < cutStart) result.push([start, cutStart]);
    if (end > cutEnd) result.push([cutEnd, end]);
  }
  return result.filter(([start, end]) => end - start >= 1);
}

function compileSpans(state: Pick<FragmentPanelContractState, "trim_start_ms" | "trim_end_ms" | "excluded_ranges">): MsRange[] {
  if (state.trim_end_ms <= state.trim_start_ms) return [];
  let spans: MsRange[] = [[state.trim_start_ms, state.trim_end_ms]];
  for (const excluded of state.excluded_ranges) spans = subtractRange(spans, excluded);
  return spans;
}

function cloneEditState(state: FragmentPanelContractState): FragmentPanelContractState {
  return { ...state, excluded_ranges: state.excluded_ranges.map(([start, end]) => [start, end]) };
}

function fingerprint(state: FragmentPanelContractState): string {
  return JSON.stringify([
    state.trim_start_ms,
    state.trim_end_ms,
    state.excluded_ranges,
    state.removed,
  ]);
}

function resolveGap(gap: GapChoice, spanMs: number, frameCount: number): number {
  return gap === "default" ? Math.max(Math.round(spanMs / Math.max(frameCount, 1)), MIN_GAP_MS) : gap;
}

function formatSeconds(ms: number): string {
  return `${(Math.max(0, ms) / 1000).toFixed(1)}초`;
}

function formatRangeSeconds([start, end]: MsRange, anchorStart: number): string {
  return `${((start - anchorStart) / 1000).toFixed(1)}–${((end - anchorStart) / 1000).toFixed(1)}초`;
}

function formatClock(ms: number | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  return `${minutes}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

function humanSoundLabel(key: SoundMix["key"]): string {
  if (key === "voice") return "대사";
  if (key === "ambience") return "배경";
  return "소음";
}

const FragmentPanel: React.FC<FragmentPanelProps> = ({
  index,
  total,
  pos,
  contractState,
  ids,
  sourceLabel,
  sourceStartMs,
  sourceEndMs,
  text,
  words,
  frameUrls,
  soundMix,
  soundRole = null,
  soundRoleSaving = false,
  onSoundRoleChange,
  onApply,
  onSoundMix,
  onSeek,
  onPrev,
  onNext,
  onClose,
}) => {
  const [state, setState] = useState<FragmentPanelContractState>(contractState);
  const [tab, setTab] = useState<"video" | "sound">("video");
  const [gapChoice, setGapChoice] = useState<GapChoice>("default");
  const [selectedRange, setSelectedRange] = useState<MsRange | null>(null);
  const [dragging, setDragging] = useState<"range" | "left" | "right" | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [lastSaveError, setLastSaveError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);
  const [pendingLeave, setPendingLeave] = useState<"prev" | "next" | "close" | null>(null);
  const [localMix, setLocalMix] = useState<SoundMix[]>(soundMix);
  const [cellWidth, setCellWidth] = useState(0);
  const initialStateRef = useRef<FragmentPanelContractState>(cloneEditState(contractState));
  const baselineRef = useRef(fingerprint(contractState));
  const trackRef = useRef<HTMLDivElement>(null);
  const dragStartRef = useRef<{ x: number; ms: number; at: number } | null>(null);
  const justSavedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveStateRef = useRef(state);

  useEffect(() => {
    const snapshot = cloneEditState(contractState);
    setState(snapshot);
    initialStateRef.current = snapshot;
    baselineRef.current = fingerprint(snapshot);
    saveStateRef.current = snapshot;
    setPendingLeave(null);
    setLastSaveError(null);
    setJustSaved(false);
  }, [ids.timelineItemId]);

  useEffect(() => setLocalMix(soundMix), [soundMix]);

  useEffect(() => {
    const cssCell = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--pbe-cell"));
    if (Number.isFinite(cssCell) && cssCell > 0) setCellWidth(cssCell);
  }, []);

  useEffect(() => () => {
    if (justSavedTimerRef.current) clearTimeout(justSavedTimerRef.current);
  }, []);

  const anchorStart = Math.round(state.anchor_start_ms);
  const anchorEnd = Math.max(anchorStart + 1, Math.round(state.anchor_end_ms));
  const spanMs = anchorEnd - anchorStart;
  const frameCount = Math.max(frameUrls.length, 1);
  const gapMs = resolveGap(gapChoice, spanMs, frameCount);
  const pixelsPerMs = cellWidth / gapMs;
  const cellCount = Math.max(1, Math.ceil(spanMs / gapMs));
  const trackWidth = cellCount * cellWidth;

  const xOf = useCallback((ms: number) => clamp((ms - anchorStart) * pixelsPerMs, 0, trackWidth), [anchorStart, pixelsPerMs, trackWidth]);
  const msOf = useCallback((x: number) => clamp(Math.round(anchorStart + x / pixelsPerMs), anchorStart, anchorEnd), [anchorEnd, anchorStart, pixelsPerMs]);

  const aliveSpans = useMemo(() => compileSpans(state), [state]);
  const aliveMs = aliveSpans.reduce((sum, [start, end]) => sum + end - start, 0);
  const excludedRanges = state.excluded_ranges;
  const excludedMs = excludedRanges.reduce((sum, [start, end]) => sum + end - start, 0);
  const isDirty = fingerprint(state) !== baselineRef.current;
  const activeGap = GAPS.find(({ v }) => resolveGap(v, spanMs, frameCount) === gapMs);
  const barCount = Math.max(1, Math.floor(trackWidth / 3));
  const overlapCount = useMemo(() => words.reduce((count, word, wordIndex) => (
    count + (words.slice(0, wordIndex).some((previous) => previous.e_ms > word.s_ms) ? 1 : 0)
  ), 0), [words]);
  const overlapWarning = words.length > 0 && overlapCount >= Math.ceil(words.length * 0.3);

  const buildApplyPayload = useCallback((nextState: FragmentPanelContractState): EditStatePayload => ({
    fragmentUid: ids.fragmentId,
    newStartSec: nextState.trim_start_ms / 1000,
    newEndSec: nextState.trim_end_ms / 1000,
    origStart: nextState.anchor_start_ms / 1000,
    origEnd: nextState.anchor_end_ms / 1000,
    segments: compileSpans(nextState).map(([start, end]) => ({
      startSec: start / 1000,
      endSec: end / 1000,
    })),
  }), [ids.fragmentId]);

  const updateState = useCallback((patch: Partial<FragmentPanelContractState>) => {
    const nextState = { ...saveStateRef.current, ...patch };
    setState(nextState);
    saveStateRef.current = nextState;
    setLastSaveError(null);
  }, []);

  const save = useCallback(async (): Promise<boolean> => {
    const nextState = cloneEditState(saveStateRef.current);
    try {
      setIsSaving(true);
      setLastSaveError(null);
      setJustSaved(false);
      await onApply(buildApplyPayload(nextState));
      initialStateRef.current = cloneEditState(nextState);
      baselineRef.current = fingerprint(nextState);
      setState(nextState);
      setJustSaved(true);
      if (justSavedTimerRef.current) clearTimeout(justSavedTimerRef.current);
      justSavedTimerRef.current = setTimeout(() => setJustSaved(false), 2000);
      setIsSaving(false);
      return true;
    } catch {
      setIsSaving(false);
      setLastSaveError("저장하지 못했어요. 다시 시도해 주세요.");
      return false;
    }
  }, [buildApplyPayload, onApply]);

  const rangeFromPointer = useCallback((event: { clientX: number }) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return msOf(event.clientX - rect.left);
  }, [msOf]);

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const ms = rangeFromPointer(event);
    if (ms == null) return;
    const target = (event.target as HTMLElement).dataset.handle;
    if (target === "left" || target === "right") {
      setDragging(target);
      dragStartRef.current = { x: event.clientX, ms, at: Date.now() };
    } else {
      setDragging("range");
      dragStartRef.current = { x: event.clientX, ms, at: Date.now() };
      setSelectedRange([ms, ms]);
    }
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging || !dragStartRef.current) return;
    const ms = rangeFromPointer(event);
    if (ms == null) return;
    if (dragging === "range") {
      const start = Math.min(dragStartRef.current.ms, ms);
      const end = Math.max(dragStartRef.current.ms, ms);
      setSelectedRange([start, end]);
      return;
    }
    const nextTrim = dragging === "left"
      ? clamp(ms, anchorStart, state.trim_end_ms - MIN_TRIM_MS)
      : clamp(ms, state.trim_start_ms + MIN_TRIM_MS, anchorEnd);
    updateState(dragging === "left" ? { trim_start_ms: nextTrim } : { trim_end_ms: nextTrim });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging || !dragStartRef.current) return;
    const started = dragStartRef.current;
    const elapsedMs = Date.now() - started.at;
    const endMs = rangeFromPointer(event) ?? started.ms;
    if (dragging === "range" && elapsedMs >= 120) {
      setSelectedRange([Math.min(started.ms, endMs), Math.max(started.ms, endMs)]);
      onSeek(endMs);
    } else if (dragging === "range") {
      setSelectedRange(null);
      onSeek(endMs);
    }
    setDragging(null);
    dragStartRef.current = null;
  };

  const expandToWordBoundary = useCallback((range: MsRange): MsRange => {
    const overlapping = words.filter((word) => word.e_ms > range[0] && word.s_ms < range[1]);
    if (!overlapping.length) return range;
    return [
      Math.max(anchorStart, Math.min(...overlapping.map((word) => word.s_ms))),
      Math.min(anchorEnd, Math.max(...overlapping.map((word) => word.e_ms))),
    ];
  }, [anchorEnd, anchorStart, words]);

  const cutSelectedRange = () => {
    if (!selectedRange || selectedRange[1] <= selectedRange[0]) return;
    const expanded = expandToWordBoundary(selectedRange);
    updateState({ excluded_ranges: mergeRanges([...excludedRanges, expanded]) });
    setSelectedRange(null);
  };

  const restoreRange = (range: MsRange) => {
    updateState({ excluded_ranges: subtractRange(excludedRanges, range) });
  };

  const discardAndLeave = useCallback(() => {
    if (!pendingLeave) return;
    const snapshot = cloneEditState(initialStateRef.current);
    setState(snapshot);
    saveStateRef.current = snapshot;
    setSelectedRange(null);
    const leave = pendingLeave;
    setPendingLeave(null);
    if (leave === "prev") onPrev();
    else if (leave === "next") onNext();
    else onClose();
  }, [onClose, onNext, onPrev, pendingLeave]);

  const leave = useCallback((action: "prev" | "next" | "close") => {
    if (action === "prev") onPrev();
    else if (action === "next") onNext();
    else onClose();
  }, [onClose, onNext, onPrev]);

  const requestLeave = useCallback((action: "prev" | "next" | "close") => {
    if (isDirty) setPendingLeave(action);
    else leave(action);
  }, [isDirty, leave]);

  const saveAndLeave = useCallback(async () => {
    if (!pendingLeave || !(await save())) return;
    const action = pendingLeave;
    setPendingLeave(null);
    leave(action);
  }, [leave, pendingLeave, save]);

  const zoomGap = (direction: -1 | 1) => {
    const next = direction < 0 ? gapMs / GAP_RATIO : gapMs * GAP_RATIO;
    setGapChoice(clamp(Math.round(next), MIN_GAP_MS, MAX_GAP_MS));
  };

  const visibleWords = useMemo(() => {
    let lastX = -Infinity;
    return words.flatMap((word, wordIndex) => {
      const x = xOf(word.s_ms);
      if (x - lastX < WORD_LABEL_GAP_PX) return [];
      lastX = x;
      const overlapN = words.reduce((count, other, otherIndex) => (
        count + (otherIndex !== wordIndex && other.s_ms < word.e_ms && other.e_ms > word.s_ms ? 1 : 0)
      ), 0);
      return [{ word, wordIndex, x, overlapN }];
    });
  }, [words, xOf]);

  const updateMix = (key: SoundMix["key"], patch: Partial<SoundMix>) => {
    const next = localMix.map((item) => item.key === key ? { ...item, ...patch } : item);
    setLocalMix(next);
    onSoundMix(next);
  };

  const ampOf = (key: SoundMix["key"], ms: number) => {
    if (key === "voice") {
      const hit = words.some((word) => ms >= word.s_ms && ms < word.e_ms);
      return hit ? 26 + Math.abs(Math.sin(ms / 78)) * 44 + Math.abs(Math.sin(ms / 23)) * 20 : 4.5;
    }
    if (key === "ambience") return 19 + Math.abs(Math.sin(ms / 420)) * 15 + Math.abs(Math.sin(ms / 97)) * 6;
    return 7 + Math.abs(Math.sin(ms / 150)) * 6;
  };

  const renderRanges = (className: string, ranges: MsRange[], rangeStyle?: React.CSSProperties) => ranges.map(([start, end], rangeIndex) => (
    <span
      key={`${start}-${end}-${rangeIndex}`}
      className={`absolute inset-y-0 ${className}`}
      style={{ ...rangeStyle, left: xOf(start), width: Math.max(1, xOf(end) - xOf(start)) }}
    />
  ));

  const renderWordsRow = () => (
    <div className="ccut-words relative h-[26px] min-w-0 overflow-hidden text-[10px]" style={{ width: trackWidth }} data-pbe-words="true">
      {visibleWords.map(({ word, wordIndex, x, overlapN }) => {
        const mid = (word.s_ms + word.e_ms) / 2;
        const dead = word.s_ms < state.trim_start_ms
          || word.e_ms > state.trim_end_ms
          || excludedRanges.some(([start, end]) => mid >= start && mid < end);
        const now = pos >= word.s_ms && pos < word.e_ms;
        return (
          <button
            key={`${word.s_ms}-${wordIndex}`}
            type="button"
            onClick={() => onSeek(word.s_ms)}
            className={[
              "absolute top-0 whitespace-nowrap border-l pl-1.5 pr-1 py-0.5",
              now ? "border-[var(--ccut-lit)] text-[var(--ccut-lit)]" : "border-[var(--ccut-line)] text-[var(--ccut-text-3)] hover:text-[var(--ccut-text-1)]",
              dead ? "opacity-30 line-through" : "",
            ].join(" ")}
            style={{ left: x }}
            title={`${word.s_ms}–${word.e_ms}ms`}
          >
            {word.w}{overlapN > 0 && <sup className="ml-0.5 text-[9px] text-[var(--ccut-lit)]">⁺{overlapN}</sup>}
          </button>
        );
      })}
    </div>
  );

  const renderKeepRow = () => (
    <div className="ccut-keep" style={{ width: trackWidth }} data-pbe-keep="true">
      <span className="ccut-keep-time is-start">{formatSeconds(0)}</span>
      <span className="ccut-keep-time is-end">{formatSeconds(spanMs)}</span>
    </div>
  );

  return (
    <section className="ccut-panel ccut-pbe-inline flex w-full min-w-0 flex-col gap-2 p-3" data-precision-pane="true">
      <header className="ccut-ph">
        <div className="ccut-ph-no">
          <button type="button" className="ccut-sym" onClick={() => requestLeave("prev")} aria-label="앞 조각">‹</button>
          <button type="button" className="ccut-sym" onClick={() => requestLeave("next")} aria-label="다음 조각">›</button>
          <span className="ccut-ph-count">{index + 1} / {total}</span>
        </div>
        <span className="ccut-ph-line" title={text}>{text || "이름 없는 조각"}</span>
        <div className="ccut-ph-tabs" role="tablist" aria-label="판 보기">
          <button type="button" className="ccut-act" onClick={() => setTab("video")} aria-pressed={tab === "video"}>영상</button>
          <button type="button" className="ccut-act" onClick={() => setTab("sound")} aria-pressed={tab === "sound"}>소리</button>
        </div>
        <button type="button" className="ccut-sym ccut-ph-close" onClick={() => requestLeave("close")} aria-label="닫기">✕</button>
      </header>

      <div className="ccut-ph2" data-pbe-identifiers="true">
        <span
          className="ccut-ph2-src"
          title={`사용본 ${ids.timelineItemId} · 조각 ${ids.fragmentId} · revision ${state.revision}`}
        >
          {sourceLabel
            ? `원본 ${sourceLabel} · ${formatClock(sourceStartMs)}–${formatClock(sourceEndMs)}`
            : "원본 위치 없음"}
        </span>
        {tab === "video" ? (
          <div className="ccut-ph2-right" data-pbe-gap="true">
            {!activeGap && <span className="ccut-gap-now">{(gapMs / 1000).toFixed(2)}s</span>}
            {GAPS.map(({ v, label }) => (
              <button key={label} type="button" className="ccut-act" onClick={() => setGapChoice(v)} aria-pressed={activeGap?.v === v}>
                {label}
              </button>
            ))}
            <button type="button" className="ccut-sym" onClick={() => zoomGap(-1)} disabled={gapMs <= MIN_GAP_MS} aria-label="더 촘촘히">−</button>
            <button type="button" className="ccut-sym" onClick={() => zoomGap(1)} disabled={gapMs >= MAX_GAP_MS} aria-label="더 성기게">+</button>
          </div>
        ) : (
          <div className="ccut-ph2-right" data-sound-role-row="true">
            <span className="text-[11px] text-[var(--ccut-text-2)]">편집에서 다룰 방식</span>
            {soundRole ? (
              <SoundRoleControl
                item={soundRole}
                saving={soundRoleSaving}
                onChange={onSoundRoleChange}
                className="!w-auto !min-w-[205px] border-b-0 px-0"
              />
            ) : (
              <span className="text-[10px] text-[var(--ccut-text-3)]">판정 자료 없음</span>
            )}
            {overlapCount > 0 && (
              <span className={overlapWarning ? "text-[11px] text-[var(--ccut-lit)]" : "text-[10px] text-[var(--ccut-text-3)]"} data-sound-overlap-warning="true">
                전사 단어 {overlapCount}개가 겹침
              </span>
            )}
          </div>
        )}
      </div>

      {tab === "video" ? (
        <>
          <div className="ccut-scrollx" data-pbe-track-scroll="true">
            <div style={{ width: trackWidth }}>
              <div
                ref={trackRef}
                className="ccut-track relative h-16 select-none touch-none"
                style={{ width: trackWidth }}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
                onClick={(event) => {
                  if (dragging) return;
                  const ms = rangeFromPointer(event);
                  if (ms != null) onSeek(ms);
                }}
                data-pbe-track="true"
              >
                {Array.from({ length: cellCount }, (_, cellIndex) => {
                  const cellStart = anchorStart + cellIndex * gapMs;
                  const imageIndex = frameUrls.length > 0
                    ? Math.min(frameUrls.length - 1, Math.floor(((cellStart - anchorStart) / Math.max(spanMs, 1)) * frameUrls.length))
                    : -1;
                  const url = imageIndex >= 0 ? frameUrls[imageIndex] : "";
                  return (
                  <span key={`${cellIndex}-${url}`} data-pbe-cell="true" className="absolute inset-y-0 overflow-hidden border-r border-[rgba(12,15,20,.5)]" style={{ left: cellIndex * cellWidth, width: cellWidth }}>
                    {url ? <img src={url} alt="" className="h-full w-full object-cover opacity-80" /> : null}
                    <small className="absolute bottom-0 right-0 px-0.5 text-[9px] text-white/30">{imageIndex >= 0 ? imageIndex : "—"}</small>
                  </span>
                  );
                })}
                {state.trim_start_ms > anchorStart && xOf(state.trim_start_ms) >= 40 && (
                  <span className="pointer-events-none absolute inset-y-0 z-10" style={{ left: 0, width: xOf(state.trim_start_ms) }}>
                    <span className="absolute inset-0 flex items-center justify-center text-[10px] text-[var(--ccut-text-3)]">앞 버림</span>
                  </span>
                )}
                {state.trim_end_ms < anchorEnd && (trackWidth - xOf(state.trim_end_ms)) >= 40 && (
                  <span className="pointer-events-none absolute inset-y-0 z-10" style={{ left: xOf(state.trim_end_ms), width: trackWidth - xOf(state.trim_end_ms) }}>
                    <span className="absolute inset-0 flex items-center justify-center text-[10px] text-[var(--ccut-text-3)]">뒤 버림</span>
                  </span>
                )}
                {renderRanges("bg-[rgba(12,15,20,.74)]", [[anchorStart, state.trim_start_ms], [state.trim_end_ms, anchorEnd]])}
                {renderRanges("", excludedRanges, { background: "repeating-linear-gradient(45deg, rgba(217,80,58,.42) 0 3px, rgba(18,12,10,.78) 3px 9px)" })}
                {selectedRange && <span className="pointer-events-none absolute inset-y-0 border border-[var(--ccut-lit)] bg-[var(--ccut-lit)]/10" style={{ left: xOf(selectedRange[0]), width: Math.max(1, xOf(selectedRange[1]) - xOf(selectedRange[0])) }} />}
                {selectedRange && selectedRange[1] > selectedRange[0] && (
                  <button
                    type="button"
                    className="ccut-pick-act"
                    style={{ left: xOf((selectedRange[0] + selectedRange[1]) / 2) }}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={(event) => { event.stopPropagation(); cutSelectedRange(); }}
                  >
                    {formatSeconds(selectedRange[1] - selectedRange[0])} 빼기
                  </button>
                )}
                <span data-handle="left" className="absolute inset-y-0 z-10 -ml-1.5 w-3 cursor-ew-resize" style={{ left: xOf(state.trim_start_ms) }}><i className="pointer-events-none absolute inset-y-0 left-1/2 w-[3px] -translate-x-1/2 bg-[#E4EEF7]" /></span>
                <span data-handle="right" className="absolute inset-y-0 z-10 -ml-1.5 w-3 cursor-ew-resize" style={{ left: xOf(state.trim_end_ms) }}><i className="pointer-events-none absolute inset-y-0 left-1/2 w-[3px] -translate-x-1/2 bg-[#E4EEF7]" /></span>
                <span className="pointer-events-none absolute inset-y-0 z-20 w-px bg-[var(--ccut-lit)]" style={{ left: xOf(pos) }} />
              </div>
              {renderWordsRow()}
              {renderKeepRow()}
            </div>
          </div>

        </>
      ) : (
        <div className="ccut-snd" data-pbe-sound="true">
          <div className="ccut-snd-controls">
            {(["voice", "ambience", "noise"] as const).map((key) => {
              const item = localMix.find((mix) => mix.key === key) ?? { key, on: true, volume: 1 };
              return (
                <div key={key} className={`ccut-snd-ctrl ${item.on ? "" : "is-off"}`} data-sound-mix-controls={key} data-sound-mix={key}>
                  <button type="button" className="ccut-snd-name" aria-pressed={item.on} onClick={() => updateMix(key, { on: !item.on })}>
                    {humanSoundLabel(key)}
                  </button>
                  <input
                    className="ccut-vol"
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value={item.volume}
                    onChange={(event) => updateMix(key, { volume: Number(event.target.value) })}
                    disabled={!item.on}
                    aria-label={`${humanSoundLabel(key)} 크기`}
                  />
                </div>
              );
            })}
          </div>
          <div className="ccut-snd-scroll ccut-scrollx" data-pbe-sound-scroll="true">
            <div style={{ width: trackWidth }}>
              {(["voice", "ambience", "noise"] as const).map((key) => {
                const item = localMix.find((mix) => mix.key === key) ?? { key, on: true, volume: 1 };
                return (
                  <div key={key} className={`ccut-snd-lane ${item.on ? "" : "is-off"}`} style={{ width: trackWidth }} data-sound-mix={key}>
                    {Array.from({ length: barCount }, (_, bar) => {
                      const ms = anchorStart + (bar * 3) / pixelsPerMs;
                      return <i key={bar} className="absolute top-1/2 w-[2px] -translate-y-1/2 rounded-[1px]" style={{ left: bar * 3, height: `${ampOf(key, ms)}%`, background: LANE_COLOR[key] }} />;
                    })}
                    {renderRanges("bg-[rgba(12,15,20,.74)]", [[anchorStart, state.trim_start_ms], [state.trim_end_ms, anchorEnd]])}
                    {renderRanges("", excludedRanges, { background: "repeating-linear-gradient(45deg, rgba(217,80,58,.42) 0 3px, rgba(18,12,10,.78) 3px 9px)" })}
                  </div>
                );
              })}
              {renderWordsRow()}
              {renderKeepRow()}
            </div>
          </div>
        </div>
      )}

      {excludedRanges.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 text-[10px] text-[var(--ccut-text-3)]" data-pbe-restores="true">
          {excludedRanges.map((range) => (
            <button key={`${range[0]}-${range[1]}`} type="button" className="ccut-act" title={`${range[0]}–${range[1]}ms`} onClick={() => restoreRange(range)}>
              {formatRangeSeconds(range, anchorStart)} 되살리기
            </button>
          ))}
        </div>
      )}

      <div className="ccut-foot" data-pbe-actions="true">
        <span className="ccut-foot-len">{formatSeconds(aliveMs)}{excludedMs > 0 ? ` · 가운데 ${formatSeconds(excludedMs)} 지움` : ""} · 원본 {formatSeconds(spanMs)} · 지금 {((Math.max(anchorStart, pos) - anchorStart) / 1000).toFixed(2)}초</span>
        <span className="ccut-foot-state">{isSaving ? "저장 중" : lastSaveError ? "저장하지 못했습니다" : justSaved ? "저장됨" : isDirty ? "바뀐 것이 있습니다" : ""}</span>
        <button type="button" className="ccut-save" disabled={isSaving} onClick={save}>저장</button>
      </div>

      {lastSaveError && <p className="ccut-warn" role="alert">{lastSaveError}</p>}

      {pendingLeave && (
        <p className="ccut-warn" data-pbe-leave-warning="true">
          저장하지 않은 것이 있습니다 · <button type="button" className="ccut-act" onClick={saveAndLeave}>저장</button> · <button type="button" className="ccut-act" onClick={discardAndLeave}>버리고 나가기</button>
        </p>
      )}
    </section>
  );
};

export default FragmentPanel;
