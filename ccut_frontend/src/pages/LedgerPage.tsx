/**
 * [LEDGER-1] 원고 — MASTER CONCEPT ①원고의 첫 구현 (R0, 읽기 전용).
 * 카드 나열 금지: 워드 문서처럼 이어진 연속 원고. 문장을 클릭하면 해당 원본 구간이 재생된다.
 * 원문 접기/펼치기 = CSS 줄 접기만 (DB 원문 무변, AI 요약 0 — v1.1 패치 5).
 * 환각 의심(비한국어·저확률)은 제거하지 않고 경고 배지만 단다 (신호등 원칙).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { videoService } from "@/services/videoService";

interface LedgerItem {
  fragment_id: string;
  timeline_item_id: string;
  ledger_span_id?: string;
  source_id?: string;
  source_title?: string;
  anchor_start_ms?: number;
  anchor_end_ms?: number;
  text?: string | null;
  no_subtitle_source?: boolean;
  warnings?: string[];
  scene_note?: string | null;
  scene_note_source?: string | null;
  video_url?: string;
  missing?: { coords?: boolean };
}

interface LedgerData {
  ok: boolean;
  program_id: string;
  program_name?: string;
  mode?: string;
  sequence_count?: number;
  items?: LedgerItem[];
}

const fmtMs = (ms?: number) => {
  if (ms === undefined || ms === null) return "?";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const WARN_LABEL: Record<string, string> = {
  non_korean: "비한국어 반복 의심",
  low_probability: "저확률 구간",
};

const LedgerPage: React.FC = () => {
  const [programs, setPrograms] = useState<Array<{ program_id: string; name: string }>>([]);
  const [programId, setProgramId] = useState<string>(() =>
    new URLSearchParams(window.location.search).get("program") || ""
  );
  const [data, setData] = useState<LedgerData | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const rangeRef = useRef<{ endSec: number } | null>(null);

  useEffect(() => {
    videoService.listProjects?.().then((res: any) => {
      const list = Array.isArray(res) ? res : res?.projects || res?.programs || [];
      setPrograms(list.map((p: any) => ({ program_id: p.program_id ?? p.id, name: p.name ?? p.program_id })));
    }).catch(() => setPrograms([]));
  }, []);

  useEffect(() => {
    if (!programId) { setData(null); return; }
    fetch(`/api/ledger/${encodeURIComponent(programId)}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null));
  }, [programId]);

  const playItem = useCallback((it: LedgerItem) => {
    if (!it.video_url || it.anchor_start_ms === undefined) return;
    setActiveItem(it.timeline_item_id);
    const v = videoRef.current;
    if (!v) return;
    const startSec = (it.anchor_start_ms ?? 0) / 1000;
    rangeRef.current = { endSec: (it.anchor_end_ms ?? 0) / 1000 };
    const url = it.video_url.startsWith("/") ? `/api${it.video_url.replace(/^\/api/, "")}` : it.video_url;
    if (!v.src.endsWith(url) || v.readyState === 0 || v.error) { v.src = url; v.load(); } // 이전 로드 실패 회복
    const seek = () => { v.currentTime = startSec; v.play().catch(() => {}); };
    if (v.readyState >= 1) seek(); else v.onloadedmetadata = seek;
  }, []);

  const onTimeUpdate = useCallback(() => {
    const v = videoRef.current;
    const r = rangeRef.current;
    if (v && r && v.currentTime >= r.endSec) v.pause();
  }, []);

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-3xl mx-auto px-6 py-6">
        <div className="flex items-center gap-3 mb-4">
          <h1 className="text-xl font-bold">원고</h1>
          <select
            className="bg-secondary text-sm rounded px-2 py-1 border border-border/30"
            value={programId}
            onChange={(e) => setProgramId(e.target.value)}
          >
            <option value="">프로그램 선택…</option>
            {programs.map((p) => (
              <option key={p.program_id} value={p.program_id}>{p.name}</option>
            ))}
          </select>
          {data?.ok && (
            <span className="text-xs text-muted-foreground">
              {data.program_name} · {data.mode}안 · 항목 {data.items?.length ?? 0}
            </span>
          )}
        </div>

        {/* 재생창 — 문장을 클릭하면 해당 원본 구간 */}
        <div className="sticky top-0 z-10 bg-background pb-3">
          <video
            ref={videoRef}
            onTimeUpdate={onTimeUpdate}
            controls
            className="w-full max-h-64 bg-black rounded-md"
          />
        </div>

        {/* 연속 원고 — 카드 나열이 아니라 이어진 문서 */}
        {!data?.ok && programId && <p className="text-sm text-muted-foreground">원고를 불러오는 중…</p>}
        <article className="space-y-4 leading-relaxed">
          {(data?.items ?? []).map((it) => {
            const isActive = activeItem === it.timeline_item_id;
            const isOpen = expanded.has(it.timeline_item_id);
            return (
              <section
                key={it.timeline_item_id}
                onClick={() => playItem(it)}
                className={`group cursor-pointer rounded-md px-3 py-2 transition-colors border-l-2 ${
                  isActive ? "border-primary bg-secondary/50" : "border-transparent hover:bg-secondary/30"
                }`}
              >
                <div className="text-[11px] text-muted-foreground mb-1">
                  {it.source_title ?? it.source_id} · {fmtMs(it.anchor_start_ms)}–{fmtMs(it.anchor_end_ms)}
                  {(it.warnings ?? []).map((w) => (
                    <span key={w} className="ml-2 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-500">
                      ⚠ {WARN_LABEL[w] ?? w}
                    </span>
                  ))}
                </div>
                {it.missing?.coords ? (
                  <p className="text-sm text-muted-foreground italic">[좌표를 찾지 못한 조각: {it.fragment_id}]</p>
                ) : it.text ? (
                  <>
                    <p className={`text-[15px] whitespace-pre-wrap ${isOpen ? "" : "line-clamp-2"}`}>{it.text}</p>
                    {it.text.length > 80 && (
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); toggleExpand(it.timeline_item_id); }}
                        className="text-[11px] text-primary/80 hover:text-primary mt-0.5"
                      >
                        {isOpen ? "접기" : "펼치기"}
                      </button>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    {it.no_subtitle_source ? "[자막 없음]" : "[이 구간과 겹치는 발화 없음]"}
                  </p>
                )}
                {it.scene_note ? (
                  <p className="text-[12.5px] italic text-muted-foreground mt-1">
                    {it.scene_note_source === "transcript" ? "🏷 (대사 파생 태그) " : "👁 "}
                    {it.scene_note}
                  </p>
                ) : (
                  !it.missing?.coords && <p className="text-[11px] text-muted-foreground/60 mt-1">[장면설명 없음]</p>
                )}
              </section>
            );
          })}
        </article>
      </div>
    </div>
  );
};

export default LedgerPage;
