// [STORY-TRACK-B] 조각 단위 공용 미니 플레이창.
// LedgerPage loadItem 미니 창(검증된 rAF 경계 로직)을 독립 컴포넌트로 승격 — 텍스트조각·
// 이미지조각 어디서 클릭해도 이 창 하나로 재생한다(§7-1/§7-2). A/B 비교 듀얼(CenterPanel
// playFrag)은 무관·무접촉.
//
// 입력 좌표 = sec 단일(canonical). 호출측이 frame→sec(readFragmentStartSec)·ms→sec(/1000)
// 변환을 마친 sec spans를 넘긴다. 내부는 sec 하나로만 돈다.
// 경계 정밀 로직: rAF 루프 + seek guard + seek 중 영상·오디오 가림.
import React, { useCallback, useEffect, useRef, useState } from "react";

export type SecRange = [number, number];
export interface MiniPlayTarget {
  videoUrl: string;
  spans: SecRange[];      // sec 단위 재생 구간(제외 구간 반영 다중 span 허용)
  fragmentId?: string;
  label?: string;
}

const STOP_EPS = 0.006;   // LedgerPage PLAYBACK_STOP_EPS_MS(6) → sec
const LEAD_FALLBACK = 0.06;
const AUDIO_PACKET_SEC = 1024 / 48000; // AAC-LC packet at the source audio sample rate

// [STORY-TRACK-C C-2] 위치 지속 — 기존 ccut_center_width와 동일 localStorage 방식.
const POS_KEY = "ccut_mini_player_pos";
function loadPos(): { left: number; top: number } | null {
  try {
    const raw = localStorage.getItem(POS_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    if (typeof p?.left === "number" && typeof p?.top === "number") return p;
  } catch { /* 손상값 무시 → 기본 위치 */ }
  return null;
}

interface Props {
  target: MiniPlayTarget | null;
  onClose: () => void;
}

const FragmentMiniPlayer: React.FC<Props> = ({ target, onClose }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  // [C-1/C-2] pos=null이면 기본(우하단 bottom/right), 드래그하면 left/top으로 전환·저장.
  const [pos, setPos] = useState<{ left: number; top: number } | null>(loadPos);
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);
  const spansRef = useRef<SecRange[]>([]);
  const rafRef = useRef<number | null>(null);
  const videoFrameRef = useRef<number | null>(null);
  const lastMediaTimeRef = useRef<number | null>(null);
  const frameDurationRef = useRef(1 / 30);
  const resumeRef = useRef(false);
  const seekMutedRef = useRef<boolean | null>(null);
  const unmuteTimerRef = useRef<number | null>(null);
  // [#9 커스텀 컨트롤 2026-07-19] 네이티브 <video controls> 폐기 — 브라우저 컨트롤바는
  // 진행바와 최대화(전체화면) 아이콘이 좁은 창에서 겹치고 CSS로 위치를 못 옮긴다. 재생 상태·
  // 시각을 직접 들고 커스텀 바(플레이버튼 + 진행바)를 하단에 여백 두고 배치한다.
  const [isPlaying, setIsPlaying] = useState(false);
  const [curTime, setCurTime] = useState(0);

  const stopRaf = useCallback(() => {
    if (rafRef.current != null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
    const v = videoRef.current;
    if (v && videoFrameRef.current != null && "cancelVideoFrameCallback" in v) {
      v.cancelVideoFrameCallback(videoFrameRef.current);
    }
    videoFrameRef.current = null;
    lastMediaTimeRef.current = null;
  }, []);

  // seek 중 잔상·중간 프레임 가림 (opacity 0 → seeked 복원, +400ms 백업)
  const hideForSeek = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    v.style.opacity = "0";
    if (seekMutedRef.current === null) seekMutedRef.current = v.muted;
    v.muted = true;
    let restored = false;
    const restore = () => {
      if (restored) return;
      restored = true;
      v.removeEventListener("seeked", restore);
      v.style.opacity = "1";
      if (unmuteTimerRef.current != null) window.clearTimeout(unmuteTimerRef.current);
      unmuteTimerRef.current = window.setTimeout(() => {
        if (seekMutedRef.current !== null) v.muted = seekMutedRef.current;
        seekMutedRef.current = null;
        unmuteTimerRef.current = null;
      }, Math.ceil(AUDIO_PACKET_SEC * 2000));
    };
    v.addEventListener("seeked", restore);
    setTimeout(restore, 400);
  }, []);

  // 경계 판정 단일 본체 (sec). 반환 true = 정지/전환 수행됨.
  const checkBoundary = useCallback((v: HTMLVideoElement): boolean => {
    const spans = spansRef.current;
    if (spans.length === 0) return false;
    const t = v.currentTime;
    const lastEnd = spans[spans.length - 1]?.[1];
    if (lastEnd !== undefined && t >= lastEnd - STOP_EPS) {
      resumeRef.current = false;
      v.pause();
      if (t > lastEnd) v.currentTime = lastEnd;
      return true;
    }
    const idx = spans.findIndex(([s, e]) => t >= s - 0.005 && t < e);
    if (idx < 0) {
      const nx = spans.find(([s]) => s > t - 0.005);
      if (nx) {
        resumeRef.current = true;
        v.pause();
        hideForSeek();
        v.currentTime = nx[0];
      } else {
        v.pause();
      }
      return true;
    }
    const [, e] = spans[idx];
    const boundaryLead = Math.max(
      LEAD_FALLBACK,
      Math.min(0.15, frameDurationRef.current + AUDIO_PACKET_SEC),
    );
    if (idx < spans.length - 1 && t >= e - boundaryLead) {
      resumeRef.current = true;
      v.pause();
      hideForSeek();
      v.currentTime = spans[idx + 1][0];
      return true;
    }
    return false;
  }, [hideForSeek]);

  const rafTick = useCallback(() => {
    const v = videoRef.current;
    if (!v) { rafRef.current = null; return; }
    if (spansRef.current.length === 0) { v.pause(); rafRef.current = null; return; }
    if (v.ended || v.paused || v.seeking) { rafRef.current = null; return; }
    if (checkBoundary(v)) { rafRef.current = null; }
    else { rafRef.current = requestAnimationFrame(rafTick); }
  }, [checkBoundary]);

  const startRaf = useCallback(() => {
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(rafTick);
    const v = videoRef.current;
    if (v && videoFrameRef.current == null && "requestVideoFrameCallback" in v) {
      const observeFrame: VideoFrameRequestCallback = (_now, metadata) => {
        const previous = lastMediaTimeRef.current;
        if (previous !== null) {
          const delta = metadata.mediaTime - previous;
          if (delta > 0.01 && delta < 0.2) frameDurationRef.current = delta;
        }
        lastMediaTimeRef.current = metadata.mediaTime;
        if (!v.paused && !v.ended) {
          videoFrameRef.current = v.requestVideoFrameCallback(observeFrame);
        } else {
          videoFrameRef.current = null;
        }
      };
      videoFrameRef.current = v.requestVideoFrameCallback(observeFrame);
    }
  }, [rafTick]);

  const onSeeked = useCallback(() => {
    if (!resumeRef.current) return;
    const v = videoRef.current;
    resumeRef.current = false;
    if (!v || spansRef.current.length === 0) { v?.pause(); return; }
    v.play().catch(() => {});
  }, []);

  const onPlay = useCallback(() => {
    const v = videoRef.current;
    const spans = spansRef.current;
    if (!v || spans.length === 0) { v?.pause(); stopRaf(); return; }
    setIsPlaying(true);
    const t = v.currentTime, lastEnd = spans[spans.length - 1][1];
    if (t >= lastEnd - 0.02) { hideForSeek(); v.currentTime = spans[0][0]; }  // 재재생 되감기 가드
    startRaf();
  }, [startRaf, stopRaf, hideForSeek]);

  const onPlaying = useCallback(() => { if (videoRef.current) startRaf(); }, [startRaf]);

  // [#9] 재생 정지 시 rAF 정지 + 버튼 상태 갱신 (기존 onPause={stopRaf} 대체).
  const onPauseHandler = useCallback(() => { stopRaf(); setIsPlaying(false); }, [stopRaf]);

  // timeupdate 백스톱 — 백그라운드 탭(rAF 정지)에서도 경계 검사 (헌장 §5)
  const onTimeUpdate = useCallback(() => {
    const v = videoRef.current;
    if (!v || spansRef.current.length === 0) return;
    setCurTime(v.currentTime);  // [#9] 커스텀 진행바 갱신
    if (v.paused || v.seeking || v.ended) return;
    if (checkBoundary(v)) stopRaf();
  }, [checkBoundary, stopRaf]);

  // [#9] 커스텀 재생/일시정지 토글 — 사용자 버튼. play()/pause()가 onPlay/onPauseHandler를
  // 거쳐 기존 rAF 경계 로직과 그대로 합성된다.
  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play().catch(() => {}); else v.pause();
  }, []);

  // [#9] 진행바 시크 — [firstSpanStart, lastSpanEnd] 연속 근사. seek는 onSeeked(resume)와 합성.
  const seekTo = useCallback((sec: number) => {
    const v = videoRef.current;
    if (!v) return;
    hideForSeek();
    v.currentTime = sec;
    setCurTime(sec);
  }, [hideForSeek]);

  // target 변경 → 로드·시크·자동재생 (loadItem 동형, sec)
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !target || !target.videoUrl || target.spans.length === 0) {
      spansRef.current = [];
      return;
    }
    spansRef.current = target.spans;
    const url = target.videoUrl.startsWith("/")
      ? `/api${target.videoUrl.replace(/^\/api/, "")}` : target.videoUrl;
    v.onloadedmetadata = null;
    if (!v.src.endsWith(url) || v.readyState === 0 || v.error) { v.src = url; v.load(); }
    const start = () => {
      v.currentTime = target.spans[0][0];
      v.play().catch(() => {});
    };
    if (v.readyState >= 1) start(); else v.onloadedmetadata = start;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  useEffect(() => () => { stopRaf(); }, [stopRaf]);

  const handleClose = useCallback(() => {
    resumeRef.current = false;
    stopRaf();
    videoRef.current?.pause();
    setIsPlaying(false);
    spansRef.current = [];
    onClose();
  }, [stopRaf, onClose]);

  // [C-1] 헤더 드래그로 창 이동. 기존 리사이저와 동형(document mousemove/up + 저장).
  const containerRef = useRef<HTMLDivElement>(null);
  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    dragRef.current = { dx: e.clientX - rect.left, dy: e.clientY - rect.top };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      // [#20 잔여] 뷰포트 안으로 clamp — 창 전체가 밖으로 나가지 않게. 크기는 매 이동마다
      // 실측(드래그 시작 후 컨트롤바·비디오 로드로 높이가 바뀌어 시작 시점 값이 어긋나던 것 교정).
      const cw = el.offsetWidth || rect.width, ch = el.offsetHeight || rect.height;
      const left = Math.max(4, Math.min(window.innerWidth - cw - 4, ev.clientX - dragRef.current.dx));
      const top = Math.max(4, Math.min(window.innerHeight - ch - 4, ev.clientY - dragRef.current.dy));
      setPos({ left, top });
    };
    const onUp = () => {
      dragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      // [C-2] 이동 결과 저장 → 껐다 켜도·새로고침해도 마지막 위치.
      setPos((p) => { if (p) { try { localStorage.setItem(POS_KEY, JSON.stringify(p)); } catch { /* quota 무시 */ } } return p; });
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.userSelect = "none";
  }, []);

  const open = !!target && target.spans.length > 0;

  // [#20 잔여 2026-07-19] 등장·복원 위치 viewport 보장 — 저장된 pos가 창 밖(큰 화면에서
  // 저장 뒤 창이 줄면 콘솔 아래로 사라짐)이면 화면 안으로 끌어온다. 드래그 clamp(onMove)와
  // 같은 규약. open될 때 실측 크기로 1회 교정.
  useEffect(() => {
    if (!open || !pos) return;
    const el = containerRef.current;
    const W = el?.offsetWidth || 220, H = el?.offsetHeight || 140;
    const cl = Math.max(4, Math.min(pos.left, window.innerWidth - W - 4));
    const ct = Math.max(4, Math.min(pos.top, window.innerHeight - H - 4));
    if (cl !== pos.left || ct !== pos.top) {
      setPos({ left: cl, top: ct });
      try { localStorage.setItem(POS_KEY, JSON.stringify({ left: cl, top: ct })); } catch { /* quota */ }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // pos 있으면 left/top 절대 위치(드래그됨), 없으면 기본 우하단(bottom/right).
  // 렌더 시점에도 안전하게 viewport 안으로 클램프(효과 반영 전 프레임 대비).
  const posStyle: React.CSSProperties = pos
    ? {
        left: Math.max(4, Math.min(pos.left, (typeof window !== "undefined" ? window.innerWidth : 1280) - 60)),
        top: Math.max(4, Math.min(pos.top, (typeof window !== "undefined" ? window.innerHeight : 720) - 36)),
        right: "auto", bottom: "auto",
      }
    : { right: 20, bottom: 20 };

  return (
    <div
      ref={containerRef}
      className={`fixed z-30 ${pos ? "" : "transition-all duration-300"} ${open ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3 pointer-events-none"}`}
      style={posStyle}
    >
      <div className="relative rounded-xl overflow-hidden bg-black border border-white/10 shadow-2xl">
        {/* [C-1] 드래그 핸들 헤더 — 여기를 잡아 창을 옮긴다. 라벨도 여기 표시. */}
        <div
          onMouseDown={onDragStart}
          className="absolute top-0 left-0 right-0 z-10 h-6 flex items-center px-2 cursor-move bg-gradient-to-b from-black/60 to-transparent"
          title="드래그해서 옮기기"
        >
          <span className="text-[10px] font-semibold text-white/85 select-none pointer-events-none truncate">
            {target?.label || "조각 미리보기"}
          </span>
        </div>
        <video
          ref={videoRef}
          onPlay={onPlay}
          onPlaying={onPlaying}
          onSeeked={onSeeked}
          onTimeUpdate={onTimeUpdate}
          onPause={onPauseHandler}
          onEnded={onPauseHandler}
          onClick={togglePlay}
          className="block cursor-pointer"
          style={{ width: "min(360px, 40vw)", minWidth: 320, height: "auto", minHeight: 180, maxHeight: "48vh", objectFit: "contain" }}
        />
        {/* [#9 커스텀 컨트롤바] 네이티브 컨트롤 대체 — 하단에 여백(pb) 두고 재생버튼·진행바를
            간격(gap) 두고 배치. 최대화 아이콘 없음(겹침 원인 제거). 진행바는 조각 구간
            [firstStart, lastEnd] 연속 근사. */}
        {open && (() => {
          const spans = spansRef.current.length ? spansRef.current : (target?.spans ?? []);
          const first = spans[0]?.[0] ?? 0;
          const last = spans[spans.length - 1]?.[1] ?? 0;
          const dur = Math.max(0.01, last - first);
          const pct = Math.min(100, Math.max(0, ((curTime - first) / dur) * 100));
          return (
            <div className="absolute bottom-0 left-0 right-0 z-10 flex items-center gap-2.5 px-2.5 pb-2 pt-4 bg-gradient-to-t from-black/70 to-transparent">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); togglePlay(); }}
                className="flex-shrink-0 w-6 h-6 rounded-full bg-white/90 hover:bg-white flex items-center justify-center text-black transition-colors"
                title={isPlaying ? "일시정지" : "재생"}
              >
                {isPlaying
                  ? <span className="flex gap-[2px]"><span className="w-[2px] h-2.5 bg-black rounded-sm" /><span className="w-[2px] h-2.5 bg-black rounded-sm" /></span>
                  : <span className="w-0 h-0 border-y-[5px] border-y-transparent border-l-[8px] border-l-black ml-[1px]" />}
              </button>
              <input
                type="range"
                min={first}
                max={last}
                step={0.01}
                value={Math.min(last, Math.max(first, curTime))}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => { e.stopPropagation(); seekTo(Number(e.target.value)); }}
                className="mini-seekbar flex-1 h-1 appearance-none cursor-pointer rounded-full"
                style={{ background: `linear-gradient(to right, #fff 0%, #fff ${pct}%, rgba(255,255,255,0.25) ${pct}%, rgba(255,255,255,0.25) 100%)` }}
              />
            </div>
          );
        })()}
      </div>
      <button
        type="button"
        onClick={handleClose}
        className="absolute -top-2.5 -right-2.5 w-6 h-6 rounded-full text-[11px] leading-none shadow-md hover:scale-110 transition-transform"
        style={{ background: "hsl(230,10%,25%)", color: "hsl(40,20%,85%)" }}
        title="닫기"
      >✕</button>
    </div>
  );
};

export default FragmentMiniPlayer;
