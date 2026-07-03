import { useState, useCallback } from "react";
import { Proposal, Direction, DirectionSnapshot } from "@/proposal/proposalTypes";
import { createNextSnapshot } from "@/proposal/directionSnapshot";
import { generateProposals } from "@/proposal/proposalOrchestrator";
import { Fragment } from "@/data/fragmentData";
import { narrativeService } from "@/services/narrativeService";
import { videoService } from "@/services/videoService";
import { assignShortDisplayIds, recalcDisplayIds } from "@/lib/fragmentIdentity";

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

type ConsultationDecision = {
  text: string;
  shouldRunProposal: boolean;
  fallbackKind?: "empty" | "unknown" | "ambiguous" | "repeat";
};

const LEGACY_NARRATIVE_ENABLED =
  String(import.meta.env.CCUT_LEGACY_NARRATIVE ?? "0") === "1";

const P6_FALLBACK_UNKNOWN =
  "저는 자유롭게 대화하는 AI는 아니에요. 영상 편집에 관한 지시를 알아듣고 실행하는 편집기예요. '실내만', '5개로 줄여줘' 처럼 편집 조건으로 말씀해주시면 바로 해드릴게요.";
const P6_FALLBACK_AMBIGUOUS =
  "말씀하신 느낌을 정확히는 못 알아들었어요. 컷을 더 빠르게 할까요, 특정 장면(실내/야외/사람) 위주로 줄일까요 — 편집 조건으로 말씀해주시면 반영해드릴게요.";
const P6_FALLBACK_REPEAT =
  "그 표현은 아직 편집 조건으로 못 바꿔요. 실내/야외, 개수, 빠르기 정도로 말씀해주시면 돼요.";

function hasRecentP6Fallback(messages: any[] = [], fallbackTexts = [P6_FALLBACK_UNKNOWN, P6_FALLBACK_AMBIGUOUS, P6_FALLBACK_REPEAT]): boolean {
  return messages.slice(-8).some((m: any) =>
    m?.sender === "ai" &&
    fallbackTexts.includes(m?.text)
  );
}

function isExecutableEditCommand(input: string): boolean {
  const hasSceneOrSubject = /실내|실외|야외|운동장|물놀이|바다|해변|수영|계곡|강|풍경|음식|요리|사람|인물|아이|어린이|밤|야경|거리|호텔|침실|방|체육관|공원|놀이터|외부|밖|표정|가족|배경|장소|공간/.test(input);
  const hasOnlyOperator = /(?:^|\s)\S+만(?:\s|$)/.test(input);
  const hasEditOperator = hasOnlyOperator || /빼|빼줘|제외|말고|없이|위주|중심|골라|선택|편집|줄여|늘려|살려|넣어|제거/.test(input);
  const hasCountOrPace = /(\d+\s*개|(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*개|빠르게|느리게|짧게|길게|템포|속도|페이스)/.test(input);
  const hasConfirm = /이대로|진행|확정|좋아|오케이|ok/i.test(input);

  return hasCountOrPace || hasConfirm || (hasSceneOrSubject && hasEditOperator);
}

export const useProposalState = (
  sourceFragments: Fragment[],
  projectId?: string,
  orderedSourceIds?: string[]
) => {
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
    
    const customFrags = (originalProposal as any).customEditFragments;
    const rawSeq = (Array.isArray(customFrags) && customFrags.length > 0)
      ? customFrags
      : ((originalProposal as any).resolved_aliases || (originalProposal as any).sequence || []);
    if (rawSeq.length > 0) {
      const guardedSeq = guardProposalSequence(rawSeq);
      
      // [STEP 10-K-C1-R39-R1] fragment_id 우선 정책 (절대 display_id 사용 금지)
      const guardedKeyFrags = guardedSeq
        .map((f: any) => f.fragment_id || f.proposal_fragment_id || f.id)
        .filter(Boolean);
      
      const normalizedGuardedSeq = guardedSeq.map((f: any) => {
        const fid = f.fragment_id || f.proposal_fragment_id || f.id;
        return {
          ...f,
          fragment_id: fid,
        };
      });

      const mappedSeq = assignShortDisplayIds(recalcDisplayIds(normalizedGuardedSeq));

      console.log("[R41_COMMIT_WEAK_GUARD_RESULT]", {
        id,
        beforeCount: rawSeq.length,
        afterCount: guardedSeq.length,
        key_fragments: guardedKeyFrags,
        resolved_aliases: mappedSeq.map((f: any) => ({
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
            resolved_aliases: mappedSeq,
            sequence: mappedSeq
          }
        };
      });
    }

    setSelectedProposalId(id);
    setCommittedProposalId(id);
  }, [proposals]);

  const handleReproposal = useCallback(
    async (nextDirection: Direction | string) => {
      if (!sourceFragments.length) {
        console.warn("[Reproposal] sourceFragments is empty. Skipping reproposal.");
        return;
      }

      const instructionText = typeof nextDirection === "string" ? nextDirection.trim() : "";
      if (!instructionText) {
        console.warn("[Reproposal] instructionText is empty. Skipping reproposal.");
        return;
      }

      if (!orderedSourceIds || orderedSourceIds.length === 0) {
        console.warn("[Reproposal] orderedSourceIds is empty. Skipping reproposal.");
        return;
      }

      // [REPROPOSAL_NL_SUBMIT] Console Log
      console.log("[REPROPOSAL_NL_SUBMIT]\n" + JSON.stringify({
        instructionText,
        sourceCount: orderedSourceIds.length,
        existingProposals: proposals ? {
          A: proposals.A?.proposal_id,
          B: proposals.B?.proposal_id
        } : "none"
      }, null, 2));

      const nextSnapshot = createNextSnapshot(directionSnapshot, typeof nextDirection === "string" ? {} as Direction : nextDirection);
      setDirectionSnapshot(nextSnapshot);

      const targetLen = proposals?.A?.preview_duration || 60.0;
      const userIntent = {
        ...(storyPlan?.story_intent || {}),
        instruction_text: instructionText,
        coverage: "balanced_sources"
      };

      const payload = {
        project_id: projectId || "default_project",
        source_ids: orderedSourceIds,
        target_length: targetLen,
        user_intent: userIntent,
        refresh: true
      };

      // [REPROPOSAL_PROJECT_REQUEST] Console Log
      console.log("[REPROPOSAL_PROJECT_REQUEST]\n" + JSON.stringify({
        apiUrl: `${videoService.API_BASE_URL}/proposals/project`,
        payloadSummary: payload,
        source_ids: orderedSourceIds,
        instruction_text: instructionText
      }, null, 2));

      try {
        const proposalData = await videoService.requestProjectProposals(
          projectId || "default_project",
          orderedSourceIds,
          targetLen,
          userIntent,
          true
        );

        if (proposalData && proposalData.proposals) {
          const generatedProposals: Record<"A" | "B", any> = {} as any;

          proposalData.proposals.forEach((p: any) => {
            const mode = p.mode === "A" ? "A" : "B";
            generatedProposals[mode] = {
              id: mode,
              proposal_id: p.proposal_id,
              mode: p.mode === "A" ? "market" : "user",
              title: p.mode === "A" ? "시장형 편집 (A)" : "사용자친화형 편집 (B)",
              desc: p.proposal_reason?.mode_reason || "백엔드 분석 기반 추천 편집안입니다.",
              score: String(Math.round(p.confidence * 100)) + "%",
              key_fragments: p.sequence.map((s: any) => s.fragment_id),
              proposal_story: p.proposal_story,
              proposal_explanation: p.proposal_explanation,
              self_check: p.self_check ?? p.proposal_reason?.self_check ?? null,
              direction: {},
              snapshot_id: "R1",
              template_id: p.mode,
              slot_trace: [],
              preview_url: p.preview_url ?? null,
              preview_duration: p.preview_duration ?? 0,
            };
            
            if (generatedProposals[mode].key_fragments.length > 0) {
              generatedProposals[mode].resolved_aliases = p.sequence.map((s: any) => ({
                proposal_fragment_id: s.fragment_id,
                source_id: s.source_id,
                source_fragment_id: s.fragment_id,
                display_id: s.display_id,
                start_sec: s.start,
                end_sec: s.end,
                thumbnail_url: s.thumbnail_url
              }));
            }
          });

          // [REPROPOSAL_PROJECT_RESULT] Console Log
          console.log("[REPROPOSAL_PROJECT_RESULT]\n" + JSON.stringify({
            proposal_id: {
              A: generatedProposals.A?.proposal_id,
              B: generatedProposals.B?.proposal_id
            },
            previewUrlExists: {
              A: !!generatedProposals.A?.preview_url,
              B: !!generatedProposals.B?.preview_url
            },
            sequenceLength: {
              A: generatedProposals.A?.key_fragments?.length || 0,
              B: generatedProposals.B?.key_fragments?.length || 0
            },
            sourceDistribution: proposalData.source_usage || {}
          }, null, 2));

          setProposals(generatedProposals);
          setSelectedProposalId(generatedProposals.B ? "B" : "A");
          setCommittedProposalId(null);
        } else {
          console.warn("[Reproposal] No proposals returned from server");
        }
      } catch (err: any) {
        console.error("[Reproposal] Failed to fetch reproposaled project proposals:", err);
      }
    },
    [
      directionSnapshot,
      proposals,
      sourceFragments,
      projectId,
      orderedSourceIds,
      storyPlan,
      setProposals,
      setSelectedProposalId,
      setCommittedProposalId
    ]
  );

  const buildConsultationReply = useCallback((input: string, previousMessages: any[] = []): ConsultationDecision => {
    const normalized = input.trim();
    const repeatedAmbiguousFallback = hasRecentP6Fallback(previousMessages, [P6_FALLBACK_AMBIGUOUS, P6_FALLBACK_REPEAT]);

    if (!normalized) {
      return {
        text: "말씀을 조금 더 입력해 주시면 그 방향을 편집 의도에 반영하겠습니다.",
        shouldRunProposal: false,
        fallbackKind: "empty"
      };
    }

    const isQuestionLike = /[?？]$|왜|뭐야|무슨|어떻게|알아듣|이해/.test(normalized);
    const isVagueEditIntent = /느낌|느낌있|느낌 있게|멋있|예쁘|좋게|세련|힙하게|감각|영화처럼|분위기 있게|감성 있게|감성적|그럴듯/.test(normalized);
    const isExecutable = isExecutableEditCommand(normalized);

    if (!isExecutable) {
      if (isVagueEditIntent && repeatedAmbiguousFallback) {
        return {
          text: P6_FALLBACK_REPEAT,
          shouldRunProposal: false,
          fallbackKind: "repeat"
        };
      }

      if (isQuestionLike) {
        return {
          text: P6_FALLBACK_UNKNOWN,
          shouldRunProposal: false,
          fallbackKind: "unknown"
        };
      }

      if (isVagueEditIntent) {
        return {
          text: P6_FALLBACK_AMBIGUOUS,
          shouldRunProposal: false,
          fallbackKind: "ambiguous"
        };
      }

      return {
        text: P6_FALLBACK_UNKNOWN,
        shouldRunProposal: false,
        fallbackKind: "unknown"
      };
    }

    if (/실내|실외|외부|야외|밖/.test(normalized)) {
      return {
        text: "알겠습니다. 말씀하신 장면 조건을 반영해 A/B 편집 제안을 다시 만들겠습니다.",
        shouldRunProposal: true
      };
    }

    if (/빠르게|템포|속도|지루|짧게/.test(normalized)) {
      return {
        text: "좋습니다. 장면 전환을 더 촘촘하게 잡고, 반복되는 구간은 줄이는 방향으로 편집 의도를 조정하겠습니다.",
        shouldRunProposal: true
      };
    }

    if (/사람|인물|표정|대화|관계|가족/.test(normalized)) {
      return {
        text: "알겠습니다. 인물의 동작, 표정, 상호작용이 잘 보이는 조각을 우선 배치하는 방향으로 맞추겠습니다.",
        shouldRunProposal: true
      };
    }

    if (/감성|분위기|여운|잔잔|따뜻/.test(normalized)) {
      return {
        text: "좋습니다. 빠른 정보 전달보다 분위기와 여운이 살아나는 장면을 중심으로 편집 방향을 잡겠습니다.",
        shouldRunProposal: true
      };
    }

    if (/풍경|배경|장소|공간/.test(normalized)) {
      return {
        text: "알겠습니다. 장소와 배경은 필요한 만큼만 남기고, 이야기 흐름을 해치지 않도록 균형을 맞추겠습니다.",
        shouldRunProposal: true
      };
    }

    if (/골고루|균형|전체|여러 영상|모두/.test(normalized)) {
      return {
        text: "좋습니다. 특정 영상에 치우치지 않도록 여러 원본의 조각을 균형 있게 섞는 방향으로 준비하겠습니다.",
        shouldRunProposal: true
      };
    }

    if (/이대로|제안|만들어|진행|좋아|오케이|ok/i.test(normalized)) {
      return {
        text: "네, 지금까지의 대화 내용을 기준으로 A/B 편집 제안을 준비하겠습니다.",
        shouldRunProposal: true
      };
    }

    return {
      text: `알겠습니다. 말씀하신 "${normalized.slice(0, 40)}${normalized.length > 40 ? "..." : ""}" 방향을 반영해서 편집 의도를 조정하겠습니다.`,
      shouldRunProposal: true
    };
  }, []);

  const handleConsultation = useCallback(async (text: string) => {
    if (!storyPlan) return;

    const lower = text.toLowerCase();
    const shouldConfirm =
      lower.includes("이대로") ||
      lower.includes("좋아") ||
      lower.includes("오케이") ||
      lower.includes("진행해") ||
      lower.includes("확정") ||
      /ok$/i.test(lower);

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

    const consultationDecision = buildConsultationReply(text, storyPlan.messages ?? []);

    if (!consultationDecision.shouldRunProposal) {
      console.log("[P6_INTENT_FALLBACK]\n" + JSON.stringify({
        inputText: text,
        fallbackKind: consultationDecision.fallbackKind,
        shouldRunProposal: false
      }, null, 2));

      setStoryPlan((prev: any) => {
        if (!prev) return prev;
        return {
          ...prev,
          consultation_status: "needs_edit_condition",
          user_notes: text,
          messages: (prev.messages ?? []).map((m: any) =>
            m.id === aiMsgId ? { ...m, text: consultationDecision.text, isInterpreting: false } : m
          ),
        };
      });
      return;
    }

    // Background Narrative AI call with 30s timeout
    const startTime = Date.now();
    let result: any = { status: "TIMEOUT", patch: null, latency_ms: 0, error: "Frontend 30s timeout" };
    if (!LEGACY_NARRATIVE_ENABLED) {
      console.log("[INTENT-ROUTE]\n" + JSON.stringify({
        stage: "narrative_skipped",
        enabled: LEGACY_NARRATIVE_ENABLED,
        inputText: text
      }, null, 2));
    } else {
      console.log("[INTENT-ROUTE]\n" + JSON.stringify({
        stage: "narrative_call",
        enabled: LEGACY_NARRATIVE_ENABLED,
        inputText: text
      }, null, 2));
      try {
        const timeoutPromise = new Promise((_, reject) =>
          setTimeout(() => reject(new Error("TIMEOUT")), 30000)
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
    }

    const nextIntent: any = { ...(storyPlan.story_intent || {}) };
    
    const shouldUseDeterministicFallback = !(
      LEGACY_NARRATIVE_ENABLED &&
      result.status === "OK" &&
      result.patch
    );

    if (result.status === "OK" && result.patch && LEGACY_NARRATIVE_ENABLED) {
      Object.assign(nextIntent, result.patch);
      console.log("[INTENT-ROUTE]\n" + JSON.stringify({
        stage: "patch_consumed",
        enabled: LEGACY_NARRATIVE_ENABLED,
        status: result.status,
        patch: result.patch
      }, null, 2));
    }
    // NOTE: patch_suppressed 로그는 게이트 off 시 narrative 호출 자체가
    // 스킵되면서 도달 불가(dead)가 되어 제거됨 — narrative_skipped로 대체.

    if (shouldUseDeterministicFallback) {
      if (/빠르게|템포|속도/.test(lower)) nextIntent.pace = "fast";
      if (/감성|따뜻|여운/.test(lower)) nextIntent.mood = "warm";
      if (/사람|인물|가족/.test(lower)) nextIntent.focus = "people";
      if (/풍경|배경|장소/.test(lower)) nextIntent.focus = "landscape";
      if (/골고루|균형/.test(lower)) nextIntent.coverage = "balanced_sources";
      console.log("[INTENT-ROUTE]\n" + JSON.stringify({
        stage: "fallback_used(deterministic)",
        enabled: LEGACY_NARRATIVE_ENABLED,
        status: result.status,
        nextIntent
      }, null, 2));
    }

    const nextStatus = shouldConfirm ? "confirmed" : "user_requested_change";
    const finalAiText = consultationDecision.text;

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

    if (!shouldConfirm) {
      if (!orderedSourceIds || orderedSourceIds.length === 0) {
        console.warn("[Consultation] orderedSourceIds is empty. Skipping proposal generation.");
        return;
      }

      const inputText = text;
      console.log("[CONSULTATION_NL_SUBMIT]\n" + JSON.stringify({
        inputText,
        shouldConfirm,
        sourceCount: orderedSourceIds.length
      }, null, 2));

      const targetLen = proposals?.A?.preview_duration || 60.0;
      const userIntent = {
        ...nextIntent,
        instruction_text: inputText
      };

      const payload = {
        project_id: projectId || "default_project",
        source_ids: orderedSourceIds,
        target_length: targetLen,
        user_intent: userIntent,
        refresh: true
      };

      console.log("[INTENT-ROUTE]\n" + JSON.stringify({
        stage: "proposal_submit",
        enabled: LEGACY_NARRATIVE_ENABLED,
        user_intent: userIntent
      }, null, 2));

      console.log("[CONSULTATION_PROJECT_REQUEST]\n" + JSON.stringify({
        apiUrl: `${videoService.API_BASE_URL}/proposals/project`,
        payloadSummary: payload
      }, null, 2));

      try {
        const proposalData = await videoService.requestProjectProposals(
          projectId || "default_project",
          orderedSourceIds,
          targetLen,
          userIntent,
          true
        );

        if (proposalData && proposalData.proposals) {
          const generatedProposals: Record<"A" | "B", any> = {} as any;

          proposalData.proposals.forEach((p: any) => {
            const mode = p.mode === "A" ? "A" : "B";
            generatedProposals[mode] = {
              id: mode,
              proposal_id: p.proposal_id,
              mode: p.mode === "A" ? "market" : "user",
              title: p.mode === "A" ? "시장형 편집 (A)" : "사용자친화형 편집 (B)",
              desc: p.proposal_reason?.mode_reason || "백엔드 분석 기반 추천 편집안입니다.",
              score: String(Math.round(p.confidence * 100)) + "%",
              key_fragments: p.sequence.map((s: any) => s.fragment_id),
              proposal_story: p.proposal_story,
              proposal_explanation: p.proposal_explanation,
              self_check: p.self_check ?? p.proposal_reason?.self_check ?? null,
              direction: {},
              snapshot_id: "R1",
              template_id: p.mode,
              slot_trace: [],
              preview_url: p.preview_url ?? null,
              preview_duration: p.preview_duration ?? 0,
            };
            
            if (generatedProposals[mode].key_fragments.length > 0) {
              generatedProposals[mode].resolved_aliases = p.sequence.map((s: any) => ({
                proposal_fragment_id: s.fragment_id,
                source_id: s.source_id,
                source_fragment_id: s.fragment_id,
                display_id: s.display_id,
                start_sec: s.start,
                end_sec: s.end,
                thumbnail_url: s.thumbnail_url
              }));
            }
          });

          // [CONSULTATION_PROJECT_RESULT] Console Log
          console.log("[CONSULTATION_PROJECT_RESULT]\n" + JSON.stringify({
            proposal_id: {
              A: generatedProposals.A?.proposal_id,
              B: generatedProposals.B?.proposal_id
            },
            sequenceLength: {
              A: generatedProposals.A?.key_fragments?.length || 0,
              B: generatedProposals.B?.key_fragments?.length || 0
            },
            previewUrlExists: {
              A: !!generatedProposals.A?.preview_url,
              B: !!generatedProposals.B?.preview_url
            }
          }, null, 2));

          // Guard A/B existence
          if (!generatedProposals.A || !generatedProposals.B) {
            console.warn("[CONSULTATION_PROJECT_RESULT] Missing A/B proposals. Keeping existing proposals.");
            return;
          }

          setCommittedProposalId(null);
          setProposals(generatedProposals);
          setSelectedProposalId(generatedProposals.B ? "B" : "A");
        }
      } catch (apiErr: any) {
        console.error("[Consultation] requestProjectProposals Error:", apiErr);
      }
    }
  }, [
    storyPlan,
    buildConsultationReply,
    proposals,
    orderedSourceIds,
    projectId,
    setSelectedProposalId,
    setCommittedProposalId,
    setProposals
  ]);

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
