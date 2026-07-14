/**
 * [STORY-GATE P3] 프론트가 승인 관문을 구독한다.
 *
 * 계약: docs/STORY_GATE_CONTRACT_V1.md
 *  - 게이트 OFF면 enabled=false → 화면은 현행과 바이트 동일 (I-4). 이 훅은 아무것도 안 바꾼다.
 *  - 게이트 ON이면 story_state로 편집 UI 노출을 가른다 (승인 전엔 숨김).
 *
 * 진실원은 백엔드다. 프론트가 상태를 지어내지 않는다 — GET /story/{program_id}만 믿는다.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type StoryState = "scanned" | "story_draft" | "story_review" | "story_approved";

export interface StoryInfo {
  story_state: StoryState;
  sequence_hash: string;
  mode: string | null;
  item_count: number;
  approved: { approval_id: number; sequence_hash: string; approved_at: string;
              actor: string; stale: boolean } | null;
}

// 게이트 값은 서버 기동 중 안 바뀐다 → 세션당 1회만 묻는다.
let gatePromise: Promise<boolean> | null = null;
export const storyGateEnabled = (): Promise<boolean> => {
  if (!gatePromise) {
    gatePromise = fetch("/api/story/gate")
      .then((r) => (r.ok ? r.json() : { enabled: false }))
      .then((d) => !!d?.enabled)
      .catch(() => false);
  }
  return gatePromise;
};

export const fetchStory = (programId: string): Promise<StoryInfo | null> =>
  fetch(`/api/story/${encodeURIComponent(programId)}`)
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => (d && d.ok ? (d as StoryInfo) : null))
    .catch(() => null);

export const approveStory = (programId: string, sequenceHash: string) =>
  fetch(`/api/story/${encodeURIComponent(programId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sequence_hash: sequenceHash, actor: "user" }),
  }).then(async (r) => ({ ok: r.ok, status: r.status, body: await r.json().catch(() => ({})) }));

/**
 * @param programId 현재 열려 있는 프로젝트
 * @param active    이 화면이 원고를 볼 수 있는 상태인지(분석 완료 등). false면 폴링 안 함.
 */
export function useStoryGate(programId?: string | null, active = true) {
  const [enabled, setEnabled] = useState(false);
  const [gateReady, setGateReady] = useState(false);
  const [story, setStory] = useState<StoryInfo | null>(null);
  const [storyReady, setStoryReady] = useState(false);
  // 사용자가 지금 보고 있는 원고의 지문 — 서버 해시가 이것과 달라지면 "새 결과 있음"
  const viewingHashRef = useRef<string | null>(null);
  const [staleHash, setStaleHash] = useState<string | null>(null);

  useEffect(() => {
    let dead = false;
    storyGateEnabled()
      .then((v) => { if (!dead) setEnabled(v); })
      .finally(() => { if (!dead) setGateReady(true); });
    return () => { dead = true; };
  }, []);

  const reload = useCallback(async () => {
    if (!programId) { setStory(null); setStoryReady(true); return null; }
    const s = await fetchStory(programId);
    setStory(s);
    setStoryReady(true);
    return s;
  }, [programId]);

  // 프로젝트가 바뀌면 "보고 있는 원고" 기준을 새로 잡는다
  useEffect(() => { viewingHashRef.current = null; setStaleHash(null); }, [programId]);

  useEffect(() => {
    if (!gateReady) return;
    setStoryReady(false);
    if (!enabled || !programId || !active) {
      setStory(null);
      setStoryReady(true);
      return;
    }
    let dead = false;
    const tick = async () => {
      const s = await fetchStory(programId);
      if (dead) return;
      setStory(s);
      setStoryReady(true);
      if (!s) return;
      // [STORY-GATE P3 / S5] 원고를 자동으로 갈아치우지 않는다.
      // 2차 집중분석이 끝나 서버 원고가 바뀌어도 화면은 그대로 두고, 알림만 띄운다.
      if (viewingHashRef.current === null) viewingHashRef.current = s.sequence_hash;
      else if (s.sequence_hash !== viewingHashRef.current) setStaleHash(s.sequence_hash);
    };
    tick();
    const id = window.setInterval(tick, 10000);
    return () => { dead = true; window.clearInterval(id); };
  }, [gateReady, enabled, programId, active]);

  // 사용자가 "반영하기"를 눌렀을 때만 보고 있는 원고를 최신으로 승격
  const adoptLatest = useCallback(() => {
    if (staleHash) { viewingHashRef.current = staleHash; setStaleHash(null); }
  }, [staleHash]);

  const approve = useCallback(async () => {
    if (!programId || !story) return { ok: false, status: 0, body: {} };
    const res = await approveStory(programId, story.sequence_hash);
    await reload();
    return res;
  }, [programId, story, reload]);

  return {
    ready: gateReady && storyReady,
    loading: active && (!gateReady || (enabled && !storyReady)),
    enabled,
    story,
    /** 승인 전인가 = 편집 UI를 숨겨야 하는가 (게이트 ON일 때만 의미) */
    awaitingApproval: enabled && !!story && story.story_state !== "story_approved",
    approved: !!story && story.story_state === "story_approved",
    /** 2차 분석 등으로 서버 원고가 바뀜 — 자동 교체 금지, 알림만 (S5) */
    hasNewerStory: !!staleHash,
    adoptLatest,
    approve,
    reload,
  };
}
