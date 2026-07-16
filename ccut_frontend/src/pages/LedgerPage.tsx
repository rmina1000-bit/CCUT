/**
 * [SCRIPT-2e] 대본 v5 — 워드식 글자 단위 편집.
 * 국장 지시: 조각 통째 선택 폐기. 글자 한 자씩 지우고(회색=비활성) 되살린다(다시 타이핑).
 *  hover → 조각이 살짝 밝아짐(범위 인지, 사용자는 '조각'을 몰라도 됨)
 *  1클릭 → 재생 / 더블클릭 → 글자 사이에 커서 진입(워드식)
 *  지우기키 → 글자 삭제가 아니라 회색(비활성) = PBE 비활성 프레임과 동일(영상에서 제외)
 *  되살리기 → 커서 위치에서 그 글자를 다시 치면 활성(회색 해제)
 * 저장은 계약(EXCLUDE_RANGE) 그대로 — 원문 불변, 회색 글자의 시간만 제외.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Play } from "lucide-react";
import { videoService } from "@/services/videoService";

type MsRange = [number, number];
const PLAYBACK_STOP_EPS_MS = 6;

interface WordTok { w: string; s_ms: number; e_ms: number; p?: number | null; excluded?: boolean; }
interface ScriptItem {
  fragment_id: string;
  timeline_item_id: string;
  source_id?: string;
  revision?: number | null;
  words?: WordTok[];
  excluded_ranges?: number[][];
  anchor_start_ms?: number;
  anchor_end_ms?: number;
  trim_start_ms?: number;
  trim_end_ms?: number;
  dialogue?: string | null;
  stage_direction?: string | null;
  place?: string | null;
  original_text?: string | null;
  warnings?: string[];
  video_url?: string;
  missing?: { coords?: boolean };
  selected?: boolean;
}
interface ScriptData {
  ok: boolean;
  mode?: string;
  program_name?: string;
  running_ms?: number;
  stringout_count?: number;
  selected_count?: number;
  unselected_count?: number;
  excluded_count?: number;
  excluded_items?: ScriptItem[];
  items?: ScriptItem[];
}
interface EdlClip {
  order: number;
  source_id: string;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  fragment_id: string;
  clip_of?: string;
  video_url?: string;
}

interface Char { ch: string; s_ms: number | null; e_ms: number | null; }
interface Editing { itemId: string; chars: Char[]; inactive: Set<number>; caret: number; }

const SANS = `-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif`;

const fmtClock = (ms?: number) => {
  if (!ms || ms < 0) return "0:00";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

// 대사 단어 → 글자 배열 (글자별 시간 = 단어 시간을 글자 수로 균등 분할. 근사지만 결정론)
const wordsToChars = (words: WordTok[]): Char[] => {
  const chars: Char[] = [];
  words.forEach((w, wi) => {
    const arr = Array.from(w.w);
    const per = arr.length ? (w.e_ms - w.s_ms) / arr.length : 0;
    arr.forEach((ch, i) => chars.push({
      ch, s_ms: Math.round(w.s_ms + i * per), e_ms: Math.round(w.s_ms + (i + 1) * per),
    }));
    if (wi < words.length - 1) chars.push({ ch: " ", s_ms: null, e_ms: null });  // 단어 사이 공백(시간 없음)
  });
  return chars;
};

/** [STORY-GATE P3] 워크스페이스 안에 끼워 넣을 수 있게 props 수용.
 *  embedded=true면 자기 배경·프로젝트 선택기(페이지 껍데기)를 접고 본문만 낸다. */
interface LedgerPageProps { programId?: string; embedded?: boolean; onEditStateChanged?: () => void; }

const LedgerPage: React.FC<LedgerPageProps> = ({ programId: propProgramId, embedded, onEditStateChanged }) => {
  const [programs, setPrograms] = useState<Array<{ program_id: string; name: string }>>([]);
  const [programId, setProgramId] = useState<string>(() =>
    propProgramId || new URLSearchParams(window.location.search).get("program") || ""
  );
  // 부모(워크스페이스)가 프로젝트를 바꾸면 따라간다
  useEffect(() => {
    if (propProgramId && propProgramId !== programId) setProgramId(propProgramId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [propProgramId]);
  const [data, setData] = useState<ScriptData | null>(null);
  const [edlClips, setEdlClips] = useState<EdlClip[]>([]);
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const [playerOpen, setPlayerOpen] = useState(false);
  const [showOriginal, setShowOriginal] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const hiddenRef = useRef<HTMLInputElement>(null);
  const playRef = useRef<{ spans: MsRange[]; idx: number } | null>(null);

  useEffect(() => {
    if (embedded) return;  // 워크스페이스 안에서는 프로젝트 선택기가 없다 (부모가 정한다)
    videoService.listProjects?.().then((res: any) => {
      const list = Array.isArray(res) ? res : res?.projects || res?.programs || [];
      setPrograms(list.map((p: any) => ({ program_id: p.program_id ?? p.id, name: p.name ?? p.program_id })));
    }).catch(() => setPrograms([]));
  }, [embedded]);

  const reload = useCallback(() => {
    if (!programId) { setData(null); setEdlClips([]); return; }
    Promise.all([
      fetch(`/api/ledger/${encodeURIComponent(programId)}`).then((r) => r.json()),
      fetch(`/api/ledger/${encodeURIComponent(programId)}/edl`).then((r) => r.json()),
    ])
      .then(([ledger, edl]) => {
        setData(ledger);
        setEdlClips(Array.isArray(edl?.clips) ? edl.clips : []);
      })
      .catch(() => { setData(null); setEdlClips([]); });
  }, [programId]);
  useEffect(() => { reload(); }, [reload]);

  const scenes = useMemo(() => {
    const out: Array<{ heading: string | null; items: ScriptItem[] }> = [];
    let lastPlace: string | null | undefined = undefined;
    for (const it of data?.items ?? []) {
      if (it.missing?.coords) continue;
      const p = it.place ?? null;
      if (out.length === 0 || (p && p !== lastPlace)) {
        out.push({ heading: p, items: [it] });
        lastPlace = p ?? lastPlace ?? null;
      } else out[out.length - 1].items.push(it);
    }
    return out;
  }, [data]);

  const lostCount = useMemo(
    () => (data?.items ?? []).filter((it) => it.missing?.coords).length, [data]);

  const editingRef = useRef<Editing | null>(null);

  const edlSpansOf = useCallback((it: ScriptItem): MsRange[] => {
    if (it.selected === false) return [];
    return edlClips
      .filter((clip) => clip.fragment_id === it.fragment_id)
      .sort((a, b) => a.order - b.order)
      .map((clip) => [Math.round(clip.start_sec * 1000), Math.round(clip.end_sec * 1000)] as MsRange)
      .filter(([s, e]) => e > s);
  }, [edlClips]);

  // 미니 플레이어에 항목을 로드. autoplay=false면 미리듣기 대기(편집 중).
  const loadItem = useCallback((it: ScriptItem, autoplay: boolean) => {
    if (!it.video_url || it.anchor_start_ms === undefined) {
      videoRef.current?.pause();
      playRef.current = null;
      return;
    }
    const spans = edlSpansOf(it);
    if (spans.length === 0) {
      videoRef.current?.pause();
      playRef.current = null;
      return;
    }
    const v = videoRef.current;
    if (!v) return;
    playRef.current = { spans, idx: 0 };
    setActiveItem(it.timeline_item_id);
    setPlayerOpen(true);
    const url = it.video_url.startsWith("/") ? `/api${it.video_url.replace(/^\/api/, "")}` : it.video_url;
    v.onloadedmetadata = null;
    if (!v.src.endsWith(url) || v.readyState === 0 || v.error) { v.src = url; v.load(); }
    const playNow = () => {
      v.play().catch(() => {});
    };
    const start = () => {
      v.currentTime = spans[0][0] / 1000;
      if (autoplay) playNow();
    };
    if (v.readyState >= 1) start(); else v.onloadedmetadata = start;
  }, [edlSpansOf]);

  const playItem = useCallback((it: ScriptItem) => loadItem(it, true), [loadItem]);

  const rafRef = useRef<number | null>(null);
  const resumeRef = useRef(false);
  const LEAD = 90;

  const stopRaf = useCallback(() => {
    if (rafRef.current != null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
  }, []);

  const closePlayer = useCallback(() => {
    resumeRef.current = false;
    stopRaf();
    videoRef.current?.pause();
    if (videoRef.current) videoRef.current.onloadedmetadata = null;
    playRef.current = null;
    setPlayerOpen(false); setActiveItem(null);
  }, [stopRaf]);

  const rafTick = useCallback(() => {
    const v = videoRef.current, st = playRef.current;
    if (!v) { rafRef.current = null; return; }
    if (!st || st.spans.length === 0) {
      v.pause();
      rafRef.current = null;
      return;
    }
    if (v.ended || v.paused || v.seeking) { rafRef.current = null; return; }
    const t = v.currentTime * 1000;
    const lastEnd = st.spans[st.spans.length - 1]?.[1];
    if (lastEnd !== undefined && t >= lastEnd - PLAYBACK_STOP_EPS_MS) {
      resumeRef.current = false;
      v.pause();
      if (t > lastEnd) v.currentTime = lastEnd / 1000;
      rafRef.current = null;
      return;
    }
    const idx = st.spans.findIndex(([s, e]) => t >= s - 5 && t < e);
    if (idx < 0) {
      const nx = st.spans.find(([s]) => s > t - 5);
      if (nx) {
        resumeRef.current = true;
        v.pause();
        v.currentTime = nx[0] / 1000;
      } else {
        v.pause();
      }
      rafRef.current = null;
      return;
    }
    const [, e] = st.spans[idx];
    if (idx < st.spans.length - 1 && t >= e - LEAD) {
      resumeRef.current = true;
      v.pause();
      v.currentTime = st.spans[idx + 1][0] / 1000;
      rafRef.current = null;
    } else {
      rafRef.current = requestAnimationFrame(rafTick);
    }
  }, []);

  const startRaf = useCallback(() => {
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(rafTick);
  }, [rafTick]);

  const onSeeked = useCallback(() => {
    if (!resumeRef.current) return;
    const v = videoRef.current, st = playRef.current;
    resumeRef.current = false;
    if (!v || !st || st.spans.length === 0) { v?.pause(); return; }
    v.play().catch(() => {});
  }, []);

  const onPlay = useCallback(() => {
    const v = videoRef.current, st = playRef.current;
    if (!v || !st || st.spans.length === 0) {
      v?.pause();
      stopRaf();
      return;
    }
    const t = v.currentTime * 1000, lastEnd = st.spans[st.spans.length - 1][1];
    if (t >= lastEnd - 20) {
      v.currentTime = st.spans[0][0] / 1000;
    }
    startRaf();
  }, [startRaf, stopRaf]);

  const onPlaying = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    startRaf();
  }, [startRaf]);

  const onPlaybackTimeUpdate = useCallback(() => {
    const v = videoRef.current;
    const st = playRef.current;
    if (!v || !st || st.spans.length === 0) return;
    const endMs = st.spans[st.spans.length - 1][1];
    const currentMs = Math.round(v.currentTime * 1000);
    if (!v.paused && currentMs >= endMs) {
      v.pause();
      stopRaf();
    }
  }, [stopRaf]);

  // 저장 (EXCLUDE_RANGE / REMOVE / RESTORE 공통)
  const postEdit = useCallback(async (it: ScriptItem, body: Record<string, unknown>) => {
    const res = await fetch("/api/edit-state", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        program_id: programId, timeline_item_id: it.timeline_item_id, source_id: it.source_id,
        anchor_start_ms: it.anchor_start_ms, anchor_end_ms: it.anchor_end_ms,
        trim_start_ms: it.trim_start_ms ?? it.anchor_start_ms, trim_end_ms: it.trim_end_ms ?? it.anchor_end_ms,
        revision: it.revision ?? undefined, parent_fragment_id: it.fragment_id,
        origin: "TEXT_EDITOR", ...body,
      }),
    });
    return res.json();
  }, [programId]);

  const saveOrder = useCallback(async (items: ScriptItem[], selectedIds?: string[]) => {
    if (!programId) return null;
    const order = items.filter((it) => !it.missing?.coords).map((it) => it.fragment_id);
    const selected = selectedIds ?? items
      .filter((it) => !it.missing?.coords && it.selected !== false)
      .map((it) => it.fragment_id);
    const res = await fetch(`/api/ledger/${encodeURIComponent(programId)}/order`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: data?.mode, order, selected }),
    });
    return res.json();
  }, [programId, data?.mode]);

  const toggleItem = useCallback(async (it: ScriptItem) => {
    const items = data?.items ?? [];
    const nextSelected = it.selected === false;
    const selected = items
      .filter((x) => !x.missing?.coords && (x.timeline_item_id === it.timeline_item_id ? nextSelected : x.selected !== false))
      .map((x) => x.fragment_id);
    const r = await saveOrder(items, selected);
    if (!r?.ok) return;
    onEditStateChanged?.();
    reload();
  }, [data?.items, saveOrder, onEditStateChanged, reload]);

  // 문장 통째 삭제 (✕) — REMOVE
  const [undoInfo, setUndoInfo] = useState<{ item: ScriptItem; savedSec: number } | null>(null);
  const undoTimer = useRef<number | null>(null);
  const removeItem = useCallback(async (it: ScriptItem) => {
    if (activeItem === it.timeline_item_id) closePlayer();
    const r = await postEdit(it, { excluded_ranges: [], removed: true, command_type: "REMOVE" });
    if (!r?.ok) return;
    onEditStateChanged?.();
    setUndoInfo({ item: { ...it, revision: r.revision }, savedSec: ((it.anchor_end_ms ?? 0) - (it.anchor_start_ms ?? 0)) / 1000 });
    if (undoTimer.current) window.clearTimeout(undoTimer.current);
    undoTimer.current = window.setTimeout(() => setUndoInfo(null), 8000);
    reload();
  }, [activeItem, closePlayer, postEdit, reload, onEditStateChanged]);
  const undoRemove = useCallback(async () => {
    if (!undoInfo) return;
    const r = await postEdit(undoInfo.item, { excluded_ranges: [], removed: false, command_type: "RESTORE" });
    if (r?.ok) { onEditStateChanged?.(); setUndoInfo(null); reload(); }
  }, [undoInfo, postEdit, reload, onEditStateChanged]);

  // ── 워드식 글자 편집 ──────────────────────────────────────────────
  const enterEdit = useCallback((it: ScriptItem, caret = 0) => {
    if (!it.words || it.words.length === 0) return;
    const chars = wordsToChars(it.words);
    const inactive = new Set<number>();
    (it.excluded_ranges ?? []).forEach(([s, e]) => {
      chars.forEach((c, i) => { if (c.s_ms != null && c.s_ms < e && (c.e_ms ?? 0) > s) inactive.add(i); });
    });
    const ed = { itemId: it.timeline_item_id, chars, inactive, caret };
    editingRef.current = ed;
    setEditing(ed);
    loadItem(it, false);  // 미리듣기 준비 — 편집하며 재생 버튼으로 확인
    setTimeout(() => hiddenRef.current?.focus({ preventScroll: true }), 0);
  }, [loadItem]);

  // 편집 상태 변화를 즉시 재생 구간에 반영 (회색 바꾸면 재생도 따라감)
  useEffect(() => {
    editingRef.current = editing;
    if (!editing || !data?.items || !playRef.current) return;
    const it = data.items.find((x) => x.timeline_item_id === editing.itemId);
    if (it) playRef.current.spans = edlSpansOf(it);
  }, [editing, data, edlSpansOf]);

  const commitEdit = useCallback(async () => {
    setEditing((cur) => {
      if (!cur || !data?.items) return null;
      const it = data.items.find((x) => x.timeline_item_id === cur.itemId);
      if (it) {
        const ranges: number[][] = [];
        cur.inactive.forEach((i) => { const c = cur.chars[i]; if (c.s_ms != null) ranges.push([c.s_ms, c.e_ms!]); });
        postEdit(it, { excluded_ranges: ranges, removed: false, command_type: "EXCLUDE_RANGE" })
          .then((r) => { if (r?.ok) { onEditStateChanged?.(); reload(); } });
      }
      return null;
    });
  }, [data, postEdit, reload, onEditStateChanged]);

  const moveCaret = (from: number, dir: -1 | 1, chars: Char[]) => Math.max(0, Math.min(chars.length, from + dir));

  const onEditKey = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    const key = e.key;
    if (key === "Escape" || key === "Enter") { e.preventDefault(); commitEdit(); return; }
    if (!["ArrowLeft", "ArrowRight", "Home", "End", "Backspace", "Delete"].includes(key)) return;
    e.preventDefault();
    setEditing((cur) => {
      if (!cur) return cur;
      const { chars, caret, inactive } = cur;
      if (key === "ArrowLeft") return { ...cur, caret: moveCaret(caret, -1, chars) };
      if (key === "ArrowRight") return { ...cur, caret: moveCaret(caret, 1, chars) };
      if (key === "Home") return { ...cur, caret: 0 };
      if (key === "End") return { ...cur, caret: chars.length };
      if (key === "Backspace") {
        let p = caret - 1;
        while (p >= 0 && chars[p].s_ms == null) p--;   // 공백 건너뜀
        if (p < 0) return cur;
        const ni = new Set(inactive); ni.has(p) ? ni.delete(p) : ni.add(p);
        return { ...cur, inactive: ni, caret: p };
      }
      // Delete
      let p = caret;
      while (p < chars.length && chars[p].s_ms == null) p++;
      if (p >= chars.length) return cur;
      const ni = new Set(inactive); ni.has(p) ? ni.delete(p) : ni.add(p);
      return { ...cur, inactive: ni, caret: p + 1 };
    });
  }, [commitEdit]);

  // 되살리기 — 커서 위치에서 그 글자를 다시 치면 활성. IME(한글) 대응: composition/ input 양쪽.
  const handleTyped = useCallback((typed: string) => {
    if (!typed) return;
    setEditing((cur) => {
      if (!cur) return cur;
      const ni = new Set(cur.inactive);
      let c = cur.caret;
      for (const ch of Array.from(typed)) {
        while (c < cur.chars.length && cur.chars[c].s_ms == null) c++;  // 공백 스킵
        if (c < cur.chars.length && cur.chars[c].ch === ch) {
          ni.delete(c); c++;                        // 회색이면 되살리고, 활성이면 그냥 전진
        } else break;                               // 원문과 다르면 무시(원문 불변)
      }
      return { ...cur, inactive: ni, caret: c };
    });
  }, []);

  // 편집 중 캐럿 위치를 글자 클릭으로 옮김
  const caretTo = useCallback((i: number) => {
    setEditing((cur) => (cur ? { ...cur, caret: i } : cur));
    hiddenRef.current?.focus({ preventScroll: true });
  }, []);

  const stripPlace = (stage: string | null | undefined, heading: string | null) => {
    if (!stage) return null;
    if (!heading) return stage;
    const prefix = `(${heading}.`;
    if (!stage.startsWith(prefix)) return stage;
    const rest = stage.slice(prefix.length).replace(/^\s+/, "");
    return rest === ")" ? null : `(${rest}`;
  };

  const Caret = () => (
    <span className="inline-block w-px h-[1.05em] align-[-0.15em] mx-[0.5px]"
      style={{ background: "hsl(220,9%,90%)", animation: "ccutBlink 1s step-end infinite" }} />
  );

  let sceneNo = 0;

  return (
    <div className={embedded ? "" : "min-h-screen"}
      style={embedded ? { color: "hsl(220, 9%, 87%)" }
                      : { background: "hsl(228, 12%, 10%)", color: "hsl(220, 9%, 87%)" }}>
      <style>{`@keyframes ccutBlink{50%{opacity:0}}`}</style>

      <header className="max-w-2xl mx-auto px-6 pt-5 pb-1 flex items-baseline" style={{ fontFamily: SANS }}>
        {embedded ? (
          <span className="text-[17px] font-semibold">{data?.program_name ?? ""}</span>
        ) : (
          <select
            aria-label="프로젝트"
            className="bg-transparent text-[17px] font-semibold outline-none cursor-pointer appearance-none pr-2 hover:opacity-70 transition-opacity"
            style={{ color: "inherit" }}
            value={programId} onChange={(e) => setProgramId(e.target.value)}
          >
            <option value="" style={{ color: "#111" }}>대본 고르기…</option>
            {programs.map((p) => <option key={p.program_id} value={p.program_id} style={{ color: "#111" }}>{p.name}</option>)}
          </select>
        )}
        {data?.ok && (
          <span className="ml-auto text-xs tabular-nums opacity-50">
            {data.stringout_count ?? data.items?.length ?? 0} / {data.selected_count ?? 0} · {fmtClock(data.running_ms)}
          </span>
        )}
      </header>

      <main className={embedded ? "max-w-2xl mx-auto px-6 pb-8" : "max-w-2xl mx-auto px-6 pb-28"}
        style={{ fontFamily: SANS }}>
        {!programId && !embedded && <p className="pt-20 text-center text-sm opacity-50">위의 제목을 눌러 대본을 고르세요.</p>}

        {scenes.map((sc) => {
          sceneNo += 1;
          return (
            <section key={sceneNo} className="mt-6">
              <h2 className="mb-1 text-[15px] font-semibold select-none opacity-70">
                S#{sceneNo}.{sc.heading ? ` ${sc.heading}` : ""}
              </h2>
              <p className="text-[15px] leading-[1.7]">
                {sc.items.map((it) => {
                  const isActive = activeItem === it.timeline_item_id;
                  const isEditing = editing?.itemId === it.timeline_item_id;
                  const selected = it.selected !== false;
                  const dimmed = playerOpen && !isActive && !isEditing;
                  const stage = stripPlace(it.stage_direction, sc.heading);
                  const hallu = it.warnings?.includes("non_korean");
                  const hasExcl = (it.excluded_ranges?.length ?? 0) > 0;
                  const canEdit = !!(it.words && it.words.length);
                  const textOpacity = selected ? 1 : 0.34;
                  return (
                    <span
                      key={it.timeline_item_id}
                      onClick={(e) => {
                        if (isEditing) return;
                        if (e.detail >= 2) { if (canEdit) enterEdit(it, 0); }
                        else toggleItem(it);
                      }}
                      className="group/span rounded-[3px] transition-colors duration-150 px-[1px]"
                      style={{
                        cursor: isEditing ? "text" : "pointer",
                        opacity: dimmed ? 0.4 : 1,
                        // hover 시 조각이 '일어난다' — 다른 글자보다 약간 밝은 배경
                        background: isEditing ? "hsl(228,14%,15%)" : isActive ? "hsl(230,14%,16%)" : selected ? undefined : "hsl(228,10%,12%)",
                        color: `rgba(231,232,236,${textOpacity})`,
                      }}
                      onMouseEnter={(e) => { if (!isEditing && !isActive) e.currentTarget.style.background = "hsl(228,13%,14%)"; }}
                      onMouseLeave={(e) => { if (!isEditing && !isActive) e.currentTarget.style.background = selected ? "" : "hsl(228,10%,12%)"; }}
                    >
                      <span className="inline-flex align-[0.05em] opacity-0 group-hover/span:opacity-80 transition-opacity mr-1">
                        <button type="button" onClick={(e) => { e.stopPropagation(); playItem(it); }}
                          className="px-0.5 opacity-70 hover:opacity-100" title="재생"><Play size={11} /></button>
                      </span>
                      {!selected && <span className="text-[10px] align-super mr-1 opacity-70">off</span>}
                      {stage && <span>{stage} </span>}
                      {!stage && hallu && <span>(장면이 이어진다.) </span>}
                      {hallu && (
                        <button type="button"
                          onClick={(e) => { e.stopPropagation(); setShowOriginal(showOriginal === it.timeline_item_id ? null : it.timeline_item_id); }}
                          className="text-[10px] align-super opacity-30 hover:opacity-80 transition-opacity"
                          title="자막 인식이 불안정해 지문으로 표기했습니다">※</button>
                      )}
                      {showOriginal === it.timeline_item_id && (
                        <span className="text-[10.5px] opacity-40 break-all" style={{ fontFamily: "monospace" }}> [{it.original_text}] </span>
                      )}

                      {/* 대사 — 편집 모드면 글자 단위, 아니면 단어 단위(회색=비활성) */}
                      {it.dialogue && (
                        isEditing && editing ? (
                          <>
                            {editing.chars.map((c, i) => (
                              <React.Fragment key={i}>
                                {editing.caret === i && <Caret />}
                                <span
                                  onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); caretTo(i); }}
                                  style={editing.inactive.has(i)
                                    ? { color: "hsl(220,5%,45%)", textDecoration: "line-through" }
                                    : undefined}
                                >{c.ch === " " ? " " : c.ch}</span>
                              </React.Fragment>
                            ))}
                            {editing.caret === editing.chars.length && <Caret />}
                            <span>{" "}</span>
                          </>
                        ) : it.words && it.words.length ? (
                          it.words.map((w, wi) => (
                            <span key={wi} style={w.excluded ? { color: "hsl(220,5%,45%)", textDecoration: "line-through" } : undefined}>
                              {w.w}{" "}
                            </span>
                          ))
                        ) : <span>{it.dialogue} </span>
                      )}
                      {!it.dialogue && !stage && !hallu && <span>(조용한 장면.) </span>}

                      {hasExcl && !isEditing && (
                        <button type="button"
                          onClick={(e) => { e.stopPropagation(); postEdit(it, { excluded_ranges: [], removed: false, command_type: "EXCLUDE_RANGE" }).then((r) => { if (r?.ok) { onEditStateChanged?.(); reload(); } }); }}
                          className="text-[10px] align-super opacity-40 hover:opacity-90 transition-opacity px-0.5"
                          title="이 문장의 뺀 부분을 되살립니다">↩</button>
                      )}
                      {!isEditing && (
                        <button type="button"
                          onClick={(e) => { e.stopPropagation(); removeItem(it); }}
                          className="text-[11px] align-super opacity-0 group-hover/span:opacity-40 hover:!opacity-90 transition-opacity px-0.5"
                          title="이 장면을 대본에서 뺍니다 (영상에서도 빠집니다)">✕</button>
                      )}
                    </span>
                  );
                })}
              </p>
            </section>
          );
        })}

        {data?.ok && <p className="mt-10 text-center text-[12px] tracking-[0.3em] select-none opacity-40">끝</p>}
        {(data?.excluded_count ?? 0) > 0 && (
          <p className="mt-2 text-center text-[10.5px] opacity-40">
            대본에서 뺀 장면 {data?.excluded_count}개
            <button type="button"
              onClick={async () => { let changed = false; for (const ex of data?.excluded_items ?? []) { const r = await postEdit(ex, { excluded_ranges: [], removed: false, command_type: "RESTORE" }); changed = changed || !!r?.ok; } if (changed) onEditStateChanged?.(); reload(); }}
              className="ml-2 underline underline-offset-2 opacity-70 hover:opacity-100">모두 되돌리기</button>
          </p>
        )}
        {lostCount > 0 && (
          <p className="mt-2 text-center text-[10.5px] opacity-30">원본을 찾는 중인 장면 {lostCount}개는 잠시 접어두었습니다</p>
        )}
      </main>

      {/* 숨은 입력 — 글자 편집 키/타이핑(IME) 수신 */}
      <input
        ref={hiddenRef}
        onKeyDown={onEditKey}
        onInput={(e) => { if (!(e.nativeEvent as unknown as { isComposing: boolean }).isComposing) { handleTyped(e.currentTarget.value); e.currentTarget.value = ""; } }}
        onCompositionEnd={(e) => { handleTyped(e.currentTarget.value); e.currentTarget.value = ""; }}
        onBlur={() => { if (editing) commitEdit(); }}
        className="fixed opacity-0 w-px h-px pointer-events-none" style={{ left: -9999, top: 0 }}
        aria-hidden
      />

      {/* 편집 힌트 */}
      {editing && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-40 px-4 py-1.5 rounded-full text-[12px] opacity-90"
          style={{ background: "hsl(228,12%,17%)", fontFamily: SANS }}>
          지우기 키로 글자를 빼고, 다시 타이핑하면 살아납니다 · Esc로 끝
        </div>
      )}

      {/* 수정 확인 한 줄 */}
      {!editing && (
        <div className={`fixed bottom-5 left-1/2 -translate-x-1/2 z-40 transition-all duration-300 ${undoInfo ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2 pointer-events-none"}`}>
          <div className="px-4 py-2 rounded-full text-[13px] shadow-lg flex items-center gap-3" style={{ background: "hsl(228,12%,17%)", fontFamily: SANS }}>
            <span>장면 1개 제외 — 영상이 {undoInfo?.savedSec.toFixed(1)}초 짧아졌습니다</span>
            <button type="button" onClick={undoRemove} className="underline underline-offset-2 opacity-80 hover:opacity-100">되돌리기</button>
          </div>
        </div>
      )}

      {/* 플로팅 플레이어 — 양축 상한 */}
      <div className={`fixed bottom-5 right-5 z-30 transition-all duration-300 ${playerOpen ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3 pointer-events-none"}`}>
        <div className="rounded-xl overflow-hidden shadow-2xl inline-block" style={{ background: "#000" }}>
          <video ref={videoRef} onPlay={onPlay} onPlaying={onPlaying} onSeeked={onSeeked} onTimeUpdate={onPlaybackTimeUpdate} onPause={stopRaf} onEnded={stopRaf} controls className="block"
            style={{ maxWidth: "min(360px, 40vw)", maxHeight: "48vh", width: "auto", height: "auto" }} />
        </div>
        <button type="button" onClick={closePlayer}
          className="absolute -top-2.5 -right-2.5 w-6 h-6 rounded-full text-[11px] leading-none shadow-md hover:scale-110 transition-transform"
          style={{ background: "hsl(230,10%,25%)", color: "hsl(40,20%,85%)" }} title="닫기">✕</button>
      </div>
    </div>
  );
};

export default LedgerPage;
