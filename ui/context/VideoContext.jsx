import React, {
  createContext, useContext, useRef, useCallback, useState,
} from 'react';

const HOVER_DELAY_MS  = 60;   // intentional hover gate
const LEAVE_DELAY_MS  = 80;   // graceful exit — jitter guard
const FRAME_INTERVAL  = 83;   // ~12 fps
const SEEK_THRESHOLD  = 0.15; // seconds — skip micro-seeks

const VideoContext = createContext(null);

/** Direct DOM manipulation — zero React re-renders during hover transitions */
function applyVisualState(activeId) {
  document.querySelectorAll('[data-frag-id]').forEach((el) => {
    if (!activeId) {
      el.style.filter  = '';
      el.style.outline = '';
      return;
    }
    const isActive = el.dataset.fragId === activeId;
    el.style.filter  = isActive ? '' : 'grayscale(60%) brightness(0.7)';
    el.style.outline = isActive ? '2px solid #38bdf8' : '';
  });
}

export function VideoProvider({ children }) {
  const videoRef        = useRef(null);
  const activeIdRef     = useRef(null);
  const hoverTimerRef   = useRef(null);
  const leaveTimerRef   = useRef(null);
  const lastFrameRef    = useRef(0);
  const activeSrcRef    = useRef('');
  const hoverEnabledRef = useRef(true);

  const [visible, setVisible] = useState(false);
  const [pos,     setPos]     = useState({ top: 0, left: 0 });
  const [videoURL, setVideoURL] = useState(null);

  /**
   * hoverPlay(fragmentId, src, startTime, anchorRect)
   * — 60 ms intentional delay
   * — mouse-sweep protection: replaces any pending hover
   * — same-fragment re-hover: no-op (after clearing leave timer)
   */
  const setHoverEnabled = useCallback((enabled) => {
    hoverEnabledRef.current = !!enabled;
    if (!enabled) {
      clearTimeout(hoverTimerRef.current);
      clearTimeout(leaveTimerRef.current);
    }
  }, []);

  const hoverPlay = useCallback((fragmentId, src, startTime, anchorRect) => {
    if (!hoverEnabledRef.current) return;
    // sweep protection: cancel previous pending hover
    clearTimeout(hoverTimerRef.current);
    // cancel any in-progress leave grace period
    clearTimeout(leaveTimerRef.current);

    // same-fragment re-hover guard (after grace timers are cleared)
    if (activeIdRef.current === fragmentId) return;

    hoverTimerRef.current = setTimeout(() => {
      const video = videoRef.current;
      if (!video) return;

      activeIdRef.current = fragmentId;
      applyVisualState(fragmentId);

      // source update only when changed
      if (src && activeSrcRef.current !== src) {
        video.src = src;
        activeSrcRef.current = src;
      }

      // currentTime jump stabilisation — skip micro-seeks
      if (Math.abs(video.currentTime - startTime) > SEEK_THRESHOLD) {
        video.currentTime = startTime;
      }

      // position floating overlay near anchor
      if (anchorRect) {
        setPos({
          top:  Math.max(8, anchorRect.top - 148),
          left: Math.max(8, Math.min(
            anchorRect.left + anchorRect.width / 2 - 120,
            window.innerWidth - 252,
          )),
        });
      }
      setVisible(true);

      // 12 fps throttle — GPU guard
      const now = performance.now();
      if (now - lastFrameRef.current > FRAME_INTERVAL) {
        lastFrameRef.current = now;
        video.play().catch(() => {});
      }
    }, HOVER_DELAY_MS);
  }, []);

  /**
   * hoverStop(fragmentId)
   * — 80 ms graceful exit
   * — a subsequent hoverPlay() will cancel the leave timer
   */
  const hoverStop = useCallback((_fragmentId) => {
    // cancel pending hover (cursor left before 60 ms fired)
    clearTimeout(hoverTimerRef.current);

    leaveTimerRef.current = setTimeout(() => {
      const video = videoRef.current;
      if (!video) return;
      video.pause();
      activeIdRef.current = null;
      applyVisualState(null);
      setVisible(false);
    }, LEAVE_DELAY_MS);
  }, []);

  return (
    <VideoContext.Provider value={{ videoRef, hoverPlay, hoverStop, setHoverEnabled, videoURL, setVideoURL }}>
      {children}
      <video
        ref={videoRef}
        src={videoURL}
        width={240}
        height={135}
        muted
        preload="metadata"
        playsInline
        style={{
          position:     'fixed',
          top:          pos.top,
          left:         pos.left,
          zIndex:       1000,
          border:       '1px solid #38bdf8',
          borderRadius: 4,
          background:   '#000',
          display:      visible ? 'block' : 'none',
          pointerEvents: 'none',
          boxShadow:    '0 4px 24px rgba(0,0,0,0.75)',
        }}
      />
    </VideoContext.Provider>
  );
}

export const useVideo = () => useContext(VideoContext);
