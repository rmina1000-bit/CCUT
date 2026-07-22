type MirrorEventKind = "qwen_complete" | "undo" | "accept" | "edit_again" | "continue";
type MirrorPendingStatus = "open" | "closed";
type MirrorVerdict = "pass" | "correction";
type MirrorVerdictBasis = MirrorEventKind | "elapsed_time_threshold";

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
  pending_id?: string;
  pending_status?: MirrorPendingStatus;
  verdict?: MirrorVerdict;
  verdict_for_pending_id?: string;
  verdict_basis_event_kind?: MirrorVerdictBasis;
  verdict_elapsed_ms?: number;
  closed_at?: string;
  closed_by_event_kind?: MirrorVerdictBasis;
};

type MirrorEventRecord = Omit<MirrorEventInput, "ts"> & {
  ts: number;
  at: string;
  elapsed_ms_since_qwen_complete?: number;
};

export const MIRROR_EVENT_STORAGE_KEY = "ccut.mirror.phase0.events";

const MAX_EVENTS = 500;
const MIRROR_LONG_ELAPSED_MS = 10 * 60 * 1000;

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

function pendingIdFor(event: MirrorEventRecord) {
  return event.pending_id || `mirror_pending:${event.project_id || "unknown"}:${event.ts}`;
}

function proposalMatches(pending: MirrorEventRecord, event: MirrorEventRecord) {
  if (!event.proposal_id) return true;
  const pendingProposalIds = Object.values(pending.proposal_ids || {}).filter(Boolean);
  if (!pendingProposalIds.length) return true;
  return pendingProposalIds.includes(event.proposal_id);
}

function isClosed(events: MirrorEventRecord[], index: number, pendingId: string) {
  const event = events[index];
  if (event.pending_status === "closed" || event.verdict) return true;
  for (let i = index + 1; i < events.length; i += 1) {
    if (events[i].verdict_for_pending_id === pendingId) return true;
  }
  return false;
}

function latestOpenPending(events: MirrorEventRecord[], event: MirrorEventRecord) {
  if (!event.project_id || event.event_kind === "qwen_complete") return null;
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const pending = events[i];
    if (
      pending.event_kind === "qwen_complete" &&
      pending.project_id === event.project_id &&
      typeof pending.ts === "number" &&
      pending.ts <= event.ts
    ) {
      const pendingId = pendingIdFor(pending);
      if (!isClosed(events, i, pendingId) && proposalMatches(pending, event)) {
        return { index: i, event: pending, pendingId };
      }
    }
  }
  return null;
}

function verdictFor(event: MirrorEventRecord, pending: MirrorEventRecord) {
  const elapsed = Math.max(0, event.ts - pending.ts);
  if (event.event_kind === "undo" || event.event_kind === "edit_again") {
    return {
      verdict: "correction" as const,
      basis: event.event_kind,
      elapsed,
    };
  }
  if (elapsed >= MIRROR_LONG_ELAPSED_MS) {
    return {
      verdict: "correction" as const,
      basis: "elapsed_time_threshold" as const,
      elapsed,
    };
  }
  if (event.event_kind === "accept" || event.event_kind === "continue") {
    return {
      verdict: "pass" as const,
      basis: event.event_kind,
      elapsed,
    };
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

  if (base.event_kind === "qwen_complete") {
    base.pending_id = pendingIdFor(base);
    base.pending_status = "open";
  }

  if (
    base.event_kind !== "qwen_complete" &&
    base.project_id &&
    base.elapsed_ms_since_qwen_complete === undefined
  ) {
    const lastComplete = latestComplete(prior, base.project_id, ts);
    if (lastComplete) base.elapsed_ms_since_qwen_complete = Math.max(0, ts - lastComplete.ts);
  }

  const pending = latestOpenPending(prior, base);
  const verdict = pending ? verdictFor(base, pending.event) : null;
  if (verdict) {
    base.pending_status = "closed";
    base.verdict = verdict.verdict;
    base.verdict_for_pending_id = pending.pendingId;
    base.verdict_basis_event_kind = verdict.basis;
    base.verdict_elapsed_ms = verdict.elapsed;
  } else if (base.event_kind === "continue") {
    return compactRecord(base);
  }

  const event = compactRecord(base);
  console.log("[MIRROR_EVENT] " + JSON.stringify(event));

  if (!canUseLocalStorage()) return event;
  try {
    const updated = pending && verdict
      ? prior.map((item, index) => index === pending.index
        ? compactRecord({
          ...item,
          pending_id: pending.pendingId,
          pending_status: "closed",
          verdict: verdict.verdict,
          verdict_basis_event_kind: verdict.basis,
          verdict_elapsed_ms: verdict.elapsed,
          closed_at: base.at,
          closed_by_event_kind: verdict.basis,
        })
        : item)
      : prior;
    const next = [...updated, event].slice(-MAX_EVENTS);
    window.localStorage.setItem(MIRROR_EVENT_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Observability must not change the product flow.
  }
  return event;
}
