import { useState, useCallback } from "react";
import { Proposal, Direction, DirectionSnapshot } from "@/proposal/proposalTypes";
import { createNextSnapshot } from "@/proposal/directionSnapshot";
import { generateProposals } from "@/proposal/proposalOrchestrator";
import { Fragment } from "@/data/fragmentData";

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

  const handleConsultation = useCallback((text: string) => {
    if (!storyPlan || storyPlan.consultation_status === "confirmed") return;

    const lower = text.toLowerCase();
    const userMsg = { id: `user_${Date.now()}`, sender: "user" as const, text, timestamp: Date.now() };
    let aiResponse = "";
    let nextStatus = storyPlan.consultation_status;

    if (lower.includes("이대로") || lower.includes("좋아") || lower.includes("진행") || lower.includes("제안해")) {
      aiResponse = "좋습니다. 이제 이 기준으로 두 가지 편집안을 만들어볼게요.";
      nextStatus = "confirmed";
    } else {
      if (lower.includes("빠르게") || lower.includes("템포")) aiResponse = "네, 핵심 위주로 템포를 빠르게 가져가며 속도감을 살려보겠습니다.";
      else if (lower.includes("감성") || lower.includes("따뜻")) aiResponse = "분위기 있고 감성적인 장면들을 우선적으로 배치해서 여운을 줄게요.";
      else if (lower.includes("사람") || lower.includes("가족")) aiResponse = "좋습니다. 사람과 표정, 동작이 중심이 되도록 무게를 좀 더 둘게요.";
      else if (lower.includes("풍경") || lower.includes("배경")) aiResponse = "풍경과 배경의 미학을 살려서 시각적으로 시원한 전개를 만들어볼게요.";
      else if (lower.includes("골고루")) aiResponse = "여러 영상을 골고루 활용해서 전체적인 기록이 잘 드러나게 할게요.";
      else aiResponse = "의견 감사합니다. 말씀하신 방향을 잘 반영해서 준비해볼게요.";
      nextStatus = "user_requested_change";
    }

    const aiMsg = { id: `ai_${Date.now() + 1}`, sender: "ai" as const, text: aiResponse, timestamp: Date.now() + 1 };
    const nextIntent: any = { ...storyPlan.story_intent };
    if (lower.includes("빠르게") || lower.includes("템포")) nextIntent.pace = "fast";
    if (lower.includes("감성") || lower.includes("따뜻")) nextIntent.mood = "warm";
    if (lower.includes("사람") || lower.includes("가족")) nextIntent.focus = "people";
    if (lower.includes("풍경") || lower.includes("배경")) nextIntent.focus = "landscape";
    if (lower.includes("골고루")) nextIntent.coverage = "balanced_sources";

    setStoryPlan({
      ...storyPlan,
      story_intent: nextIntent,
      consultation_status: nextStatus,
      confirmation_status: nextStatus === "confirmed" ? "confirmed" : storyPlan.confirmation_status,
      user_notes: text,
      messages: [...(storyPlan.messages || []), userMsg, aiMsg]
    });
  }, [storyPlan]);

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
