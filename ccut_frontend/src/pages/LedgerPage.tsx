/**
 * [DESIGN-1b] 대본 v4 — 흐르는 문단.
 * 국장 지시: 조각 단위 개행 금지(전부 이어붙임), 지문·대사 한 줄, 줄간격 압축(채팅 수준),
 * 폰트 최소화(본문 1종 + 헤딩 1종). 한 화면에 최대한 많은 대본이 들어온다.
 * 유지: S# 씬 헤딩 / 포커스 리딩 / 플로팅 플레이어(양축 상한) / 크롬 제로.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { videoService } from "@/services/videoService";

interface ScriptItem {
  fragment_id: string;
  timeline_item_id: string;
  source_id?: string;
  revision?: number | null;
  anchor_start_ms?: number;
  anchor_end_ms?: number;
  dialogue?: string | null;
  stage_direction?: string | null;
  place?: string | null;
  original_text?: string | null;
  warnings?: string[];
  video_url?: string;
  missing?: { coords?: boolean };
}

interface ScriptData {
  ok: boolean;
  program_name?: string;
  running_ms?: number;
  excluded_count?: number;
  excluded_items?: ScriptItem[];
  items?: ScriptItem[];
}

// 채팅(Claude) 화면과 동일한 시스템 산세리프 — 폰트 1종
const SANS = `-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif`;

const fmtClock = (ms?: number) => {
  if (!ms || ms < 0) return "0:00";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const LedgerPage: React.FC = () => {
  const [programs, setPrograms] = useState<Array<{ program_id: string; name: string }>>([]);
  const [programId, setProgramId] = useState<string>(() =>
    new URLSearchParams(window.location.search).get("program") || ""
  );
  const [data, setData] = useState<ScriptData | null>(null);
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const [playerOpen, setPlayerOpen] = useState(false);
  const [showOriginal, setShowOriginal] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const rangeRef = useRef<{ endSec: number } | null>(null);

  useEffect(() => {
    videoService.listProjects?.().then((res: any) => {
      const list = Array.isArray(res) ? res : res?.projects || res?.programs || [];
      setPrograms(list.map((p: any) => ({ program_id: p.program_id ?? p.id, name: p.name ?? p.program_id })));
    }).catch(() => setPrograms([]));
  }, []);

  const reload = useCallback(() => {
    if (!programId) { setData(null); return; }
    fetch(`/api/ledger/${encodeURIComponent(programId)}`)
      .then((r) => r.json()).then(setData).catch(() => setData(null));
  }, [programId]);
  useEffect(() => { reload(); }, [reload]);

  // 장소가 바뀌는 지점마다 씬 (S#n)
  const scenes = useMemo(() => {
    const out: Array<{ heading: string | null; items: ScriptItem[] }> = [];
    let lastPlace: string | null | undefined = undefined;
    for (const it of data?.items ?? []) {
      if (it.missing?.coords) continue;
      const p = it.place ?? null;
      if (out.length === 0 || (p && p !== lastPlace)) {
        out.push({ heading: p, items: [it] });
        lastPlace = p ?? lastPlace ?? null;
      } else {
        out[out.length - 1].items.push(it);
      }
    }
    return out;
  }, [data]);

  const lostCount = useMemo(
    () => (data?.items ?? []).filter((it) => it.missing?.coords).length,
    [data]
  );

  const playItem = useCallback((it: ScriptItem) => {
    if (!it.video_url || it.anchor_start_ms === undefined) return;
    setActiveItem(it.timeline_item_id);
    setPlayerOpen(true);
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

  const closePlayer = useCallback(() => {
    videoRef.current?.pause();
    setPlayerOpen(false);
    setActiveItem(null);
  }, []);

  // [SCRIPT-2] 문장 삭제 = 영상 구간 제외 (Edit State REMOVE — 승인된 편집만 저장)
  const [undoInfo, setUndoInfo] = useState<{
    item: ScriptItem; revision: number; savedSec: number;
  } | null>(null);
  const undoTimer = useRef<number | null>(null);

  const postState = useCallback(async (it: ScriptItem, removed: boolean, revision?: number) => {
    const res = await fetch("/api/edit-state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        program_id: programId,
        timeline_item_id: it.timeline_item_id,
        source_id: it.source_id,
        anchor_start_ms: it.anchor_start_ms,
        anchor_end_ms: it.anchor_end_ms,
        trim_start_ms: it.anchor_start_ms,
        trim_end_ms: it.anchor_end_ms,
        excluded_ranges: [],
        removed,
        revision,
        parent_fragment_id: it.fragment_id,
        command_type: removed ? "REMOVE" : "RESTORE",
        origin: "TEXT_EDITOR",
      }),
    });
    return res.json();
  }, [programId]);

  const removeItem = useCallback(async (it: ScriptItem) => {
    if (activeItem === it.timeline_item_id) closePlayer();
    const r = await postState(it, true, it.revision ?? undefined);
    if (!r?.ok) { console.error("[대본] 제외 실패:", r); return; }
    const savedSec = ((it.anchor_end_ms ?? 0) - (it.anchor_start_ms ?? 0)) / 1000;
    setUndoInfo({ item: it, revision: r.revision, savedSec });
    if (undoTimer.current) window.clearTimeout(undoTimer.current);
    undoTimer.current = window.setTimeout(() => setUndoInfo(null), 8000);
    reload();
  }, [activeItem, closePlayer, postState, reload]);

  const undoRemove = useCallback(async () => {
    if (!undoInfo) return;
    const r = await postState(undoInfo.item, false, undoInfo.revision);
    if (r?.ok) { setUndoInfo(null); reload(); }
    else console.error("[대본] 되돌리기 실패:", r);
  }, [undoInfo, postState, reload]);

  // Delete 키 = 선택(재생 중) 문장 제외
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (!activeItem || !data?.items) return;
      const it = data.items.find((x) => x.timeline_item_id === activeItem);
      if (it) { e.preventDefault(); removeItem(it); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeItem, data, removeItem]);

  // 씬 헤딩이 말한 장소를 지문이 반복하지 않는다
  const stripPlace = (stage: string | null | undefined, heading: string | null) => {
    if (!stage) return null;
    if (!heading) return stage;
    const prefix = `(${heading}.`;
    if (!stage.startsWith(prefix)) return stage;
    const rest = stage.slice(prefix.length).replace(/^\s+/, "");
    return rest === ")" ? null : `(${rest}`;
  };

  let sceneNo = 0;

  return (
    <div className="min-h-screen" style={{ background: "hsl(228, 12%, 10%)", color: "hsl(220, 9%, 87%)" }}>
      {/* 머리 — 제목과 러닝타임 한 줄 */}
      <header className="max-w-2xl mx-auto px-6 pt-5 pb-1 flex items-baseline" style={{ fontFamily: SANS }}>
        <select
          aria-label="프로젝트"
          className="bg-transparent text-[17px] font-semibold outline-none cursor-pointer appearance-none pr-2 hover:opacity-70 transition-opacity"
          style={{ color: "inherit" }}
          value={programId} onChange={(e) => setProgramId(e.target.value)}
        >
          <option value="" style={{ color: "#111" }}>대본 고르기…</option>
          {programs.map((p) => (
            <option key={p.program_id} value={p.program_id} style={{ color: "#111" }}>{p.name}</option>
          ))}
        </select>
        {data?.ok && (
          <span className="ml-auto text-xs tabular-nums opacity-50">{fmtClock(data.running_ms)}</span>
        )}
      </header>

      {/* 본문 — 씬당 흐르는 문단 하나. 지문(이탤릭)과 대사가 같은 줄에 이어진다. */}
      <main className="max-w-2xl mx-auto px-6 pb-28" style={{ fontFamily: SANS }}>
        {!programId && (
          <p className="pt-20 text-center text-sm opacity-50">위의 제목을 눌러 대본을 고르세요.</p>
        )}

        {scenes.map((sc) => {
          sceneNo += 1;
          return (
            <section key={sceneNo} className="mt-6">
              <h2 className="mb-1 text-[15px] font-semibold select-none opacity-70">
                S#{sceneNo}.{sc.heading ? ` ${sc.heading}` : ""}
              </h2>
              <p className="text-[15px] leading-[1.6]">
                {sc.items.map((it) => {
                  const isActive = activeItem === it.timeline_item_id;
                  const dimmed = playerOpen && !isActive;
                  const stage = stripPlace(it.stage_direction, sc.heading);
                  const hallu = it.warnings?.includes("non_korean");
                  return (
                    <span
                      key={it.timeline_item_id}
                      onClick={() => playItem(it)}
                      className="group/span cursor-pointer transition-all duration-200 underline-offset-4 decoration-1 hover:underline"
                      style={{
                        opacity: dimmed ? 0.4 : 1,
                        background: isActive ? "hsl(230,14%,16%)" : undefined,
                        textDecorationColor: "hsl(40,20%,45%)",
                      }}
                    >
                      {stage && <span>{stage} </span>}
                      {!stage && hallu && <span>(장면이 이어진다.) </span>}
                      {hallu && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setShowOriginal(showOriginal === it.timeline_item_id ? null : it.timeline_item_id);
                          }}
                          className="text-[10px] align-super opacity-30 hover:opacity-80 transition-opacity"
                          title="자막 인식이 불안정해 지문으로 표기했습니다"
                        >※</button>
                      )}
                      {showOriginal === it.timeline_item_id && (
                        <span className="text-[10.5px] opacity-40 break-all" style={{ fontFamily: "monospace" }}>
                          {" "}[{it.original_text}]{" "}
                        </span>
                      )}
                      {it.dialogue && <span>{it.dialogue} </span>}
                      {!it.dialogue && !stage && !hallu && (
                        <span>(조용한 장면.) </span>
                      )}
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); removeItem(it); }}
                        className="text-[11px] align-super opacity-0 group-hover/span:opacity-40 hover:!opacity-90 transition-opacity px-0.5"
                        title="이 장면을 대본에서 뺍니다 (영상에서도 빠집니다)"
                      >✕</button>
                    </span>
                  );
                })}
              </p>
            </section>
          );
        })}

        {data?.ok && (
          <p className="mt-10 text-center text-[12px] tracking-[0.3em] select-none opacity-40">끝</p>
        )}
        {(data?.excluded_count ?? 0) > 0 && (
          <p className="mt-2 text-center text-[10.5px] opacity-40">
            대본에서 뺀 장면 {data?.excluded_count}개
            <button
              type="button"
              onClick={async () => {
                for (const ex of data?.excluded_items ?? []) {
                  await postState(ex, false, ex.revision ?? undefined);
                }
                reload();
              }}
              className="ml-2 underline underline-offset-2 opacity-70 hover:opacity-100"
            >모두 되돌리기</button>
          </p>
        )}
        {lostCount > 0 && (
          <p className="mt-2 text-center text-[10.5px] opacity-30">
            원본을 찾는 중인 장면 {lostCount}개는 잠시 접어두었습니다
          </p>
        )}
      </main>

      {/* 수정 확인 한 줄 — 헌장 5조 (은은한 확인 + 되돌리기) */}
      <div
        className={`fixed bottom-5 left-1/2 -translate-x-1/2 z-40 transition-all duration-300 ${
          undoInfo ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2 pointer-events-none"
        }`}
      >
        <div
          className="px-4 py-2 rounded-full text-[13px] shadow-lg flex items-center gap-3"
          style={{ background: "hsl(228,12%,17%)", fontFamily: SANS }}
        >
          <span>장면 1개 제외 — 영상이 {undoInfo?.savedSec.toFixed(1)}초 짧아졌습니다</span>
          <button type="button" onClick={undoRemove} className="underline underline-offset-2 opacity-80 hover:opacity-100">
            되돌리기
          </button>
        </div>
      </div>

      {/* 플로팅 플레이어 — 양축 상한 (국장 확인 완료 크기 유지) */}
      <div
        className={`fixed bottom-5 right-5 z-30 transition-all duration-300 ${
          playerOpen ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3 pointer-events-none"
        }`}
      >
        <div className="rounded-xl overflow-hidden shadow-2xl inline-block" style={{ background: "#000" }}>
          <video
            ref={videoRef}
            onTimeUpdate={onTimeUpdate}
            controls
            className="block"
            style={{ maxWidth: "min(360px, 40vw)", maxHeight: "48vh", width: "auto", height: "auto" }}
          />
        </div>
        <button
          type="button"
          onClick={closePlayer}
          className="absolute -top-2.5 -right-2.5 w-6 h-6 rounded-full text-[11px] leading-none shadow-md hover:scale-110 transition-transform"
          style={{ background: "hsl(230,10%,25%)", color: "hsl(40,20%,85%)" }}
          title="닫기"
        >✕</button>
      </div>
    </div>
  );
};

export default LedgerPage;
