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
  // [R8 유령 2호 2026-07-20] 요청 순번 가드 — reload·폴러·프로젝트 전환이 뒤섞여도 '마지막으로
  // 띄운 요청'의 응답만 화면에 반영한다. 늦게 도착한 응답이 최신을 덮어 화면이 흔들리던
  // ('취객 흔들림') 경로를 봉인. 매 fetch 직전 ++, 응답 도착 시 순번이 최신이 아니면 폐기.
  const reqSeqRef = useRef(0);

  useEffect(() => {
    let dead = false;
    storyGateEnabled()
      .then((v) => { if (!dead) setEnabled(v); })
      .finally(() => { if (!dead) setGateReady(true); });
    return () => { dead = true; };
  }, []);

  const reload = useCallback(async () => {
    if (!programId) { reqSeqRef.current++; setStory(null); setStoryReady(true); return null; }
    const myId = ++reqSeqRef.current;
    const s = await fetchStory(programId);
    if (myId !== reqSeqRef.current) return s;   // [R8] 늦은 응답 — 폐기(최신이 이미 반영됨)
    setStoryReady(true);
    if (!s) return s;                            // [R8] 실패·부재 — 최신 원고 유지(null 덮어쓰기 금지)
    setStory(s);
    // [R8] 사용자 행동에 따른 '명시적' 새로고침(편집·승인 직후) — 이 원고를 시청 기준으로 승격,
    // stale 알림 해제. 다음 폴이 사용자 자기 편집을 '새 분석 결과'로 오탐하던 것도 함께 봉인한다.
    viewingHashRef.current = s.sequence_hash;
    setStaleHash(null);
    return s;
  }, [programId]);

  // 프로젝트가 바뀌면 "보고 있는 원고" 기준을 새로 잡는다
  useEffect(() => { viewingHashRef.current = null; setStaleHash(null); }, [programId]);

  useEffect(() => {
    if (!gateReady) return;
    setStoryReady(false);
    if (!enabled || !programId || !active) {
      reqSeqRef.current++;   // [R8] 진행 중 요청 무효화 — 늦은 응답이 이 clear를 덮지 못하게
      setStory(null);
      setStoryReady(true);
      return;
    }
    let dead = false;
    const tick = async () => {
      const myId = ++reqSeqRef.current;
      const s = await fetchStory(programId);
      if (dead || myId !== reqSeqRef.current) return;   // [R8 유령 2호] 늦은 응답 폐기
      setStoryReady(true);
      if (!s) return;                                    // [R8] 실패·부재 — 최신 원고 유지(null 덮어쓰기 금지)
      setStory(s);
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
    // [R8 유령 3호 2026-07-20] 승인 후 원고 새로고침은 '단일 소유자'(nonce 경유)에게 맡긴다 —
    // 여기서 직접 reload하지 않는다. 호출자(CenterPanel)가 성공·실패(409=그새 바뀜) 모두
    // onStoryEditStateChanged를 발화 → Index가 nonce를 올려 중앙 gate를 1회만 갱신한다.
    // (기존: approve 내부 reload + nonce reload = 같은 gate 이중 발사 → stale 겹침의 씨앗.)
    return res;
  }, [programId, story]);

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
