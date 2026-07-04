import { useState, useCallback, useEffect } from "react";
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

// [PERSON-PALETTE] 저장된 사람 이름 — 동적 편집 어휘 (CenterPanel이 주입)
const KNOWN_PERSON_NAMES: string[] = [];
export function setKnownPersonNames(names: string[]) {
  KNOWN_PERSON_NAMES.splice(0, KNOWN_PERSON_NAMES.length, ...names.filter(Boolean));
}

function isExecutableEditCommand(input: string): boolean {
  const hasSceneOrSubject =
    /실내|실외|야외|운동장|물놀이|바다|해변|해안|바닷가|갯벌|수영|계곡|강|풍경|음식|요리|사람|인물|아이|어린이|밤|야경|거리|호텔|침실|방|체육관|공원|놀이터|외부|밖|표정|가족|배경|장소|공간/.test(input) ||
    // [PERSON-PALETTE] "X 나오는 장면/조각/컷" 은 대상이 무엇이든 편집 명령
    /나오는\s*(장면|조각|컷|부분)/.test(input) ||
    // 저장된 사람 이름이 들어 있으면 편집 대상 인정 ("은한이만 남겨줘")
    KNOWN_PERSON_NAMES.some((n) => n.length >= 2 && input.includes(n));
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

  // [FLOW] 제안 세대 기록 — 중앙창 타임라인에 흘려보내고, 옛 제안을 다시 무대로 복원.
  // pair 전체를 스냅샷으로 보관하므로 setProposals(entry.pair)만으로 조각맵까지 동기화된다.
  const [proposalHistory, setProposalHistory] = useState<Array<{
    id: string; ts: number; pair: Record<"A" | "B", Proposal>;
  }>>([]);
  const [activeProposalEntryId, setActiveProposalEntryId] = useState<string | null>(null);

  // 프로젝트 전환 시 세대 기록 초기화 (storyPlan과 동일 수명)
  useEffect(() => {
    setProposalHistory([]);
    setActiveProposalEntryId(null);
  }, [projectId]);

  // proposals가 바뀔 때마다 세대 기록 갱신 — 새 pair면 append, 같은 pair면 스냅샷만 갱신
  useEffect(() => {
    if (!proposals?.A || !proposals?.B) return;
    const sig = `${(proposals.A as any).proposal_id ?? "A"}|${(proposals.B as any).proposal_id ?? "B"}`;
    setActiveProposalEntryId(sig);
    setProposalHistory((prev) => {
      const i = prev.findIndex((h) => h.id === sig);
      if (i >= 0) {
        const next = [...prev];
        next[i] = { ...next[i], pair: proposals };
        return next;
      }
      console.log("[FLOW] proposal generation appended:", sig);
      return [...prev, { id: sig, ts: Date.now(), pair: proposals }];
    });
  }, [proposals]);

  const restoreProposalEntry = useCallback((id: string) => {
    setProposalHistory((prev) => {
      const entry = prev.find((h) => h.id === id);
      if (entry) {
        console.log("[FLOW] restore proposal entry:", id);
        setProposals(entry.pair);
        setActiveProposalEntryId(id);
        setSelectedProposalId(null);
      }
      return prev;
    });
  }, []);

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
      // [R2-B] orderedSourceIds가 비어도 지시를 버리지 않는다 — 조각 pool에서 source 유도.
      // (Camellia 재현 결함: 지시가 백엔드에 도달하지 못하고 조용히 소멸)
      let effectiveSourceIds = orderedSourceIds && orderedSourceIds.length > 0
        ? orderedSourceIds
        : Array.from(new Set(
            (sourceFragments ?? []).map((f: any) => f.source_id).filter(Boolean)
          )) as string[];
      if (effectiveSourceIds.length === 0 && storyPlan?.sources?.length) {
        effectiveSourceIds = storyPlan.sources
          .map((s: any) => s.source_id ?? s.id)
          .filter(Boolean);
      }
      if (effectiveSourceIds.length === 0) {
        console.warn("[Consultation] source ids unresolved (orderedSourceIds/fragments/storyPlan 모두 빈 값). Skipping proposal generation.");
        return;
      }
      if (!orderedSourceIds || orderedSourceIds.length === 0) {
        console.warn("[Consultation] orderedSourceIds empty → fallback source ids:", effectiveSourceIds);
      }

      const inputText = text;
      console.log("[CONSULTATION_NL_SUBMIT]\n" + JSON.stringify({
        inputText,
        shouldConfirm,
        sourceCount: effectiveSourceIds.length
      }, null, 2));

      const targetLen = proposals?.A?.preview_duration || 60.0;
      const userIntent = {
        ...nextIntent,
        instruction_text: inputText
      };

      const payload = {
        project_id: projectId || "default_project",
        source_ids: effectiveSourceIds,
        target_length: targetLen,
        user_intent: userIntent,
        refresh: true
      };

      console.log("[INTENT-ROUTE]\n" + JSON.stringify({
        stage: "proposal_submit",
        enabled: LEGACY_NARRATIVE_ENABLED,
        user_intent: userIntent
      }, null, 2));

      // [UI-④] 재편집 착수 보고 — 무엇을 얼마나 보는지, 시간은 얼마나 걸릴지
      const _poolSize = (sourceFragments ?? []).length;
      const _estMin = Math.max(1, Math.ceil(((_poolSize / 8) * 7 + 45) / 60));
      setStoryPlan((prev: any) => prev ? {
        ...prev,
        messages: [...(prev.messages ?? []), {
          id: `ai_working_${Date.now()}`,
          sender: "ai",
          text: `조각 ${_poolSize}개를 "${inputText}" 기준으로 다시 고르고 있어요. 판단과 미리보기 렌더까지 약 ${_estMin}분 예상 — 끝나면 알려드릴게요.`,
          timestamp: Date.now(),
        }],
      } : prev);

      console.log("[CONSULTATION_PROJECT_REQUEST]\n" + JSON.stringify({
        apiUrl: `${videoService.API_BASE_URL}/proposals/project`,
        payloadSummary: payload
      }, null, 2));

      try {
        const proposalData = await videoService.requestProjectProposals(
          projectId || "default_project",
          effectiveSourceIds,
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

          // [FLOW/HONEST-EMPTY] 조건에 맞는 조각이 0개면 침묵하지 않고 흐름에 설명을 남긴다.
          // (Hollyhock "실내만" 사례: keep=0 → 조각맵/무대가 비어 고장처럼 보였던 문제)
          const emptyA = (generatedProposals.A?.key_fragments?.length || 0) === 0;
          const emptyB = (generatedProposals.B?.key_fragments?.length || 0) === 0;

          // [UI-⑤] 편집 완료 보고 — 과하지 않게, 결과 요약 한 줄
          if (!emptyA || !emptyB) {
            const _fmt = (p: any) => `${p?.key_fragments?.length ?? 0}조각 ${Math.round(p?.preview_duration ?? 0)}초`;
            setStoryPlan((prev: any) => prev ? {
              ...prev,
              messages: [...(prev.messages ?? []), {
                id: `ai_done_${Date.now()}`,
                sender: "ai",
                text: `다 골랐습니다 — A안 ${_fmt(generatedProposals.A)} · B안 ${_fmt(generatedProposals.B)}. 아래 무대에서 재생해 보시고, 방향이 다르면 조건을 바꿔 말씀해 주세요.`,
                timestamp: Date.now(),
              }],
            } : prev);
          }

          if (emptyA && emptyB) {
            const sc = generatedProposals.B?.self_check || generatedProposals.A?.self_check;
            const theme = sc?.theme ? `'${sc.theme}' ` : "";
            setStoryPlan((prev: any) => prev ? {
              ...prev,
              messages: [...(prev.messages ?? []), {
                id: `ai_empty_${Date.now()}`,
                sender: "ai",
                text: `말씀하신 ${theme}조건에 맞는 조각을 찾지 못했습니다. 조작된 결과를 보여드리지 않기 위해 빈 제안을 드립니다. 다른 조건으로 말씀해 주시거나, 이전 제안을 타임라인에서 '다시 열기'로 불러오실 수 있어요.`,
                timestamp: Date.now(),
              }],
            } : prev);
          }
        } else {
          // [FLOW/NO-SILENCE] 200이어도 proposals가 없으면(백엔드 ERROR payload 등)
          // 조용히 삼키지 않는다 — 흐름에 실패 사유를 남긴다 (locked 사건 재발 방지)
          const errMsg = (proposalData as any)?.message || (proposalData as any)?.status || "알 수 없는 오류";
          console.warn("[Consultation] proposals missing in response:", proposalData);
          setStoryPlan((prev: any) => prev ? {
            ...prev,
            messages: [...(prev.messages ?? []), {
              id: `ai_fail_${Date.now()}`,
              sender: "ai",
              text: `제안 생성이 실패했습니다 (${String(errMsg).slice(0, 80)}). 잠시 후 같은 지시를 다시 보내주시면 재시도할게요.`,
              timestamp: Date.now(),
            }],
          } : prev);
        }
      } catch (apiErr: any) {
        console.error("[Consultation] requestProjectProposals Error:", apiErr);
        setStoryPlan((prev: any) => prev ? {
          ...prev,
          messages: [...(prev.messages ?? []), {
            id: `ai_fail_${Date.now()}`,
            sender: "ai",
            text: "서버와의 통신이 실패했습니다. 잠시 후 같은 지시를 다시 보내주시면 재시도할게요.",
            timestamp: Date.now(),
          }],
        } : prev);
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
    logProposalPair,
    proposalHistory,
    activeProposalEntryId,
    restoreProposalEntry
  };
};
