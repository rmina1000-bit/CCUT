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
import { FRAGMENT_TEXT_FONT, fragmentTextColor, FRAGMENT_EXCLUDED_STYLE } from "@/lib/fragmentText";
import { recordMirrorEvent } from "@/utils/mirrorEventLog";

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

// [#21 잔여] 조각 텍스트 폰트 단일 원천 — 우측 전사·중앙 스토리카드 공용.
const SANS = FRAGMENT_TEXT_FONT;

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
interface LedgerPageProps {
  programId?: string;
  embedded?: boolean;
  onEditStateChanged?: () => void;
  // [STORY-TRACK-A A-4] 텍스트조각 클릭 시 원본맵 동기화 콜백 — (fragment_id, source_id).
  onItemFocus?: (fragmentId: string, sourceId: string) => void;
  // [STORY-TRACK-B] 조각 재생을 공용 미니 창으로 위임 — 있으면 내부 미니 창 대신 이걸 쓴다
  // (하나의 미니 창으로 통일). sec spans canonical.
  onPlayItem?: (target: { videoUrl: string; spans: [number, number][]; fragmentId?: string; label?: string }) => void;
  // [#4 SOURCE-TITLE 2026-07-19] source_id -> 임시명(A,B,C…업로드순, 조각맵과 동일 매핑,
  // main.py _xl_label 원본). 전사에서 원본영상이 바뀌는 지점마다 대제목으로 표기한다.
  sourceLabels?: Record<string, string>;
}

const LedgerPage: React.FC<LedgerPageProps> = ({ programId: propProgramId, embedded, onEditStateChanged, onItemFocus, onPlayItem, sourceLabels }) => {
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
  const [saveError, setSaveError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const hiddenRef = useRef<HTMLInputElement>(null);
  const playRef = useRef<{ spans: MsRange[]; idx: number } | null>(null);
  const mirrorLedgerEnterRef = useRef<Set<string>>(new Set());

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
  useEffect(() => {
    if (!programId || !embedded) return;
    const key = `${programId}:embedded`;
    if (mirrorLedgerEnterRef.current.has(key)) return;
    mirrorLedgerEnterRef.current.add(key);
    recordMirrorEvent({
      event_kind: "continue",
      project_id: programId,
      origin: "LEDGER_EMBEDDED",
    });
  }, [programId, embedded]);

  // [#4 전사 전체화 2026-07-19] 장소(place) 기반 장면 그룹핑 폐기. 구획은 원본영상(source)
  // 단위 하나뿐 — 업로드순(sourceLabels 라벨 A,B,C…= main.py display_order)으로 그룹 정렬,
  // 그룹 안은 조각 시작시간순(ledger가 source_id,start 순으로 주므로 소스 내부는 이미 정렬됨).
  // ledger API는 7개 소스 77조각 전부 반환(missing.coords=0 실측) — 표시 계층이 전량을 낸다.
  const sourceGroups = useMemo(() => {
    const bySource = new Map<string, ScriptItem[]>();
    for (const it of data?.items ?? []) {
      if (it.missing?.coords) continue;
      const sid = it.source_id ?? "__unknown__";
      if (!bySource.has(sid)) bySource.set(sid, []);
      bySource.get(sid)!.push(it);
    }
    // 업로드순 = 라벨 순(A<B<…<G). 라벨 없으면 뒤로.
    const labelOf = (sid: string) => sourceLabels?.[sid] ?? "￿" + sid;
    return Array.from(bySource.entries())
      .map(([sid, items]) => ({ sourceId: sid, label: sourceLabels?.[sid] ?? null, items }))
      .sort((a, b) => labelOf(a.sourceId).localeCompare(labelOf(b.sourceId)));
  }, [data, sourceLabels]);

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

  // [STORY-TRACK-B] onPlayItem 있으면 공용 미니 창으로 위임(내부 창 미사용) — 창 1개 통일.
  // 없으면(단독 페이지) 기존 내부 미니 창 loadItem. spans는 edl(제외구간 반영) ms→sec.
  const playItem = useCallback((it: ScriptItem, fragNo?: string) => {
    if (onPlayItem && it.video_url && it.anchor_start_ms !== undefined) {
      let spansSec = edlSpansOf(it).map(([s, e]) => [s / 1000, e / 1000] as [number, number]);
      // [#20 비활성 조각 재생 2026-07-19] 비선택 조각은 edl이 없어 재생이 막혀 있었다.
      // 이 경로는 재생(playItem)일 뿐 선택 토글이 아니므로 활성 상태를 절대 바꾸지 않는다 —
      // edl이 비면 조각 자체 구간(anchor)으로 재생만 시켜준다.
      if (spansSec.length === 0 && it.anchor_end_ms !== undefined
          && it.anchor_end_ms > (it.anchor_start_ms ?? 0)) {
        spansSec = [[(it.anchor_start_ms ?? 0) / 1000, it.anchor_end_ms / 1000]];
      }
      if (spansSec.length > 0) {
        // [#20 잔여 2026-07-19] 플레이창 제목 = 조각번호(A1·D3)만. place("집안" 등 다른 단어) 금지.
        onPlayItem({ videoUrl: it.video_url, spans: spansSec,
                     fragmentId: it.fragment_id, label: fragNo || undefined });
        return;
      }
    }
    loadItem(it, true);
  }, [onPlayItem, edlSpansOf, loadItem]);

  const rafRef = useRef<number | null>(null);
  const resumeRef = useRef(false);
  const LEAD = 20; // [B2 #42] CenterPanel(R2)과 단일화 — 미달 방향 착지

  const stopRaf = useCallback(() => {
    if (rafRef.current != null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
  }, []);

  // [B3 #26] 전환 가드 — seek 진행(실측 23~50ms) 중 컴포지터가 그리는 중간 프레임(디코더
  // 키프레임 체인)의 노출 차단. CenterPanel CLIP_SWITCH_GUARD와 동일 규약:
  // 가림(opacity 0) → seek → seeked에서 복원 (+400ms 백업). 컨테이너 배경 유지 — 검은 플래시 없음.
  const hideForSeek = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    v.style.opacity = "0";
    let restored = false;
    const restore = () => {
      if (restored) return;
      restored = true;
      v.removeEventListener("seeked", restore);
      v.style.opacity = "1";
    };
    v.addEventListener("seeked", restore);
    setTimeout(restore, 400);
  }, []);

  // [B1 #41 — 단일 처리부·다중 트리거] span 경계 판정의 유일한 본체. 트리거는
  // ① rAF 루프(가시 탭, 정밀) ② timeupdate 백스톱(백그라운드 탭 — rAF 정지 환경).
  // 반환 true = 경계 처리(정지/전환) 수행됨.
  const checkSpanBoundary = useCallback((v: HTMLVideoElement, st: { spans: MsRange[] }): boolean => {
    const t = v.currentTime * 1000;
    const lastEnd = st.spans[st.spans.length - 1]?.[1];
    if (lastEnd !== undefined && t >= lastEnd - PLAYBACK_STOP_EPS_MS) {
      resumeRef.current = false;
      v.pause();
      if (t > lastEnd) v.currentTime = lastEnd / 1000;
      return true;
    }
    const idx = st.spans.findIndex(([s, e]) => t >= s - 5 && t < e);
    if (idx < 0) {
      const nx = st.spans.find(([s]) => s > t - 5);
      if (nx) {
        resumeRef.current = true;
        v.pause();
        hideForSeek();
        v.currentTime = nx[0] / 1000;
      } else {
        v.pause();
      }
      return true;
    }
    const [, e] = st.spans[idx];
    if (idx < st.spans.length - 1 && t >= e - LEAD) {
      resumeRef.current = true;
      v.pause();
      hideForSeek();
      v.currentTime = st.spans[idx + 1][0] / 1000;
      return true;
    }
    return false;
  }, [hideForSeek]);

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
    if (checkSpanBoundary(v, st)) {
      rafRef.current = null;
    } else {
      rafRef.current = requestAnimationFrame(rafTick);
    }
  }, [checkSpanBoundary]);

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
      hideForSeek(); // [B3] 재재생 되감기 seek도 가드
      v.currentTime = st.spans[0][0] / 1000;
    }
    startRaf();
  }, [startRaf, stopRaf, hideForSeek]);

  const onPlaying = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    startRaf();
  }, [startRaf]);

  // [B1 #41] timeupdate 백스톱 — 최종 끝만 보던 구멍을 전 경계 검사로.
  // 백그라운드 탭(브라우저가 rAF 정지)에서도 중간 제외 구간이 통재생되지 않는다 (헌장 §5).
  // 단일 처리부(checkSpanBoundary) 공유 — 가시 탭에서는 rAF가 20ms 리드로 선점하므로 중복 발화 없음.
  const onPlaybackTimeUpdate = useCallback(() => {
    const v = videoRef.current;
    const st = playRef.current;
    if (!v || !st || st.spans.length === 0) return;
    if (v.paused || v.seeking || v.ended) return;
    if (checkSpanBoundary(v, st)) stopRaf();
  }, [checkSpanBoundary, stopRaf]);

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

  // 저장 실패 공통 처리 — 무성 금지. 409(revision_conflict)는 낡은 화면이 원인이므로
  // reload로 revision을 최신화하고 재시도를 안내한다 (자동 재시도 금지 — 낡은 기준 덮어쓰기 위험).
  const reportEditFailure = useCallback((r: any) => {
    if (r?.error === "revision_conflict") {
      setSaveError(`저장 실패 — ${r?.message ?? "다른 화면의 수정이 먼저 반영됨"} · 원고를 새로고침했습니다, 다시 시도해 주세요.`);
      reload();  // 항목 revision 최신화
      return;
    }
    setSaveError(`저장 실패 — ${r?.message ?? r?.error ?? "알 수 없는 오류"}`);
  }, [reload]);

  // 문장 통째 삭제 (✕) — REMOVE
  const [undoInfo, setUndoInfo] = useState<{ item: ScriptItem; savedSec: number } | null>(null);
  const undoTimer = useRef<number | null>(null);
  const removeItem = useCallback(async (it: ScriptItem) => {
    if (activeItem === it.timeline_item_id) closePlayer();
    const r = await postEdit(it, { excluded_ranges: [], removed: true, command_type: "REMOVE" });
    if (!r?.ok) { reportEditFailure(r); return; }
    setSaveError(null);
    onEditStateChanged?.();
    setUndoInfo({ item: { ...it, revision: r.revision }, savedSec: ((it.anchor_end_ms ?? 0) - (it.anchor_start_ms ?? 0)) / 1000 });
    if (undoTimer.current) window.clearTimeout(undoTimer.current);
    undoTimer.current = window.setTimeout(() => setUndoInfo(null), 8000);
    reload();
  }, [activeItem, closePlayer, postEdit, reload, onEditStateChanged, reportEditFailure]);
  const undoRemove = useCallback(async () => {
    if (!undoInfo) return;
    const r = await postEdit(undoInfo.item, { excluded_ranges: [], removed: false, command_type: "RESTORE" });
    if (r?.ok) {
      recordMirrorEvent({
        event_kind: "undo",
        project_id: programId,
        fragment_id: undoInfo.item.fragment_id,
        timeline_item_id: undoInfo.item.timeline_item_id,
        command_type: "RESTORE",
        origin: "TEXT_EDITOR",
      });
      setSaveError(null); onEditStateChanged?.(); setUndoInfo(null); reload();
    }
    else reportEditFailure(r);
  }, [undoInfo, postEdit, reload, onEditStateChanged, reportEditFailure, programId]);

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
    setSaveError(null);
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
    const cur = editingRef.current;
    editingRef.current = null;  // Enter 직후 blur가 또 커밋하는 이중 발사 차단
    setEditing(null);
    if (!cur || !data?.items) return;
    const it = data.items.find((x) => x.timeline_item_id === cur.itemId);
    if (!it) return;
    // 길이 0 구간(ASR 좌표 s_ms==e_ms)은 계약 위반이라 서버가 거부한다 — 전송에서 제외
    const ranges: number[][] = [];
    let droppedZero = 0;
    cur.inactive.forEach((i) => {
      const c = cur.chars[i];
      if (c.s_ms == null || c.e_ms == null) return;
      if (c.e_ms > c.s_ms) ranges.push([c.s_ms, c.e_ms]);
      else droppedZero += 1;
    });
    // 전부 길이 0이면 저장할 시간 구간이 없다 — 빈 배열 POST는 RESTORE(기존 편집 삭제)가 되므로 생략
    if (ranges.length === 0 && droppedZero > 0) return;
    const restoreEditing = () => {
      setEditing((now) => now ?? cur);  // 사용자가 다른 문장 편집을 시작했으면 덮어쓰지 않는다
      setTimeout(() => hiddenRef.current?.focus({ preventScroll: true }), 0);
    };
    try {
      const r = await postEdit(it, { excluded_ranges: ranges, removed: false, command_type: "EXCLUDE_RANGE" });
      if (r?.ok) { setSaveError(null); onEditStateChanged?.(); reload(); return; }
      reportEditFailure(r);  // 409면 reload로 revision 최신화 — 편집 내용은 아래에서 보존, 재시도 가능
      restoreEditing();
    } catch (e) {
      setSaveError(`저장 실패 — ${String(e)}`);
      restoreEditing();
    }
  }, [data, postEdit, reload, onEditStateChanged, reportEditFailure]);

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


  const Caret = () => (
    <span className="inline-block w-px h-[1.05em] align-[-0.15em] mx-[0.5px]"
      style={{ background: "hsl(220,9%,90%)", animation: "ccutBlink 1s step-end infinite" }} />
  );

  return (
    <div className={embedded ? "" : "min-h-screen"}
      style={embedded ? { color: "hsl(220, 9%, 87%)" }
                      : { background: "hsl(228, 12%, 10%)", color: "hsl(220, 9%, 87%)" }}>
      <style>{`@keyframes ccutBlink{50%{opacity:0}}`}</style>

      {/* [#21-c 2026-07-19] 우측 정렬 — 임베디드 전사는 max-w-2xl 제거. 좌측(px-2 → x=572)은
          원본맵 첫 조각(573)과 이미 정렬, 우측은 max-w-2xl(672px 캡)이 1236에서 잘려 원본맵
          패널 우측선(1272)보다 36px 짧던 것을 컬럼 전폭으로 넓혀 우측선 일치. */}
      <header className={`${embedded ? "px-2" : "max-w-2xl mx-auto px-6"} pt-5 pb-1 flex items-baseline`} style={{ fontFamily: SANS }}>
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

      <main className={embedded ? "px-2 pb-8" : "max-w-2xl mx-auto px-6 pb-28"}
        style={{ fontFamily: SANS }}>
        {!programId && !embedded && <p className="pt-20 text-center text-sm opacity-50">위의 제목을 눌러 대본을 고르세요.</p>}

        {sourceGroups.map((grp) => {
          // [#4 전사 전체화] 구획 헤더 = 원본영상 임시명(X영상) 하나뿐. S#n 장소 헤더 폐기.
          // 라벨을 모르면(sourceLabels 미주입) 대제목을 안 그린다 — 틀린 값보다 침묵.
          // [#21 타이포 극단 재단 2026-07-19] 섹션 간격 최소화(mt-6→mt-1). 제호는 본문과
          // 동일 폰트·행간(text-[15px] leading-[1.7]) — 굵기(bold)로만 구분, 크게 띄우던
          // 제호 여백(mt-10 mb-2) 제거. 전사가 한 호흡으로 촘촘히 읽히게.
          return (
            <section key={grp.sourceId} className="mt-1">
              {grp.label && (
                <h1 className="mt-2 mb-0 text-[15px] leading-[1.7] font-bold select-none opacity-90">
                  {grp.label}영상
                </h1>
              )}
              <p className="text-[15px] leading-[1.7]">
                {grp.items.map((it, itemIdx) => {
                  // [#20 잔여] 조각번호 = 소스라벨 + 그룹내 순번(A1·D3…) — 조각맵 번호와 동일.
                  const fragNo = grp.label ? `${grp.label}${itemIdx + 1}` : "";
                  const isActive = activeItem === it.timeline_item_id;
                  const isEditing = editing?.itemId === it.timeline_item_id;
                  const selected = it.selected !== false;
                  const dimmed = playerOpen && !isActive && !isEditing;
                  const hallu = it.warnings?.includes("non_korean");
                  const hasExcl = (it.excluded_ranges?.length ?? 0) > 0;
                  const canEdit = !!(it.words && it.words.length);
                  const textColor = fragmentTextColor(selected);
                  return (
                    <span
                      key={it.timeline_item_id}
                      onClick={(e) => {
                        if (isEditing) return;
                        if (e.detail >= 2) { if (canEdit) enterEdit(it, 0); }
                        else {
                          // [A-4] 원본맵 동기화 — 강조는 활성/비활성 토글과 무관하게 항상.
                          if (it.fragment_id && it.source_id) onItemFocus?.(it.fragment_id, it.source_id);
                          // [#17 클릭 분리 2026-07-19] 텍스트조각 1클릭 = 활성/비활성 토글만.
                          // 재생(미니창)은 전사 앞 플레이 아이콘(아래 <Play> 버튼)에서만 — 클릭마다
                          // 창이 뜨던 동작 제거(playItem 호출 삭제). 더블클릭=편집 진입은 유지.
                          toggleItem(it);
                        }
                      }}
                      className="group/span rounded-[3px] transition-colors duration-150 px-[1px]"
                      style={{
                        cursor: isEditing ? "text" : "pointer",
                        opacity: dimmed ? 0.4 : 1,
                        // hover 시 조각이 '일어난다' — 다른 글자보다 약간 밝은 배경
                        background: isEditing ? "hsl(228,14%,15%)" : isActive ? "hsl(230,14%,16%)" : selected ? undefined : "hsl(228,10%,12%)",
                        color: textColor,
                      }}
                      onMouseEnter={(e) => { if (!isEditing && !isActive) e.currentTarget.style.background = "hsl(228,13%,14%)"; }}
                      onMouseLeave={(e) => { if (!isEditing && !isActive) e.currentTarget.style.background = selected ? "" : "hsl(228,10%,12%)"; }}
                    >
                      <span className="inline-flex align-[0.05em] opacity-0 group-hover/span:opacity-80 transition-opacity mr-1">
                        <button type="button" onClick={(e) => { e.stopPropagation(); playItem(it, fragNo); }}
                          className="px-0.5 opacity-70 hover:opacity-100" title="재생"><Play size={11} /></button>
                      </span>
                      {/* off 배지 — 폭 0 앵커 + absolute 오버레이(재생 슬롯 위). 줄박스 폭·높이 기여 0 = 토글해도 리플로우 없음 */}
                      {!selected && (
                        <span className="relative inline-block w-0 pointer-events-none select-none" aria-hidden>
                          <span className="absolute text-[10px] opacity-70 whitespace-nowrap" style={{ left: "-1.35em", top: "-0.95em" }}>off</span>
                        </span>
                      )}
                      {/* [#18 근본 2026-07-19] 지문(stage_direction, VL "병원" 등 장소 번역)
                          표시 제거 — 조각 텍스트의 진실 원천은 클램프 words 하나. 원문 밖 단어 0. */}
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
                                    ? FRAGMENT_EXCLUDED_STYLE
                                    : undefined}
                                >{c.ch === " " ? " " : c.ch}</span>
                              </React.Fragment>
                            ))}
                            {editing.caret === editing.chars.length && <Caret />}
                            <span>{" "}</span>
                          </>
                        ) : it.words && it.words.length ? (
                          it.words.map((w, wi) => (
                            <span key={wi} style={w.excluded ? FRAGMENT_EXCLUDED_STYLE : undefined}>
                              {w.w}{" "}
                            </span>
                          ))
                        ) : <span>{it.dialogue} </span>
                      )}
                      {/* [#18 근본] 무음(words·dialogue 둘 다 없음) = 계층 공통 마커 하나.
                          [#21-c 2026-07-19] 색 계약 위반 교정 — opacity-40 하드코딩 제거.
                          무음도 일반 조각과 같은 규칙: 부모 색(활성=흰색 rgba1 / 비활성=회색 rgba0.34)을
                          그대로 상속. 마커 자체 opacity가 곱연산으로 활성=0.4·비활성=0.136 이중감광되던 것 제거. */}
                      {!(it.words && it.words.length) && !it.dialogue && <span>(무음) </span>}

                      {hasExcl && !isEditing && (
                        <button type="button"
                          onClick={(e) => { e.stopPropagation(); postEdit(it, { excluded_ranges: [], removed: false, command_type: "EXCLUDE_RANGE" }).then((r) => { if (r?.ok) { setSaveError(null); onEditStateChanged?.(); reload(); } else reportEditFailure(r); }); }}
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
              onClick={async () => { let changed = false; let firstFail: any = null; for (const ex of data?.excluded_items ?? []) { const r = await postEdit(ex, { excluded_ranges: [], removed: false, command_type: "RESTORE" }); changed = changed || !!r?.ok; if (!r?.ok && !firstFail) firstFail = r; } if (changed) onEditStateChanged?.(); if (firstFail) reportEditFailure(firstFail); else { setSaveError(null); reload(); } }}
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
        // [가 a11y] aria-hidden 제거 — 이 input은 IME/키 수신 위해 프로그램적으로
        // 포커스를 받는다. 포커스 가능 요소의 aria-hidden이 콘솔 경고 원인이었다.
        // inert는 포커스를 막아 기능이 깨지므로, 탭 순서 제외(tabIndex=-1)+라벨로 대체.
        tabIndex={-1}
        aria-label="대본 편집 입력"
      />

      {/* 저장 실패 표시 — 침묵 금지 (원인 문구 포함) */}
      {saveError && (
        <div className="fixed bottom-14 left-1/2 -translate-x-1/2 z-40 px-4 py-1.5 rounded-full text-[12px]"
          style={{ background: "hsl(0,45%,24%)", color: "hsl(0,30%,92%)", fontFamily: SANS }}
          role="alert">
          {saveError}
          <button type="button" onClick={() => setSaveError(null)}
            className="ml-3 underline underline-offset-2 opacity-80 hover:opacity-100">닫기</button>
        </div>
      )}

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

      {/* 플로팅 플레이어 — 양축 상한. [oracle #5 수정] onPlayItem(공용 미니창 위임)이 있으면
          이 내부 플레이어를 렌더하지 않는다 — 두 창 공존(복사)을 하나로 통일(Track B 완결). */}
      {!onPlayItem && (
        <div className={`fixed bottom-5 right-5 z-30 transition-all duration-300 ${playerOpen ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3 pointer-events-none"}`}>
          <div className="rounded-xl overflow-hidden shadow-2xl inline-block" style={{ background: "#000" }}>
            <video ref={videoRef} onPlay={onPlay} onPlaying={onPlaying} onSeeked={onSeeked} onTimeUpdate={onPlaybackTimeUpdate} onPause={stopRaf} onEnded={stopRaf} controls className="block"
              style={{ maxWidth: "min(360px, 40vw)", maxHeight: "48vh", width: "auto", height: "auto" }} />
          </div>
          <button type="button" onClick={closePlayer}
            className="absolute -top-2.5 -right-2.5 w-6 h-6 rounded-full text-[11px] leading-none shadow-md hover:scale-110 transition-transform"
            style={{ background: "hsl(230,10%,25%)", color: "hsl(40,20%,85%)" }} title="닫기">✕</button>
        </div>
      )}
    </div>
  );
};

export default LedgerPage;
