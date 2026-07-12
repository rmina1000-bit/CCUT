/**
 * [DESIGN-1] 대본 v3 — 경쟁 조사 기반 재설계 (docs/CCUT_COMPETITIVE_EDGE_2026-07.md 6조).
 *  1 씬 헤딩 S#n(장소 변화 시만)  2 지문 단독 문단(무발화)  3 포커스 리딩(iA Writer)
 *  4 떠 있는 미니 플레이어(비디오가 화면을 지배하지 않음)  5 타임코드·ID·셀 추방
 *  6 즉답(스피너 없는 첫 페인트)
 * 원칙: 화면에 보이는 모든 픽셀은 사용자의 눈(읽기)과 손(클릭 한 번)을 위해서만 존재한다.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { videoService } from "@/services/videoService";

interface ScriptItem {
  fragment_id: string;
  timeline_item_id: string;
  source_id?: string;
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
  items?: ScriptItem[];
}

const SERIF = `"Noto Serif KR","Nanum Myeongjo","AppleMyungjo","Batang",serif`;

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

  useEffect(() => {
    if (!programId) { setData(null); return; }
    fetch(`/api/ledger/${encodeURIComponent(programId)}`)
      .then((r) => r.json()).then(setData).catch(() => setData(null));
  }, [programId]);

  // 씬 묶기: 장소가 바뀌는 지점마다 S#n 헤딩 (조사 결정 1)
  const scenes = useMemo(() => {
    const out: Array<{ heading: string | null; items: ScriptItem[] }> = [];
    let lastPlace: string | null | undefined = undefined;
    for (const it of data?.items ?? []) {
      if (it.missing?.coords) continue; // 좌표 잃은 조각은 대본 흐름에서 제외 (말미 각주로)
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

  // 씬 헤딩이 이미 말한 장소를 지문이 반복하지 않도록 (군더더기 제거)
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
    <div className="min-h-screen" style={{ background: "hsl(230, 12%, 9%)", color: "hsl(40, 20%, 88%)" }}>
      {/* 머리 — 프로그램 이름과 러닝타임 한 줄뿐 (조사 결정 5) */}
      <header className="max-w-2xl mx-auto px-6 pt-10 pb-2 flex items-baseline">
        <select
          aria-label="프로젝트"
          className="bg-transparent text-lg font-semibold outline-none cursor-pointer appearance-none pr-2 hover:opacity-70 transition-opacity"
          style={{ fontFamily: SERIF, color: "inherit" }}
          value={programId} onChange={(e) => setProgramId(e.target.value)}
        >
          <option value="" style={{ color: "#111" }}>대본 고르기…</option>
          {programs.map((p) => (
            <option key={p.program_id} value={p.program_id} style={{ color: "#111" }}>{p.name}</option>
          ))}
        </select>
        {data?.ok && (
          <span className="ml-auto text-xs tabular-nums" style={{ color: "hsl(40,10%,45%)" }}>
            {fmtClock(data.running_ms)}
          </span>
        )}
      </header>

      {/* 본문 — 대본만 존재한다 */}
      <main className="max-w-2xl mx-auto px-6 pb-40" style={{ fontFamily: SERIF }}>
        {!programId && (
          <p className="pt-24 text-center text-sm" style={{ color: "hsl(40,10%,40%)" }}>
            위의 제목을 눌러 대본을 고르세요.
          </p>
        )}

        {scenes.map((sc) => {
          sceneNo += 1;
          return (
            <section key={sceneNo}>
              {/* 씬 헤딩 — 방송대본 S# 문법 */}
              <h2
                className="mt-14 mb-6 text-[13px] tracking-[0.18em] select-none"
                style={{ color: "hsl(40,12%,52%)" }}
              >
                S#{sceneNo}.{sc.heading ? ` ${sc.heading}` : ""}
                <span className="block h-px mt-2" style={{ background: "hsl(40,10%,22%)" }} />
              </h2>

              {sc.items.map((it) => {
                const isActive = activeItem === it.timeline_item_id;
                const dimmed = playerOpen && !isActive;
                const stage = stripPlace(it.stage_direction, sc.heading);
                return (
                  <div
                    key={it.timeline_item_id}
                    onClick={() => playItem(it)}
                    className="group relative cursor-pointer rounded-md -mx-3 px-3 py-2.5 mb-3 transition-all duration-300"
                    style={{
                      opacity: dimmed ? 0.42 : 1,               // 포커스 리딩 (조사 결정 3)
                      background: isActive ? "hsl(230,14%,13%)" : undefined,
                    }}
                    onMouseEnter={(e) => { if (dimmed) e.currentTarget.style.opacity = "0.85"; }}
                    onMouseLeave={(e) => { if (dimmed) e.currentTarget.style.opacity = "0.42"; }}
                  >
                    {/* 재생 표식 — 여백에서만, hover 시 잉크처럼 */}
                    <span
                      className="absolute -left-6 top-3 text-[15px] opacity-0 group-hover:opacity-60 transition-opacity select-none"
                      style={{ color: "hsl(40,30%,70%)" }}
                    >▶</span>

                    {/* 지문 (이탤릭 · 들여쓰기) */}
                    {stage && (
                      <p className="italic text-[15px] leading-[1.9] pl-5" style={{ color: "hsl(40,12%,58%)" }}>
                        {stage}
                        {it.warnings?.includes("non_korean") && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setShowOriginal(showOriginal === it.timeline_item_id ? null : it.timeline_item_id);
                            }}
                            className="not-italic ml-2 text-[10px] align-middle opacity-30 hover:opacity-80 transition-opacity"
                            title="자막 인식이 불안정해 지문으로 표기했습니다"
                          >※원문</button>
                        )}
                      </p>
                    )}
                    {!stage && it.warnings?.includes("non_korean") && (
                      <p className="italic text-[14px] pl-5" style={{ color: "hsl(40,8%,44%)" }}>
                        (같은 장면이 이어진다.)
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setShowOriginal(showOriginal === it.timeline_item_id ? null : it.timeline_item_id);
                          }}
                          className="not-italic ml-2 text-[10px] align-middle opacity-30 hover:opacity-80 transition-opacity"
                          title="자막 인식이 불안정해 지문으로 표기했습니다"
                        >※원문</button>
                      </p>
                    )}
                    {showOriginal === it.timeline_item_id && (
                      <p className="pl-5 mt-1 text-[10.5px] break-all opacity-40" style={{ fontFamily: "monospace" }}>
                        {it.original_text}
                      </p>
                    )}

                    {/* 대사 (정체 · 크게) */}
                    {it.dialogue && (
                      <p className={`text-[17.5px] leading-[1.95] ${stage ? "mt-1.5" : ""}`}>
                        {it.dialogue}
                      </p>
                    )}

                    {/* 무발화·무지문 — 조용한 장면 */}
                    {!it.dialogue && !stage && !it.warnings?.includes("non_korean") && (
                      <p className="italic text-[14px] pl-5" style={{ color: "hsl(40,8%,40%)" }}>
                        (조용한 장면)
                      </p>
                    )}
                  </div>
                );
              })}
            </section>
          );
        })}

        {data?.ok && (
          <p className="mt-20 text-center text-[12px] tracking-[0.3em] select-none" style={{ color: "hsl(40,10%,35%)" }}>
            끝
          </p>
        )}
        {lostCount > 0 && (
          <p className="mt-4 text-center text-[10.5px]" style={{ color: "hsl(40,8%,32%)" }}>
            원본을 찾는 중인 장면 {lostCount}개는 잠시 접어두었습니다
          </p>
        )}
      </main>

      {/* 떠 있는 미니 플레이어 — 눈은 대본에 머문다 (조사 결정 4) */}
      <div
        className={`fixed bottom-5 right-5 z-30 transition-all duration-300 ${
          playerOpen ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3 pointer-events-none"
        }`}
      >
        <div className="rounded-xl overflow-hidden shadow-2xl inline-block" style={{ background: "#000" }}>
          {/* 가로·세로 동시 상한 — 세로영상은 높이 기준(화면 절반 이하), 가로영상은 폭 기준 */}
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
