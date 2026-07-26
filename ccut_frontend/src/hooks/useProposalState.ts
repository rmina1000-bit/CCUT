import { useState, useCallback, useEffect, useRef } from "react";
import { Proposal, Direction, DirectionSnapshot } from "@/proposal/proposalTypes";
import { createNextSnapshot } from "@/proposal/directionSnapshot";
import { generateProposals } from "@/proposal/proposalOrchestrator";
import { Fragment } from "@/data/fragmentData";
import { narrativeService } from "@/services/narrativeService";
import { videoService } from "@/services/videoService";
import { assignShortDisplayIds, recalcDisplayIds } from "@/lib/fragmentIdentity";
import { storyGateEnabled } from "@/hooks/useStoryGate";  // [STORY-GATE P3/S3] 완료 문구 분기
import { DEBUG_LOG } from "@/utils/debugFlags";
import { recordMirrorEvent } from "@/utils/mirrorEventLog";

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
  // [#49 (a) 2단] content=내용 지시(의도 갱신) / inherit=재실행(직전 의도 승계) /
  // inherit_empty=재실행인데 활성 의도 없음(무필터+고지) / clear=의도 해제(무필터)
  intentKind?: "content" | "inherit" | "inherit_empty" | "clear";
  // [INTENT-ROUTER] 백엔드 종업원이 애칭→풀네임 등으로 정규화한 실행 지시문
  normalizedInstruction?: string;
  // [ARCHIVE P1] archive_query가 추린 후보 조각 (인물+장소 교집합) — hub가 이만 판정
  candidateFragmentIds?: string[];
  rubric?: any;
  // [ARCHIVE B] 아카이브 포함 승인 시 프로젝트에 연결할 소스
  includeSourceIds?: string[];
};

const LEGACY_NARRATIVE_ENABLED =
  String(import.meta.env.CCUT_LEGACY_NARRATIVE ?? "0") === "1";

// [2026-07-06 국장지시] CCUT은 대화하는 동료다 — 이 폴백은 서버 연결 실패 시에만
// 도달하므로, "대화 못 하는 AI" 자기부정 대신 연결 문제를 정직하게 알린다.
const P6_FALLBACK_UNKNOWN =
  "죄송해요, 지금 대화 엔진 연결이 잠시 원활하지 않아 말씀을 제대로 해석하지 못했어요. 잠시 후 다시 말씀해 주세요 — 편집 지시('실내만', '5개로 줄여줘')는 연결이 복구되는 대로 바로 반영할게요.";
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

  // [PERSON-PALETTE 2026-07-04] 인물 편집 '형식'은 이름 저장 여부와 무관하게 실행 명령으로
  // 통과시킨다. 이름 통일(은한이→정은한) 후 옛 호칭이 KNOWN_PERSON_NAMES에서 빠져 입구에서
  // "OO만 편집해줘"가 unknown으로 막히던 결함 수리. 최종 keep은 백엔드(hub)가 판정하고,
  // 해당 인물이 없으면 honest-empty로 정직 응답한다(프론트가 미리 막지 않음).
  // "나오는 영상"은 기존 (장면|조각|컷|부분)에 빠져 있던 형태 — 함께 보강.
  const isPersonLikeEditForm =
    /나오는\s*(장면|조각|컷|부분|영상|것)/.test(input) ||
    /\S{2,}만\s*(편집|남겨|남기|골라|추려|보여|모아|살려)/.test(input);

  return isPersonLikeEditForm || hasCountOrPace || hasConfirm || (hasSceneOrSubject && hasEditOperator);
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

  // [#49 (a) 2단 — 의도 승계] 활성 의도 = 마지막 '내용 지시'만 기억. 명령(retrigger)은 덮지 않는다.
  // 세션 수명 — 프로젝트 전환 시 초기화 (영속은 범위 밖, 한계로 보고).
  const activeIntentRef = useRef<string | null>(null);

  // 프로젝트 전환 시 세대 기록 초기화 (storyPlan과 동일 수명)
  useEffect(() => {
    setProposalHistory([]);
    setActiveProposalEntryId(null);
    activeIntentRef.current = null; // [#49 (a)] 의도도 프로젝트 수명
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
      DEBUG_LOG && console.log("[FLOW] proposal generation appended:", sig);
      return [...prev, { id: sig, ts: Date.now(), pair: proposals }];
    });
  }, [proposals]);

  // [TIMELINE-PERSIST 2026-07-05] 저장된 제안 세대 일괄 복원 — 프로젝트 열기 시
  // chat_state에서. 프로젝트 삭제 전까지 세대가 계속 쌓이는 영속 타임라인의 절반.
  const hydrateProposalHistory = useCallback(
    (entries: Array<{ id: string; ts: number; pair: Record<"A" | "B", Proposal> }>) => {
      if (!entries?.length) return;
      setProposalHistory(entries);
      setActiveProposalEntryId(entries[entries.length - 1]?.id ?? null);
      DEBUG_LOG && console.log(`[TIMELINE-PERSIST] proposal history 복원: ${entries.length}세대`);
    }, []);

  const restoreProposalEntry = useCallback((id: string) => {
    const entry = proposalHistory.find((h) => h.id === id);
    if (entry) {
      DEBUG_LOG && console.log("[FLOW] restore proposal entry:", id);
      setProposals(entry.pair);
      setActiveProposalEntryId(id);
      setSelectedProposalId(null);
      recordMirrorEvent({
        event_kind: "edit_again",
        project_id: projectId || "default_project",
        proposal_ids: {
          A: (entry.pair as any)?.A?.proposal_id,
          B: (entry.pair as any)?.B?.proposal_id,
        },
        proposal_history_id: id,
      });
    }
  }, [projectId, proposalHistory]);

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
    recordMirrorEvent({
      event_kind: "accept",
      project_id: projectId || "default_project",
      proposal_id: (proposals[mode] as any)?.proposal_id,
      proposal_slot: id,
    });
  }, [proposals, projectId]);

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
          A: (proposals.A as any)?.proposal_id,
          B: (proposals.B as any)?.proposal_id
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
      const targetProposalSlot = selectedProposalId || committedProposalId;
      const targetProposal = targetProposalSlot === "A" || targetProposalSlot === "B"
        ? (proposals as any)?.[targetProposalSlot]
        : null;
      recordMirrorEvent({
        event_kind: "edit_again",
        project_id: projectId || "default_project",
        proposal_id: targetProposal?.proposal_id,
        proposal_slot: targetProposalSlot || undefined,
      });

      // [REPROPOSAL_PROJECT_REQUEST] Console Log
      console.log("[REPROPOSAL_PROJECT_REQUEST]\n" + JSON.stringify({
        apiUrl: `${videoService.API_BASE_URL}/proposals/project`,
        payloadSummary: payload,
        source_ids: orderedSourceIds,
        instruction_text: instructionText
      }, null, 2));

      try {
        const proposalStartedAt = Date.now();
        const proposalData = await videoService.requestProjectProposals(
          projectId || "default_project",
          orderedSourceIds,
          targetLen,
          userIntent,
          true
        );
        const proposalTotalMs = Date.now() - proposalStartedAt;

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
              proposal_reason: p.proposal_reason ?? null,
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
          recordMirrorEvent({
            event_kind: "qwen_complete",
            project_id: projectId || "default_project",
            proposal_ids: {
              A: generatedProposals.A?.proposal_id,
              B: generatedProposals.B?.proposal_id,
            },
            total_ms: proposalTotalMs,
          });
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
      selectedProposalId,
      committedProposalId,
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

    // [INTENT-ROUTER] 메뉴판 철거 — 해석은 백엔드 종업원(/intent/route-edit)이 한다.
    // 프론트는 빈 입력만 막고 말을 거의 그대로 보낸다. 서버 불가 시에만 구 메뉴판 폴백(가역성).
    let consultationDecision: ConsultationDecision;
    // [관문D 2026-07-21 스코프수리] route는 아래 try 블록 지역변수라 try 밖(852 확정점)에서 못 쓴다.
    //   근거를 함수 스코프 변수로 승격 — try 안(route 유효)에서 담아 852에서 참조.
    let candidateEvidence: Record<string, string[]> | undefined;
    let mirrorRouteTotalMs: number | undefined;
    let mirrorResolveMs: number | undefined;
    try {
      // [조각 라벨 지정 편집 2026-07-06] 조각맵 타일 라벨(display_id "K1")→조각ID 매핑 동봉 —
      // "K1,K4,K6만으로 편집해줘"를 백엔드가 정확한 조각 후보로 해석할 수 있게.
      const fragmentLabels: Record<string, string> = {};
      (sourceFragments ?? []).forEach((f: any) => {
        if (!f || f.status === "removed") return;
        const label = String(f.display_id || "").toUpperCase();
        if (/^[A-Z]{1,2}\d{1,3}$/.test(label)) {
          fragmentLabels[label] = String(f.fragment_id || "").replace(/_[LMR]\d*$/, "");
        }
      });
      const routePayload = {
        project_id: projectId,
        source_ids: orderedSourceIds ?? [],
        input_text: text,
        recent_messages: (storyPlan.messages ?? [])
          .slice(-6)
          .map((m: any) => ({ sender: m.sender, text: m.text })),
        selected_proposal_id: selectedProposalId,
        fragment_labels: fragmentLabels,
      };
      // [F2 스트리밍] 스트림 우선 — 대화 reply가 토큰 단위로 즉시 차오른다.
      // 스트림 실패 시 기존 일괄 엔드포인트로 폴백 (무언 실패 금지, 계약 동일).
      let route: any;
      let routeTotalMs: number | undefined;
      const _f2T0 = Date.now();
      try {
        route = await videoService.routeEditIntentStream(routePayload, (accum: string) => {
          setStoryPlan((prev: any) => prev ? {
            ...prev,
            messages: (prev.messages ?? []).map((m: any) =>
              m.id === aiMsgId ? { ...m, text: accum, isInterpreting: true } : m),
          } : prev);
        });
        routeTotalMs = Date.now() - _f2T0;
        console.log(`[F2-TTFT front] stream total_ms=${routeTotalMs}`);
      } catch (streamErr: any) {
        console.warn("[F2] 스트림 실패 → 일괄 폴백:", streamErr?.message);
        route = await videoService.routeEditIntent(routePayload);
        routeTotalMs = Date.now() - _f2T0;
        console.log(`[F2-TTFT front] batch total_ms=${routeTotalMs}`);
      }
      mirrorRouteTotalMs = routeTotalMs;
      const routeResolveMs = Number(route?.resolveMs ?? route?.resolve_ms);
      mirrorResolveMs = Number.isFinite(routeResolveMs) ? routeResolveMs : undefined;
      console.log("[INTENT-ROUTER route]\n" + JSON.stringify({
        action: route.action,
        via: route.via,
        confidence: route.confidence,
        normalized: route.normalized_instruction,
        matched: route.matched
      }, null, 2));

      const b21Legacy = Object.entries(route.matched ?? {})
        .filter(([key, value]) => key !== "kind" && value !== null && value !== undefined && value !== "")
        .map(([key, value]) => ({ [key]: value }));
      void narrativeService.interpretIntent(text)
        .then((res: any) => {
          const mirrorEvents = Array.isArray(res?.mirror?.mentioned_events)
            ? res.mirror.mentioned_events.map((item: any) => item?.event ?? item)
            : null;
          console.log(`[B2-1] INPUT{text=${JSON.stringify(text)}} -> OUTPUT{legacy=${JSON.stringify(b21Legacy)}, mirror=${JSON.stringify(mirrorEvents)}, used="legacy"}`);
          if (mirrorEvents && mirrorEvents.length > 0) {
            const requestLabel = res?.mirror?.request_type === "story_composition" ? " (스토리 구성 요청)" : "";
            const auxText = `제가 이해한 조건: ${mirrorEvents.join(", ")}${requestLabel}`;
            setStoryPlan((prev: any) => prev ? {
              ...prev,
              messages: [...(prev.messages ?? []), {
                id: `mirror_aux_${Date.now()}`,
                sender: "ai" as const,
                text: auxText,
                timestamp: Date.now() + 2,
              }],
            } : prev);
          }
        })
        .catch(() => {
          console.log(`[B2-1] INPUT{text=${JSON.stringify(text)}} -> OUTPUT{legacy=${JSON.stringify(b21Legacy)}, mirror=null, used="legacy"}`);
        });

      // [SHOW 2026-07-05] 조회/열람 — 편집이 아니라 보여주기. 결과 카드를 흐름 속
      // 메시지로 남긴다(타임라인 diff-sync가 자동 영속 → F5에도 유지, 클릭=재생).
      if (route.action === "show_fragments") {
        setStoryPlan((prev: any) => {
          if (!prev) return prev;
          return {
            ...prev,
            messages: (prev.messages ?? []).map((m: any) =>
              m.id === aiMsgId
                ? { ...m, text: route.reply || "찾은 조각입니다.", isInterpreting: false,
                    kind: "search_results", results: route.results ?? [] }
                : m),
          };
        });
        return; // 제안 생성 없음 — 편집하라고 할 때만 편집한다
      }
      // [#57 REVISION 도구층] 국소 수정 — 전체 재제안으로 뭉개지 않고 /revision/proposals로
      // 집행한다 (큐원=이해 op 동봉, 규칙=시퀀스 조작). 실패/미지원이면 기존 재제안 경로 폴백.
      if (route.action === "revise_current" && route.revision) {
        const targetMode: "A" | "B" | null =
          route.revision.target_mode === "A" || route.revision.target_mode === "B"
            ? route.revision.target_mode
            : (selectedProposalId === "A" || selectedProposalId === "B" ? selectedProposalId : null);
        const targetProposal = targetMode ? (proposals as any)?.[targetMode] : null;
        if (targetMode && targetProposal?.proposal_id) {
          try {
            const revRes = await videoService.reviseProposal({
              proposal_id: targetProposal.proposal_id,
              instruction: route.normalized_instruction || text,
              source_ids: orderedSourceIds ?? [],
              revision: route.revision,
            });
            console.log("[P4-REV front]\n" + JSON.stringify({
              status: revRes.status, parent: revRes.parent, proposal_id: revRes.proposal_id,
              reason: revRes.reason, count: revRes.count,
            }, null, 2));
            if (revRes.status === "OK") {
              const beforeCount = targetProposal.key_fragments?.length ?? 0;
              const seq = revRes.sequence ?? [];
              setProposals((prev: any) => {
                if (!prev?.[targetMode]) return prev;
                return {
                  ...prev,
                  [targetMode]: {
                    ...prev[targetMode],
                    proposal_id: revRes.proposal_id,
                    key_fragments: seq.map((s: any) => s.fragment_id),
                    resolved_aliases: seq.map((s: any) => ({
                      proposal_fragment_id: s.fragment_id,
                      source_id: s.source_id,
                      source_fragment_id: s.fragment_id,
                      display_id: s.display_id,
                      start_sec: s.start,
                      end_sec: s.end,
                      thumbnail_url: s.thumbnail_url,
                    })),
                    // 구 프리뷰는 수정 전 시퀀스의 렌더 — 그대로 두면 §5 위반(화면≠데이터)
                    preview_url: null,
                  },
                };
              });
              // [§5 정직 보고] 무엇이 몇 개 → 몇 개가 됐는지 + 원시 사유를 흐름에 남긴다
              const doneText = `${targetMode}안에 반영했어요 — 조각 ${beforeCount}개 → ${revRes.count}개. (${revRes.reason})`;
              setStoryPlan((prev: any) => {
                if (!prev) return prev;
                return {
                  ...prev,
                  messages: (prev.messages ?? []).map((m: any) =>
                    m.id === aiMsgId ? { ...m, text: doneText, isInterpreting: false } : m),
                };
              });
              return; // 국소 수정 완결 — 전체 재제안 없음
            }
            console.warn("[P4-REV front] 미집행 status=", revRes.status, "→ 재제안 경로 폴백");
          } catch (e: any) {
            console.warn("[P4-REV front] 실패 — 재제안 경로 폴백:", e?.message);
          }
        }
      }
      // [#49 (a) — 국장 승인 2026-07-17] retrigger = 명령: 직전 활성 의도 승계(있으면) /
      // 무필터+정직 고지(없으면). intent_clear = 의도 해제 + 무필터 복귀 (F4·§1-10).
      // 명령이 의도를 덮어쓰지 않는다 — 16:06 사건("스토리 다시 편집하게 해줘"가 의도를 대체) 절단.
      const isRetrigger = route.action === "retrigger";
      const isIntentClear = route.action === "intent_clear";
      consultationDecision = {
        text: route.reply || "네, 확인했습니다.",
        // revise_current는 현 단계에선 재제안 경로로 수렴 (백엔드 REVISION 게이트가 하류 처리)
        // ask_include_archive는 승인 대화 — 제안 실행 없이 되묻기만 표시 (P1)
        shouldRunProposal: route.action === "run_proposal" || route.action === "revise_current"
          || isRetrigger || isIntentClear,
        fallbackKind: route.action === "ask_clarification" ? "ambiguous"
          : route.action === "answer_only" ? "unknown"
          : route.action === "ask_include_archive" ? "ambiguous" : undefined,
        normalizedInstruction: isIntentClear ? ""
          : isRetrigger ? (activeIntentRef.current ?? "")
          : (route.normalized_instruction || text),
        intentKind: isIntentClear ? "clear"
          : isRetrigger ? (activeIntentRef.current ? "inherit" : "inherit_empty")
          : "content",
        candidateFragmentIds: route.candidate_fragment_ids || undefined,
        rubric: route.rubric || route.params?.rubric || undefined,
        // [ARCHIVE B] "응, 포함해줘" 승인 시 종업원이 지정한 아카이브 소스
        includeSourceIds: route.include_source_ids || undefined,
      };
      candidateEvidence = route.candidate_evidence;
    } catch (e: any) {
      console.warn("[INTENT-ROUTER] 서버 라우팅 실패 → 구 메뉴판 폴백:", e?.message);
      consultationDecision = buildConsultationReply(text, storyPlan.messages ?? []);
    }

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
          m.id === aiMsgId ? { ...m, text: finalAiText, isInterpreting: false, candidate_evidence: candidateEvidence } : m
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

      // [ARCHIVE B] 아카이브 포함 승인 — 소스를 프로젝트에 연결(멱등)하고 이번 제안에 즉시 반영
      if (consultationDecision.includeSourceIds?.length) {
        try {
          const added = await videoService.addSourcesToProject(
            projectId || "default_project", consultationDecision.includeSourceIds);
          effectiveSourceIds = Array.from(new Set([
            ...effectiveSourceIds, ...consultationDecision.includeSourceIds]));
          console.log("[ARCHIVE-INCLUDE]\n" + JSON.stringify({
            requested: consultationDecision.includeSourceIds,
            added: added?.added, effectiveSourceCount: effectiveSourceIds.length
          }, null, 2));
        } catch (e: any) {
          console.warn("[ARCHIVE-INCLUDE] 소스 연결 실패 — 이번 제안은 기존 소스로만:", e?.message);
        }
      }

      // [#49 (a) 2단 절단 — 구판 `normalizedInstruction || text`가 재실행 명령을 의도로 승격시키던 지점]
      // 내용 지시만 원문 폴백을 갖고, 승계/해제는 decision이 확정한 값(승계 의도 또는 "")을 그대로 쓴다.
      const intentKind = consultationDecision.intentKind ?? "content";
      const inputText = consultationDecision.candidateFragmentIds?.length
        ? ""
        : intentKind === "content"
          ? (consultationDecision.normalizedInstruction || text)
          : (consultationDecision.normalizedInstruction ?? "");
      if (intentKind === "content" && inputText.trim()) activeIntentRef.current = inputText; // 의도 갱신
      if (intentKind === "clear") activeIntentRef.current = null;                            // 의도 해제
      console.log("[CONSULTATION_NL_SUBMIT]\n" + JSON.stringify({
        inputText,
        rawInput: text,
        shouldConfirm,
        sourceCount: effectiveSourceIds.length
      }, null, 2));

      const targetLen = proposals?.A?.preview_duration || 60.0;
      const userIntent = {
        ...nextIntent,
        instruction_text: inputText,
        // [ARCHIVE P1] 종업원이 추린 교집합 후보 — 백엔드 hub가 이 조각들만 판정
        ...(consultationDecision.candidateFragmentIds?.length
          ? { candidate_fragment_ids: consultationDecision.candidateFragmentIds }
          : {}),
        ...(consultationDecision.rubric ? { rubric: consultationDecision.rubric } : {})
      };

      const payload = {
        project_id: projectId || "default_project",
        source_ids: effectiveSourceIds,
        target_length: targetLen,
        user_intent: userIntent,
        refresh: true
      };
      const activeProposalSlot = selectedProposalId || committedProposalId;
      const activeProposal = activeProposalSlot === "A" || activeProposalSlot === "B"
        ? (proposals as any)?.[activeProposalSlot]
        : null;
      recordMirrorEvent({
        event_kind: "edit_again",
        project_id: projectId || "default_project",
        proposal_id: activeProposal?.proposal_id,
        proposal_slot: activeProposalSlot || undefined,
        route_total_ms: mirrorRouteTotalMs,
        resolve_ms: mirrorResolveMs,
      });

      console.log("[INTENT-ROUTE]\n" + JSON.stringify({
        stage: "proposal_submit",
        enabled: LEGACY_NARRATIVE_ENABLED,
        user_intent: userIntent
      }, null, 2));

      // [UI-④] 재편집 착수 보고 — 현재 화면의 조각 수와 문구 숫자를 맞춘다.
      const _fragmentPoolSize = (sourceFragments ?? []).length;
      const _selectedMode = selectedProposalId === "A" || selectedProposalId === "B" ? selectedProposalId : null;
      const _visibleProposal = _selectedMode ? proposals?.[_selectedMode] : (proposals?.B ?? proposals?.A);
      const _visibleFragmentIds = Array.isArray(_visibleProposal?.key_fragments)
        ? _visibleProposal.key_fragments
        : (sourceFragments ?? [])
            .map((f: any) => f?.fragment_id || f?.proposal_fragment_id || f?.id)
            .filter(Boolean);
      const _visibleFragmentCount = _visibleFragmentIds.length;
      const _estMin = Math.max(1, Math.ceil(((_fragmentPoolSize / 8) * 7 + 45) / 60));
      // [#49 (a) 3단 — §5·F1] 적용 중인 의도를 지휘부 채팅에 정직 표시. toast 금지.
      const _workingText =
        intentKind === "inherit"
          ? `지금 "${inputText}" 기준으로 고르고 있어요. 바꾸시려면 말씀해 주세요. (약 ${_estMin}분 예상)`
        : intentKind === "inherit_empty"
          ? `적용 중인 기준이 없어서 전체에서 다시 골랐어요. 기준을 말씀해 주시면 그 기준으로 갑니다. (약 ${_estMin}분 예상)`
        : intentKind === "clear"
          ? `기준 없이 전체에서 다시 고르고 있어요. (약 ${_estMin}분 예상)`
        : `조각 ${_visibleFragmentCount}개를 "${inputText}" 기준으로 다시 고르고 있어요. 판단과 미리보기 렌더까지 약 ${_estMin}분 예상 — 끝나면 알려드릴게요.`;
      console.log(`[B2-0] INPUT{source_ids=${JSON.stringify(effectiveSourceIds)}, pool=${_fragmentPoolSize}, selected=${JSON.stringify(_visibleFragmentIds)}} -> OUTPUT{status_text=${JSON.stringify(_workingText)}, N=${_visibleFragmentCount}}`);
      setStoryPlan((prev: any) => prev ? {
        ...prev,
        messages: [...(prev.messages ?? []), {
          id: `ai_working_${Date.now()}`,
          sender: "ai",
          text: _workingText,
          timestamp: Date.now(),
        }],
      } : prev);

      console.log("[CONSULTATION_PROJECT_REQUEST]\n" + JSON.stringify({
        apiUrl: `${videoService.API_BASE_URL}/proposals/project`,
        payloadSummary: payload
      }, null, 2));

      try {
        const proposalStartedAt = Date.now();
        const proposalData = await videoService.requestProjectProposals(
          projectId || "default_project",
          effectiveSourceIds,
          targetLen,
          userIntent,
          true
        );
        const proposalTotalMs = Date.now() - proposalStartedAt;

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
              proposal_reason: p.proposal_reason ?? null,
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

          const _b20FragmentsA = generatedProposals.A?.key_fragments ?? [];
          const _b20FragmentsB = generatedProposals.B?.key_fragments ?? [];
          console.log(`[B2-0] INPUT{proposal_id=${JSON.stringify(generatedProposals.A?.proposal_id ?? null)}, frags=${JSON.stringify(_b20FragmentsA)}} -> OUTPUT{ui_count=${_b20FragmentsA.length}}`);
          console.log(`[B2-0] INPUT{proposal_id=${JSON.stringify(generatedProposals.B?.proposal_id ?? null)}, frags=${JSON.stringify(_b20FragmentsB)}} -> OUTPUT{ui_count=${_b20FragmentsB.length}}`);

          // [CONSULTATION_PROJECT_RESULT] Console Log
          console.log("[CONSULTATION_PROJECT_RESULT]\n" + JSON.stringify({
            proposal_id: {
              A: generatedProposals.A?.proposal_id,
              B: generatedProposals.B?.proposal_id
            },
            sequenceLength: {
              A: _b20FragmentsA.length,
              B: _b20FragmentsB.length
            },
            previewUrlExists: {
              A: !!generatedProposals.A?.preview_url,
              B: !!generatedProposals.B?.preview_url
            }
          }, null, 2));

          // Guard A/B existence
          if (!generatedProposals.A || !generatedProposals.B) {
            console.warn("[CONSULTATION_PROJECT_RESULT] Missing A/B proposals. Keeping existing proposals.", proposalData);
            // [SILENCE-1] 실패를 삼키지 않는다.
            //   구판은 여기서 console.warn 후 그냥 return 했다. 그런데 바로 위에서 사용자에게
            //   "약 1분 예상 — 끝나면 알려드릴게요"라고 이미 약속한 뒤였다(:1021 ai_working).
            //   실측(국장 콘솔): proposals=[] 빈 배열이 오면 [] 는 truthy 라서 아래 :1181 의
            //   정직한 실패 경로를 지나쳐 여기로 떨어지고, 사용자는 영원히 기다리게 된다.
            //   ★문구는 지어내지 않는다. 백엔드가 message 를 줬으면 그것을 그대로 쓴다.
            //   없으면 무엇이 안 됐는지 사실만 적는다(추측·위로·"다시 시도" 같은 빈말 금지).
            const _warnLines = Array.isArray((proposalData as any)?.warnings)
              ? (proposalData as any).warnings
                  .map((w: any) => (typeof w === "string" ? w : (w?.message || w?.reason)))
                  .filter(Boolean)
              : [];
            const _backendMsg = (proposalData as any)?.message
              || (_warnLines.length ? _warnLines.join(" / ") : null);
            const _got = Object.keys(generatedProposals).join("·") || "없음";
            const _failText = _backendMsg
              ? String(_backendMsg)
              : `제안을 만들지 못했습니다 — 서버가 A·B 두 안을 돌려주지 않았습니다 (받은 안: ${_got}, 응답 상태: ${(proposalData as any)?.status ?? "없음"}). 이전 제안은 그대로 두었습니다.`;
            setStoryPlan((prev: any) => prev ? {
              ...prev,
              messages: [...(prev.messages ?? []), {
                id: `ai_fail_${Date.now()}`,
                sender: "ai",
                text: _failText,
                timestamp: Date.now(),
              }],
            } : prev);
            return;
          }

          setCommittedProposalId(null);
          setProposals(generatedProposals);
          setSelectedProposalId(generatedProposals.B ? "B" : "A");
          recordMirrorEvent({
            event_kind: "qwen_complete",
            project_id: projectId || "default_project",
            proposal_ids: {
              A: generatedProposals.A?.proposal_id,
              B: generatedProposals.B?.proposal_id,
            },
            total_ms: proposalTotalMs,
          });

          // [FLOW/HONEST-EMPTY] 조건에 맞는 조각이 0개면 침묵하지 않고 흐름에 설명을 남긴다.
          // (Hollyhock "실내만" 사례: keep=0 → 조각맵/무대가 비어 고장처럼 보였던 문제)
          const emptyA = (generatedProposals.A?.key_fragments?.length || 0) === 0;
          const emptyB = (generatedProposals.B?.key_fragments?.length || 0) === 0;

          // [UI-⑤] 편집 완료 보고 — 과하지 않게, 결과 요약 한 줄
          if (!emptyA || !emptyB) {
            const _fmt = (p: any) => `${p?.key_fragments?.length ?? 0}조각 ${Math.round(p?.preview_duration ?? 0)}초`;
            const _ledger = generatedProposals.B?.proposal_reason?.ledger ?? generatedProposals.A?.proposal_reason?.ledger ?? null;
            const _ledgerHits = Array.isArray(_ledger?.hit) ? _ledger.hit : [];
            const _ledgerTokens = Array.isArray(_ledger?.matched_tokens)
              ? _ledger.matched_tokens.filter((tok: any) => typeof tok === "string" && tok.trim())
              : [];
            const _ledgerToken = _ledgerTokens[0];
            const _ledgerLine = _ledgerHits.length > 0 && _ledgerToken
              ? ` 말씀하신 '${_ledgerToken}'이 적힌 영상 ${_ledgerHits.length}개에서 골랐어요.`
              : "";
            // [4b §5 고지 — 국장 A 확정] 번역층이 실제 사용된 경우에만 해석 사실을 알린다
            const _trSc = generatedProposals.B?.self_check ?? generatedProposals.B?.proposal_reason?.self_check
              ?? generatedProposals.A?.self_check ?? generatedProposals.A?.proposal_reason?.self_check ?? null;
            const _tr = _trSc?.translated;
            const _trLine = _tr?.from && _tr?.to
              ? ` 말씀하신 '${_tr.from}'은 '${_tr.to}' 장면으로 해석했어요.`
              : "";
            // [STORY-GATE P3 / S3] 게이트 ON이면 결과 통보가 아니라 협의를 연다.
            // 승인 전에는 편집 결과물이 없으므로 "무대에서 재생해 보시고"라고 말하면 거짓말이 된다.
            const _gateOn = await storyGateEnabled();
            const _doneText = _gateOn
              ? `이런 이야기로 엮었습니다 — ${_fmt(generatedProposals.B ?? generatedProposals.A)}.${_trLine}${_ledgerLine} 원고를 읽어 보시고, 고치고 싶은 곳을 말씀해 주세요. 마음에 드시면 승인해 주시면 그때 편집으로 넘어갑니다.`
              : `다 골랐습니다 — A안 ${_fmt(generatedProposals.A)} · B안 ${_fmt(generatedProposals.B)}.${_trLine}${_ledgerLine} 아래 무대에서 재생해 보시고, 방향이 다르면 조건을 바꿔 말씀해 주세요.`;
            setStoryPlan((prev: any) => prev ? {
              ...prev,
              messages: [...(prev.messages ?? []), {
                id: `ai_done_${Date.now()}`,
                sender: "ai",
                text: _doneText,
                timestamp: Date.now(),
              }],
            } : prev);
          }

          if (emptyA && emptyB) {
            const sc = generatedProposals.B?.self_check || generatedProposals.A?.self_check;
            const theme = sc?.theme ? `'${sc.theme}' ` : "";
            // [4b §5] 빈 제안이라도 번역을 썼다면 어떤 해석으로 찾았는지 알린다
            const emptyTr = sc?.translated?.from && sc?.translated?.to
              ? ` ('${sc.translated.from}'은 '${sc.translated.to}' 장면으로 해석해 찾았어요.)`
              : "";
            setStoryPlan((prev: any) => prev ? {
              ...prev,
              messages: [...(prev.messages ?? []), {
                id: `ai_empty_${Date.now()}`,
                sender: "ai",
                text: `말씀하신 ${theme}조건에 맞는 조각을 찾지 못했습니다.${emptyTr} 조작된 결과를 보여드리지 않기 위해 빈 제안을 드립니다. 다른 조건으로 말씀해 주시거나, 이전 제안을 타임라인에서 '다시 열기'로 불러오실 수 있어요.`,
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
    // [#57] revise 타겟 결정이 현재 선택 안을 읽는다 — stale closure로 다른 안을
    // 수정하는 사고 방지 (기존 참조 587·854행도 같은 구멍이었음)
    selectedProposalId,
    committedProposalId,
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
    restoreProposalEntry,
    hydrateProposalHistory
  };
};
