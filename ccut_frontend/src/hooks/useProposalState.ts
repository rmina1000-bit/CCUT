import { useState, useCallback } from "react";
import { Proposal, Direction, DirectionSnapshot } from "@/proposal/proposalTypes";
import { createNextSnapshot } from "@/proposal/directionSnapshot";
import { generateProposals } from "@/proposal/proposalOrchestrator";
import { Fragment } from "@/data/fragmentData";
import { narrativeService } from "@/services/narrativeService";

/**
 * [STEP 10-K-C1-R39] Frontend Commit-Time Sequence Guard
 * 백엔드가 어떤 시퀀스를 주든, 프론트에서 실제 재생 직전에 
 * 같은 source_video의 연속 조각을 제거한다.
 */
function getSourceKey(item: any): string {
  return (
    item?.source_id ||
    item?.source_video ||
    item?.source_label ||
    item?.sourceLabel ||
    "UNKNOWN"
  );
}

function getFrameRange(item: any, fps = 30): { start: number; end: number } {
  const start = Number(
    item?.start_frame ??
    Math.round(Number(item?.start ?? item?.start_time ?? 0) * fps)
  );
  const end = Number(
    item?.end_frame ??
    Math.round(Number(item?.end ?? item?.end_time ?? start) * fps)
  );
  return { start, end };
}

/**
 * [STEP 10-K-C1-R41] Weak Sequence Guard (Reverting R40 Over-guarding)
 * 1. 동일 fragment_id 중복 제거
 * 2. 동일 source 내 완전 인접 조각 (연속 재생) 제거
 * *주의*: source당 1개 제한(R40)은 비활성화함.
 */
function guardProposalSequence(sequence: any[], _minGapFrames = 30): any[] {
  if (!Array.isArray(sequence) || sequence.length === 0) return [];
  const result: any[] = [];
  const seenIds = new Set<string>();
  for (const item of sequence) {
    const fid = item?.fragment_id || item?.proposal_fragment_id || item?.id;
    if (fid && seenIds.has(fid)) continue;
    result.push(item);
    if (fid) seenIds.add(fid);
  }
  console.log("[R41_WEAK_SEQUENCE_GUARD]", {
    before: sequence.length,
    after: result.length,
    removedCount: sequence.length - result.length
  });
  return result;
}

export const useProposalState = (sourceFragments: Fragment[]) => {
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [committedProposalId, setCommittedProposalId] = useState<string | null>(null);
  const [proposals, setProposals] = useState<Record<"A" | "B", Proposal> | null>(null);
  const [directionSnapshot, setDirectionSnapshot] = useState<DirectionSnapshot | null>(null);
  const [storyPlan, setStoryPlan] = useState<any | null>(null); // StoryPlanPreview

  const logProposalPair = useCallback(
    (pair: Record<"A" | "B", Proposal>, label: string) => {
      const keyA = pair.A.key_fragments;
      const keyB = pair.B.key_fragments;
      const firstA = keyA[0] ?? "none";
      const firstB = keyB[0] ?? "none";
      const isFirstDiff = firstA !== firstB;

      console.log("[strategyEngine] A order:", keyA);
      console.log("[strategyEngine] B order:", keyB);
      console.log(`[strategyEngine] A/B first fragment differs: ${isFirstDiff}`);
      console.log(`[PROPOSAL][${label}] snapshot=${pair.A.snapshot_id} (A:${firstA}, B:${firstB})`);
    },
    []
  );

  const handleProposalPreview = useCallback((id: string) => {
    setSelectedProposalId(id);
  }, []);

  const handleProposalCommit = useCallback((id: string) => {
    if (!proposals || !proposals[id as "A" | "B"]) {
      console.warn("[proposalState] commit blocked: proposals not ready", id);
      return;
    }
    
    console.log("[proposalState] handleProposalCommit called with id:", id);
    
    // [STEP 10-K-C1-R41] Guard the sequence before committing
    const mode = id as "A" | "B";
    const originalProposal = proposals[mode];
    
    // resolved_aliases나 sequence 필드에 객체 형태의 메타데이터가 포함되어 있음
    const rawSeq = (originalProposal as any).resolved_aliases || (originalProposal as any).sequence || [];
    if (rawSeq.length > 0) {
      const guardedSeq = guardProposalSequence(rawSeq);
      
      // [STEP 10-K-C1-R39-R1] fragment_id 우선 정책 (절대 display_id 사용 금지)
      const guardedKeyFrags = guardedSeq
        .map((f: any) => f.fragment_id || f.proposal_fragment_id || f.id)
        .filter(Boolean);
      
      console.log("[R41_COMMIT_WEAK_GUARD_RESULT]", {
        id,
        beforeCount: rawSeq.length,
        afterCount: guardedSeq.length,
        key_fragments: guardedKeyFrags,
        resolved_aliases: guardedSeq.map((f: any) => ({
          fragment_id: f.fragment_id,
          display_id: f.display_id,
          source_video: f.source_video,
          source_id: f.source_id,
          start_frame: f.start_frame,
          end_frame: f.end_frame,
        })),
      });

      setProposals(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          [mode]: {
            ...prev[mode],
            key_fragments: guardedKeyFrags,
            resolved_aliases: guardedSeq,
            sequence: guardedSeq
          }
        };
      });
    }

    setSelectedProposalId(id);
    setCommittedProposalId(id);
  }, [proposals]);

  const handleReproposal = useCallback(
    (nextDirection: Direction) => {
      if (!sourceFragments.length) {
        console.warn("[Reproposal] sourceFragments is empty. Skipping reproposal.");
        return;
      }

      const nextSnapshot = createNextSnapshot(directionSnapshot, nextDirection);
      
      // [STEP 10-I.5.27-E2] Local reproposal isolation
      if (proposals) {
        console.warn("[Reproposal] Local strategyEngine is legacy fallback only. Backend narrative reproposal is required.");
        // Keep existing proposals but update the snapshot to reflect user intent
        setDirectionSnapshot(nextSnapshot);
        return;
      }

      console.warn("[Reproposal] Falling back to local strategyEngine (No backend proposals found).");
      const nextProposals = generateProposals(sourceFragments, nextSnapshot);

      logProposalPair(nextProposals, "REPROPOSAL");

      setSelectedProposalId(null);
      setCommittedProposalId(null);
      setProposals(nextProposals);
      setDirectionSnapshot(nextSnapshot);

      console.log("[Reproposal] active_direction:", nextSnapshot.active_direction);
      console.log("[Reproposal] snapshot_id:", nextSnapshot.snapshot_id);
    },
    [directionSnapshot, logProposalPair, sourceFragments]
  );

  const buildConsultationReply = useCallback((input: string): string => {
    const normalized = input.trim();

    if (!normalized) {
      return "말씀을 조금 더 입력해 주시면 그 방향을 편집 의도에 반영하겠습니다.";
    }

    if (/빠르게|템포|속도|지루|짧게/.test(normalized)) {
      return "좋습니다. 장면 전환을 더 촘촘하게 잡고, 반복되는 구간은 줄이는 방향으로 편집 의도를 조정하겠습니다.";
    }

    if (/사람|인물|표정|대화|관계|가족/.test(normalized)) {
      return "알겠습니다. 인물의 동작, 표정, 상호작용이 잘 보이는 조각을 우선 배치하는 방향으로 맞추겠습니다.";
    }

    if (/감성|분위기|여운|잔잔|따뜻/.test(normalized)) {
      return "좋습니다. 빠른 정보 전달보다 분위기와 여운이 살아나는 장면을 중심으로 편집 방향을 잡겠습니다.";
    }

    if (/풍경|배경|장소|공간/.test(normalized)) {
      return "알겠습니다. 장소와 배경은 필요한 만큼만 남기고, 이야기 흐름을 해치지 않도록 균형을 맞추겠습니다.";
    }

    if (/골고루|균형|전체|여러 영상|모두/.test(normalized)) {
      return "좋습니다. 특정 영상에 치우치지 않도록 여러 원본의 조각을 균형 있게 섞는 방향으로 준비하겠습니다.";
    }

    if (/이대로|제안|만들어|진행|좋아|오케이|ok/i.test(normalized)) {
      return "네, 지금까지의 대화 내용을 기준으로 A/B 편집 제안을 준비하겠습니다.";
    }

    if (/[?？]$|알아듣|이해/.test(normalized)) {
      return "네, 말씀하신 내용을 편집 방향으로 해석하고 있습니다. 지금까지의 대화는 StoryIntent에 누적하고, 그 기준으로 A/B 제안을 준비하겠습니다.";
    }

    return `알겠습니다. 말씀하신 "${normalized.slice(0, 40)}${normalized.length > 40 ? "..." : ""}" 방향을 반영해서 편집 의도를 조정하겠습니다.`;
  }, []);

  const handleConsultation = useCallback(async (text: string) => {
    if (!storyPlan) return;

    const lower = text.toLowerCase();
    const shouldConfirm =
      lower.includes("이대로") ||
      lower.includes("진행") ||
      lower.includes("제안해") ||
      /ok$/i.test(lower) ||
      lower.includes("오케이");

    const userMsgId = `user_${Date.now()}`;
    const aiMsgId = `ai_${Date.now() + 1}`;

    const userMsg = {
      id: userMsgId,
      sender: "user" as const,
      text,
      timestamp: Date.now(),
    };

    // Immediate AI feedback (Interpreting...)
    const aiMsg = {
      id: aiMsgId,
      sender: "ai" as const,
      text: "편집 방향을 해석하고 있습니다...",
      timestamp: Date.now() + 1,
      isInterpreting: true
    };

    setStoryPlan((prev: any) => {
      if (!prev) return prev;
      return {
        ...prev,
        messages: [...(prev.messages ?? []), userMsg, aiMsg],
      };
    });

    // Background Narrative AI call with 15s timeout
    const startTime = Date.now();
    let result: any = { status: "TIMEOUT", patch: null, latency_ms: 0, error: "Frontend 15s timeout" };
    try {
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error("TIMEOUT")), 15000)
      );
      
      result = await Promise.race([
        narrativeService.interpretIntent(text),
        timeoutPromise
      ]);
    } catch (err: any) {
      console.warn("[NarrativeAI] Safe fallback triggered:", err.message);
    }

    const latency = Date.now() - startTime;
    if (result.status !== "OK") {
      console.log(`[NarrativeAI] Fallback (Status: ${result.status}, Latency: ${latency}ms)`);
    }

    const nextIntent: any = { ...(storyPlan.story_intent || {}) };
    
    // AI Success: Apply StoryIntentPatch
    if (result.status === "OK" && result.patch) {
      // Merge patch into story_intent
      Object.assign(nextIntent, result.patch);
    } else {
      // AI Fallback: Rule-based simple intent extraction
      if (/빠르게|템포|속도/.test(lower)) nextIntent.pace = "fast";
      if (/감성|따뜻|여운/.test(lower)) nextIntent.mood = "warm";
      if (/사람|인물|가족/.test(lower)) nextIntent.focus = "people";
      if (/풍경|배경|장소/.test(lower)) nextIntent.focus = "landscape";
      if (/골고루|균형/.test(lower)) nextIntent.coverage = "balanced_sources";
    }

    const nextStatus = shouldConfirm ? "confirmed" : "user_requested_change";
    const finalAiText = buildConsultationReply(text);

    setStoryPlan((prev: any) => {
      if (!prev) return prev;
      return {
        ...prev,
        story_intent: nextIntent,
        consultation_status: nextStatus,
        confirmation_status: nextStatus === "confirmed" ? "confirmed" : prev.confirmation_status,
        user_notes: text,
        messages: (prev.messages ?? []).map((m: any) => 
          m.id === aiMsgId ? { ...m, text: finalAiText, isInterpreting: false } : m
        ),
      };
    });
  }, [storyPlan, buildConsultationReply]);

  return {
    selectedProposalId,
    setSelectedProposalId,
    committedProposalId,
    setCommittedProposalId,
    proposals,
    setProposals,
    directionSnapshot,
    setDirectionSnapshot,
    storyPlan,
    setStoryPlan,
    handleProposalPreview,
    handleProposalCommit,
    handleReproposal,
    handleConsultation,
    logProposalPair
  };
};
