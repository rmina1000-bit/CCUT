type MirrorEventKind = "qwen_complete" | "undo" | "accept" | "edit_again";

export type MirrorEventInput = {
  event_kind: MirrorEventKind;
  project_id?: string;
  ts?: number;
  proposal_id?: string;
  proposal_ids?: Record<string, string | undefined | null>;
  proposal_slot?: string;
  proposal_history_id?: string;
  fragment_id?: string;
  timeline_item_id?: string;
  approval_id?: number;
  sequence_hash?: string;
  mode?: string;
  item_count?: number;
  command_type?: string;
  origin?: string;
  total_ms?: number;
  route_total_ms?: number;
  resolve_ms?: number;
};

type MirrorEventRecord = Omit<MirrorEventInput, "ts"> & {
  ts: number;
  at: string;
  elapsed_ms_since_qwen_complete?: number;
};

export const MIRROR_EVENT_STORAGE_KEY = "ccut.mirror.phase0.events";

const MAX_EVENTS = 500;

function canUseLocalStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function cleanValue(value: unknown): unknown {
  if (value === undefined || value === null || value === "") return undefined;
  if (Array.isArray(value)) {
    const cleaned = value
      .map((item) => cleanValue(item))
      .filter((item) => item !== undefined);
    return cleaned.length ? cleaned : undefined;
  }
  if (typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      const cleaned = cleanValue(inner);
      if (cleaned !== undefined) out[key] = cleaned;
    }
    return Object.keys(out).length ? out : undefined;
  }
  return value;
}

function compactRecord<T extends Record<string, unknown>>(record: T): T {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(record)) {
    const cleaned = cleanValue(value);
    if (cleaned !== undefined) out[key] = cleaned;
  }
  return out as T;
}

function readStoredEvents(): MirrorEventRecord[] {
  if (!canUseLocalStorage()) return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(MIRROR_EVENT_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function latestComplete(events: MirrorEventRecord[], projectId: string, ts: number) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (
      event.event_kind === "qwen_complete" &&
      event.project_id === projectId &&
      typeof event.ts === "number" &&
      event.ts <= ts
    ) {
      return event;
    }
  }
  return null;
}

export function recordMirrorEvent(input: MirrorEventInput) {
  const ts = typeof input.ts === "number" ? input.ts : Date.now();
  const prior = readStoredEvents();
  const base = compactRecord({
    ...input,
    ts,
    at: new Date(ts).toISOString(),
  }) as MirrorEventRecord;

  if (
    base.event_kind !== "qwen_complete" &&
    base.project_id &&
    base.elapsed_ms_since_qwen_complete === undefined
  ) {
    const lastComplete = latestComplete(prior, base.project_id, ts);
    if (lastComplete) base.elapsed_ms_since_qwen_complete = Math.max(0, ts - lastComplete.ts);
  }

  const event = compactRecord(base);
  console.log("[MIRROR_EVENT] " + JSON.stringify(event));

  if (!canUseLocalStorage()) return event;
  try {
    const next = [...prior, event].slice(-MAX_EVENTS);
    window.localStorage.setItem(MIRROR_EVENT_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Observability must not change the product flow.
  }
  return event;
}
