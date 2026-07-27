type LongTaskRow = {
  name: string;
  start: number;
  duration: number;
};

export type SpeedTraceRun = {
  traceId: string;
  t0: number;
  t1?: number;
  t6?: number;
  t7?: number;
  t8?: number;
  longtasks: LongTaskRow[];
  observer?: PerformanceObserver;
  mutationObserver?: MutationObserver;
};

declare global {
  interface Window {
    __ccutLastInputEpochMs?: number;
  }
}

function flagOn(value: unknown): boolean {
  return String(value || "").toLowerCase() === "1"
    || String(value || "").toLowerCase() === "true"
    || String(value || "").toLowerCase() === "on";
}

export function speedTraceEnabled(): boolean {
  if (typeof window !== "undefined" && flagOn(window.localStorage.getItem("CCUT_TRACE"))) return true;
  return flagOn((import.meta as any).env?.VITE_CCUT_TRACE);
}

function installInputCapture() {
  if (typeof window === "undefined" || (window as any).__ccutSpeedTraceInputInstalled) return;
  (window as any).__ccutSpeedTraceInputInstalled = true;
  const mark = () => {
    if (speedTraceEnabled()) window.__ccutLastInputEpochMs = Date.now();
  };
  window.addEventListener("click", mark, true);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Enter") mark();
  }, true);
}

installInputCapture();

export function beginSpeedTrace(): SpeedTraceRun | null {
  if (!speedTraceEnabled() || typeof window === "undefined") return null;
  const trace: SpeedTraceRun = {
    traceId: `speed_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    t0: window.__ccutLastInputEpochMs || Date.now(),
    longtasks: [],
  };
  try {
    trace.observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const start = Math.round(performance.timeOrigin + entry.startTime);
        const duration = Math.round(entry.duration);
        if (start >= trace.t0 && (!trace.t7 || start <= trace.t7)) {
          trace.longtasks.push({ name: entry.name, start, duration });
        }
      }
    });
    trace.observer.observe({ type: "longtask", buffered: true as any });
  } catch {
    trace.longtasks = [];
  }
  return trace;
}

export function markFetchIssued(trace: SpeedTraceRun | null): HeadersInit {
  if (!trace) return {};
  trace.t1 = Date.now();
  return { "X-CCUT-Trace-Id": trace.traceId };
}

export function markFirstByte(trace: SpeedTraceRun | null) {
  if (!trace || trace.t6) return;
  trace.t6 = Date.now();
  try {
    trace.mutationObserver = new MutationObserver(() => {
      if (!trace.t7) trace.t7 = Date.now();
      trace.mutationObserver?.disconnect();
    });
    trace.mutationObserver.observe(document.body, { childList: true, subtree: true, characterData: true });
  } catch {
    // Longtask and DOM observers are best-effort trace evidence only.
  }
}

export function markFirstDom(trace: SpeedTraceRun | null) {
  if (!trace || trace.t7) return;
  requestAnimationFrame(() => {
    if (!trace.t7) trace.t7 = Date.now();
  });
}

export function finishSpeedTrace(
  trace: SpeedTraceRun | null,
  apiBaseUrl: string,
  request: Record<string, unknown>,
  response: Record<string, unknown>,
) {
  if (!trace) return;
  trace.t8 = Date.now();
  trace.observer?.disconnect();
  trace.mutationObserver?.disconnect();
  const payload = {
    trace_id: trace.traceId,
    t0: trace.t0,
    t1: trace.t1,
    t6: trace.t6,
    t7: trace.t7,
    t8: trace.t8,
    longtasks: trace.longtasks,
    request,
    response,
  };
  void fetch(`${apiBaseUrl}/trace/speed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => undefined);
}
