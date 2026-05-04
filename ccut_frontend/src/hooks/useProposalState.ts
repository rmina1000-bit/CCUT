import { useState, useCallback } from "react";
import { Proposal, Direction, DirectionSnapshot } from "@/proposal/proposalTypes";
import { createNextSnapshot } from "@/proposal/directionSnapshot";
import { generateProposals } from "@/proposal/proposalOrchestrator";
import { Fragment } from "@/data/fragmentData";
import { narrativeService } from "@/services/narrativeService";

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

  const classifyConsultationInput = useCallback((text: string) => {
    const lower = text.toLowerCase().trim();
    if (!lower) return "unknown";

    if (/안녕|반가워|하이|hello|hi/.test(lower)) return "greeting";
    if (/누구|뭐하는|뭐 하는|기능|할 수 있는|정체/.test(lower)) return "system_question";
    if (/이대로|진행|좋아|오케이|ok|맞아|응|네|제안해/.test(lower)) return "confirmation";
    if (/안 돼|안돼|이상해|모르겠|못 알아|대화가 안|답답/.test(lower)) return "complaint_or_confusion";

    // editing_instruction keywords
    if (/빠르게|템포|속도|감성|따뜻|여운|사람|인물|가족|풍경|배경|장소|골고루|균형|줄여|늘려|길게|짧게|촘촘|여백|중심|위주/.test(lower)) {
      return "editing_instruction";
    }

    return "unknown";
  }, []);

  const buildConsultationReply = useCallback((input: string, intent: string): string => {
    const normalized = input.trim();

    if (intent === "greeting") {
      return "안녕하세요. 편집 방향을 말씀해 주시면 그 기준으로 제안을 준비하겠습니다.";
    }
    if (intent === "system_question") {
      return "저는 이 프로젝트의 영상을 분석하고, 편집 방향을 정리해 A/B 제안을 준비하는 CCUT 편집 보조입니다.";
    }
    if (intent === "complaint_or_confusion") {
      return "지금 대화가 자연스럽지 않게 느껴질 수 있습니다. 편집 방향을 짧게 말씀해 주시면 그 기준으로 다시 정리하겠습니다.";
    }
    if (intent === "unknown") {
      return "편집 방향을 조금 더 구체적으로 말씀해 주세요. 예: 더 빠르게, 사람 중심으로, 감성적으로.";
    }
    if (intent === "confirmation") {
      return "네, 지금까지의 대화 내용을 기준으로 A/B 편집 제안을 준비하겠습니다.";
    }

    // Default or editing_instruction
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

    return `알겠습니다. 말씀하신 "${normalized.slice(0, 40)}${normalized.length > 40 ? "..." : ""}" 방향을 반영해서 편집 의도를 조정하겠습니다.`;
  }, []);

  const handleConsultation = useCallback(async (text: string) => {
    if (!storyPlan) return;

    const intent = classifyConsultationInput(text);
    const lower = text.toLowerCase();
    const shouldConfirm = intent === "confirmation";

    const userMsgId = `user_${Date.now()}`;
    const aiMsgId = `ai_${Date.now() + 1}`;

    const userMsg = {
      id: userMsgId,
      sender: "user" as const,
      text,
      timestamp: Date.now(),
    };

    // Immediate AI feedback
    const aiMsg = {
      id: aiMsgId,
      sender: "ai" as const,
      text: intent === "editing_instruction" ? "편집 방향을 해석하고 있습니다..." : "의도를 파악하고 있습니다...",
      timestamp: Date.now() + 1,
      isInterpreting: intent === "editing_instruction"
    };

    setStoryPlan((prev: any) => {
      if (!prev) return prev;
      return {
        ...prev,
        messages: [...(prev.messages ?? []), userMsg, aiMsg],
      };
    });

    let nextIntent: any = { ...(storyPlan.story_intent || {}) };
    let finalAiText = "";
    let finalIntentStr = intent;

    // Background Narrative AI call (LLM-based Classification + Patch)
    const startTime = Date.now();
    let result: any = { status: "TIMEOUT", patch: null, classification: null, latency_ms: 0 };
    
    try {
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error("TIMEOUT")), 15000)
      );
      
      result = await Promise.race([
        narrativeService.interpretIntent(text),
        timeoutPromise
      ]);
    } catch (err: any) {
      console.warn("[NarrativeAI] LLM interpretation failed, falling back to keywords:", err.message);
    }

    const totalLatency = Date.now() - startTime;

    if (result.status === "OK" && result.classification) {
      const clf = result.classification;
      console.log(`[NarrativeAI] LLM Intent: ${clf.input_type} (Needs Patch: ${clf.needs_story_patch}) Latency: ${totalLatency}ms`);
      
      finalAiText = clf.short_reply;
      finalIntentStr = clf.input_type;

      if (clf.needs_story_patch && result.patch) {
        Object.assign(nextIntent, result.patch);
      }
    } else {
      // AI Fallback: Rule-based keyword classification
      console.log(`[NarrativeAI] Fallback to keywords (Status: ${result.status}, Latency: ${totalLatency}ms)`);
      finalAiText = buildConsultationReply(text, intent);
      
      if (intent === "editing_instruction") {
        const lower = text.toLowerCase();
        if (/빠르게|템포|속도/.test(lower)) nextIntent.pace = "fast";
        if (/감성|따뜻|여운/.test(lower)) nextIntent.mood = "warm";
        if (/사람|인물|가족/.test(lower)) nextIntent.focus = "people";
        if (/풍경|배경|장소/.test(lower)) nextIntent.focus = "landscape";
        if (/골고루|균형/.test(lower)) nextIntent.coverage = "balanced_sources";
      }
    }

    const nextStatus = finalIntentStr === "confirmation" || finalIntentStr === "proposal_request" ? "confirmed" : "user_requested_change";

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
  }, [storyPlan, buildConsultationReply, classifyConsultationInput]);

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
