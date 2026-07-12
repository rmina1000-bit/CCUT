/**
 * [SCRIPT-1] 대본 — MASTER CONCEPT ①원고 / 헌장 v1.1 "대본(시나리오) 편집실".
 * 대본 = 대사(정체) + 지문(이탤릭). 지문 = AI가 장면 태그를 사람의 문장으로 번역한 본문.
 * 둘 다 Story Item: hover·클릭 재생 동등. 카드 나열 금지 — 워드/대본처럼 이어진 문서.
 * 환각 자막 구간은 대사 대신 지문으로 대체 표기(원문은 '원문 보기'에 보존).
 * 파일명·시간·ID·confidence는 본문에 들어오지 않는다(정보 은닉 — 필요 시 메타 줄에만).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { videoService } from "@/services/videoService";

interface ScriptItem {
  fragment_id: string;
  timeline_item_id: string;
  ledger_span_id?: string;
  source_id?: string;
  source_title?: string;
  anchor_start_ms?: number;
  anchor_end_ms?: number;
  dialogue?: string | null;
  stage_direction?: string | null;
  original_text?: string | null;
  no_subtitle_source?: boolean;
  warnings?: string[];
  scene_note_source?: string | null;
  video_url?: string;
  missing?: { coords?: boolean };
}

interface ScriptData {
  ok: boolean;
  program_id: string;
  program_name?: string;
  mode?: string;
  running_ms?: number;
  items?: ScriptItem[];
}

const fmtClock = (ms?: number) => {
  if (!ms || ms < 0) return "0:00";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const PlayIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="9" /><path d="M10 8.5l6 3.5-6 3.5v-7z" fill="currentColor" stroke="none" />
  </svg>
);

const LedgerPage: React.FC = () => {
  const [programs, setPrograms] = useState<Array<{ program_id: string; name: string }>>([]);
  const [programId, setProgramId] = useState<string>(() =>
    new URLSearchParams(window.location.search).get("program") || ""
  );
  const [data, setData] = useState<ScriptData | null>(null);
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const [showOriginal, setShowOriginal] = useState<Set<string>>(new Set());
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
      .then((r) => r.json()).then(setData).catch(() => setData(null));
  }, [programId]);

  const playItem = useCallback((it: ScriptItem) => {
    if (!it.video_url || it.anchor_start_ms === undefined) return;
    setActiveItem(it.timeline_item_id);
    const v = videoRef.current;
    if (!v) return;
    const startSec = (it.anchor_start_ms ?? 0) / 1000;
    rangeRef.current = { endSec: (it.anchor_end_ms ?? 0) / 1000 };
    const url = it.video_url.startsWith("/") ? `/api${it.video_url.replace(/^\/api/, "")}` : it.video_url;
    if (!v.src.endsWith(url) || v.readyState === 0 || v.error) { v.src = url; v.load(); }
    const seek = () => { v.currentTime = startSec; v.play().catch(() => {}); };
    if (v.readyState >= 1) seek(); else v.onloadedmetadata = seek;
  }, []);

  const onTimeUpdate = useCallback(() => {
    const v = videoRef.current, r = rangeRef.current;
    if (v && r && v.currentTime >= r.endSec) v.pause();
  }, []);

  const toggleOriginal = useCallback((id: string) => {
    setShowOriginal((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }, []);

  return (
    <div className="min-h-screen bg-[hsl(228,14%,7%)] text-foreground">
      {/* 상단 바 — 브레드크럼 + 러닝타임 (문단별 시간은 숨김) */}
      <header className="sticky top-0 z-20 bg-[hsl(228,14%,7%)]/95 backdrop-blur border-b border-border/10">
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center gap-3">
          <span className="font-bold tracking-tight">CCUT</span>
          <span className="text-muted-foreground/50">·</span>
          <select
            className="bg-transparent text-sm rounded px-1 py-0.5 outline-none hover:bg-secondary/40"
            value={programId} onChange={(e) => setProgramId(e.target.value)}
          >
            <option value="">프로젝트 선택…</option>
            {programs.map((p) => <option key={p.program_id} value={p.program_id}>{p.name}</option>)}
          </select>
          <span className="text-muted-foreground/40">›</span>
          <span className="text-sm text-primary font-medium">대본</span>
          <div className="ml-auto text-xs text-muted-foreground tabular-nums">
            {data?.ok && <>현재 <span className="text-foreground">{fmtClock(data.running_ms)}</span> <span className="opacity-40">/ 목표 —</span></>}
          </div>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6 py-5">
        {/* 재생창 — 대사/지문 어느 줄을 눌러도 그 장면 */}
        <div className="sticky top-14 z-10 bg-[hsl(228,14%,7%)] pb-3 -mx-1">
          <video ref={videoRef} onTimeUpdate={onTimeUpdate} controls className="w-full max-h-60 bg-black rounded-lg" />
        </div>

        {!data?.ok && programId && <p className="text-sm text-muted-foreground py-8 text-center">대본을 불러오는 중…</p>}
        {!programId && <p className="text-sm text-muted-foreground py-8 text-center">위에서 프로젝트를 선택하세요.</p>}

        {/* 대본 본문 — 지문(이탤릭) + 대사(정체)가 이어진 문서 */}
        <article className="space-y-5 pt-2">
          {(data?.items ?? []).map((it) => {
            const isActive = activeItem === it.timeline_item_id;
            const showOrig = showOriginal.has(it.timeline_item_id);
            const hasDialogue = !!it.dialogue;
            const hasStage = !!it.stage_direction;
            return (
              <section
                key={it.timeline_item_id}
                onClick={() => playItem(it)}
                className={`group relative cursor-pointer rounded-lg pl-4 pr-12 py-2.5 -ml-4 border-l-2 transition-colors ${
                  isActive ? "border-primary bg-secondary/40" : "border-transparent hover:bg-secondary/25"
                }`}
              >
                {/* 지문 (이탤릭, 은은한 톤) */}
                {hasStage && (
                  <p className="italic text-[14.5px] leading-relaxed text-muted-foreground/85">
                    {it.stage_direction}
                    {it.scene_note_source === "transcript" && (
                      <span className="ml-1.5 not-italic text-[10px] text-muted-foreground/40">(대사 기반 추정)</span>
                    )}
                  </p>
                )}

                {/* 대사 (정체) */}
                {hasDialogue && (
                  <p className={`text-[16px] leading-relaxed whitespace-pre-wrap ${hasStage ? "mt-1" : ""}`}>
                    {it.dialogue}
                  </p>
                )}

                {/* 환각 자막 → 지문으로 대체, 원문은 접어서 보존 */}
                {it.warnings?.includes("non_korean") && (
                  <div className="mt-1">
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); toggleOriginal(it.timeline_item_id); }}
                      className="text-[11px] text-amber-500/80 hover:text-amber-400"
                    >
                      ⚠ 자막 인식 불안정 — {showOrig ? "원문 숨기기" : "원문 보기"}
                    </button>
                    {showOrig && (
                      <p className="mt-1 text-[11px] text-muted-foreground/50 break-all font-mono">{it.original_text}</p>
                    )}
                  </div>
                )}

                {/* 대사도 지문도 없음 — 정직 표기 */}
                {!hasDialogue && !hasStage && !it.missing?.coords && (
                  <p className="italic text-[14px] text-muted-foreground/40">
                    {it.no_subtitle_source ? "(말 없는 장면 — 장면 설명 준비 중)" : "(조용한 장면)"}
                  </p>
                )}
                {it.missing?.coords && (
                  <p className="italic text-[13px] text-muted-foreground/40">(좌표를 찾지 못한 조각)</p>
                )}

                {/* 우측 재생/메뉴 — hover 시 (이미지의 ▶ / ⋮ 어포던스) */}
                <div className="absolute right-3 top-2.5 flex items-center gap-1 opacity-40 group-hover:opacity-100 transition-opacity">
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); playItem(it); }}
                    className="p-1 rounded-full hover:bg-secondary/60 text-muted-foreground hover:text-primary"
                    title="이 장면 재생"
                  >
                    <PlayIcon />
                  </button>
                  <span className="px-1 text-muted-foreground/30 select-none">⋮</span>
                </div>
              </section>
            );
          })}
        </article>

        {data?.ok && (
          <p className="text-[11px] text-muted-foreground/30 text-center pt-8 pb-4">
            — 대본 끝 · {data.items?.length ?? 0}개 장면 —
          </p>
        )}
      </div>
    </div>
  );
};

export default LedgerPage;
