// CCUT 1.0.4 - R9.1 Rollback Verified
import React, { useRef, useEffect, useState, useCallback, useMemo } from "react";
import { Upload, Play, Loader2, Send, CheckCircle2, Package, BookOpen, List, ChevronDown, AlertCircle } from "lucide-react";
import { Fragment } from "@/data/fragmentData";
import { videoService } from "@/services/videoService";
import { Direction, StoryPlanPreview } from "@/proposal/proposalTypes";
import { PhysicalClip, validateExportClips } from "@/utils/exportClipBuilder";

type AppState = "empty" | "analyzing" | "complete";

type SourceEntry = {
  source_id: string;
  label: string;
  video_url: string;
  fragments: Fragment[];
  file_size_bytes?: number;
  duration_sec?: number;
};

interface CenterPanelProps {
  selectedFragment: Fragment | null;
  selectedSource: string;
  onAnalyze?: (file?: File, extraFiles?: File[]) => Promise<boolean>;
  onExport?: (
    projectId: string
  ) => Promise<{ status: string; file_url?: string; ai_msg?: string; message?: string }>;
  onFileSelect?: (file: File) => void;
  onReproposal?: (direction: Direction) => void;
  onConsultation?: (text: string) => void;
  appState: AppState;
  onAppStateChange: (state: AppState) => void;
  analyzeProgress: number;
  analyzeMessage?: string;
  videoUrl?: string | null;
  sources?: any[];
  proposals?: any;
  committedProposalId?: string | null;
  onPreviewProposal?: (key: string) => void;
  onCommitProposal?: (key: string) => void;
  onPreviewNext?: () => void;
  guidanceMessage?: string;
  onNextProposals?: () => void;
  sourceFragments?: Fragment[];
  sourceId?: string | null;
  sourceEntries?: SourceEntry[];
  fragments?: Fragment[];
  exportClips?: PhysicalClip[];
  storyPlan?: StoryPlanPreview | null;
  onStoryPlanConfirm?: (plan: StoryPlanPreview) => void;
  onActiveFragmentChange?: (id: string | null) => void;
}

function parseDirectionFromText(text: string): Direction | null {
  const direction: Direction = {};
  const n = text.trim().toLowerCase();

  if (n.includes("감성") || n.includes("감정") || n.includes("부드럽")) {
    direction.tone = "emotional";
  } else if (n.includes("자연") || n.includes("편안") || n.includes("부담없")) {
    direction.tone = "natural";
  }

  if (n.includes("빠르게") || n.includes("속도") || n.includes("템포") || n.includes("짧게")) {
    direction.pace = "fast";
  } else if (n.includes("천천히") || n.includes("여유") || n.includes("느리게")) {
    direction.pace = "slow";
  }

  if (
    n.includes("시장형") ||
    n.includes("임팩트") ||
    n.includes("후킹") ||
    n.includes("강하게")
  ) {
    direction.structure = "hook-priority";
  } else if (
    n.includes("사용자형") ||
    n.includes("자연 흐름") ||
    n.includes("스토리") ||
    n.includes("순서대로")
  ) {
    direction.structure = "chronological";
  }

  if (n.includes("웃긴")) direction.highlight = "웃긴";
  else if (n.includes("설명")) direction.highlight = "설명";

  return Object.keys(direction).length > 0 ? direction : null;
}

const formatMB = (bytes?: number) => {
  if (!bytes) return "0MB";
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
};

const formatDuration = (seconds?: number) => {
  if (!seconds) return "0초";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins > 0) return `${mins}분 ${secs}초`;
  return `${secs}초`;
};

/**
 * [STEP 10-I.5.27-E6-R5] Robust Fragment Source ID Extraction Fallback
 */
function extractSourceIdFromAny(value: any): string {
  if (!value) return "";

  // If input is string, directly match SRC_...
  if (typeof value === "string") {
    const match = value.match(/SRC_[A-Z0-9]+/);
    return match?.[0] || "";
  }

  // If input is object, try direct fields
  const direct =
    value.source_id ||
    value.source_video ||
    value.sourceId ||
    value.source?.source_id ||
    "";

  if (direct) {
    // If field found, still run regex on it just in case it's a decorated ID
    const sid = extractSourceIdFromAny(String(direct));
    if (sid) return sid;
    return String(direct);
  }

  // Fallback to searching candidate ID fields
  const candidates = [
    value.fragment_id,
    value.id,
    value.source_fragment_id,
    value.display_id,
    value.key,
  ];

  for (const candidate of candidates) {
    const sid = extractSourceIdFromAny(candidate);
    if (sid) return sid;
  }

  return "";
}

const CenterPanel: React.FC<CenterPanelProps> = ({
  selectedFragment,
  selectedSource,
  sourceFragments,
  onPreviewNext,
  guidanceMessage,
  onNextProposals,
  onAnalyze,
  onExport,
  onFileSelect,
  onReproposal,
  onConsultation,
  appState,
  analyzeProgress,
  analyzeMessage,
  videoUrl,
  proposals,
  committedProposalId,
  onPreviewProposal,
  onCommitProposal,
  sourceId,
  sourceEntries = [],
  fragments = [],
  exportClips = [],
  storyPlan,
  onStoryPlanConfirm,
  onActiveFragmentChange,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRefA = useRef<HTMLVideoElement>(null);
  const videoRefB = useRef<HTMLVideoElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const consultationTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [activePlayer, setActivePlayer] = useState<"A" | "B" | null>(null);
  const activePlayerRef = useRef<"A" | "B" | null>(null);
  const [consultationInput, setConsultationInput] = useState("");

  const resizeConsultationTextarea = useCallback((textarea?: HTMLTextAreaElement | null) => {
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, []);

  const resetConsultationTextarea = useCallback(() => {
    requestAnimationFrame(() => {
      if (consultationTextareaRef.current) {
        consultationTextareaRef.current.style.height = "auto";
      }
    });
  }, []);

  const handleSubmitConsultation = useCallback(() => {
    const text = consultationInput.trim();
    if (!text) return;
    setConsultationInput("");
    resetConsultationTextarea();
    if (onConsultation) {
      onConsultation(text);
    }
  }, [consultationInput, onConsultation, resetConsultationTextarea]);

  // Auto scroll for consultation chat — always run when messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [storyPlan?.messages?.length]);

  const setActivePlayerSafe = useCallback((player: "A" | "B" | null) => {
    activePlayerRef.current = player;
    setActivePlayer(player);
  }, []);

  const [isPlayingA, setIsPlayingA] = useState(false);
  const [isPlayingB, setIsPlayingB] = useState(false);
  const [chatValue, setChatValue] = useState("");
  const [proposalTimeA, setProposalTimeA] = useState(0);
  const [proposalTimeB, setProposalTimeB] = useState(0);
  const [, setDurationA] = useState(0);
  const [, setDurationB] = useState(0);
  const [, setExportedProgramId] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [renderStatus, setRenderStatus] = useState<string>("");
  const [renderResult, setRenderResult] = useState<{
    file_size?: number;
    duration?: number;
    status?: string;
  } | null>(null);

  const normalizeMediaUrl = useCallback((url?: string | null) => {
    if (!url) return "";
    if (url.startsWith("http://") || url.startsWith("https://")) return url;
    return `${videoService.API_BASE_URL}${url.startsWith("/") ? "" : "/"}${url}`;
  }, []);

  const allSourceFragments = useMemo(
    () =>
      sourceEntries && sourceEntries.length > 0
        ? sourceEntries.flatMap((e) => e.fragments)
        : (sourceFragments ?? []),
    [sourceEntries, sourceFragments]
  );

  const sourceLabelMap = useMemo(() => {
    const map: Record<string, string> = {};
    sourceEntries?.forEach((e) => {
      map[e.source_id] = e.label;
    });
    return map;
  }, [sourceEntries]);

  const labels = useMemo(() => ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"], []);


  const pendingLoadHandlerARef = useRef<(() => void) | null>(null);
  const pendingLoadHandlerBRef = useRef<(() => void) | null>(null);

  const seqFragsARef = useRef<Fragment[]>([]);
  const seqIdxARef = useRef<number>(-1);
  const seqEndARef = useRef<number>(-1);
  const isSeqARef = useRef<boolean>(false);

  const seqFragsBRef = useRef<Fragment[]>([]);
  const seqIdxBRef = useRef<number>(-1);
  const seqEndBRef = useRef<number>(-1);
  const isSeqBRef = useRef<boolean>(false);

  const seqTotalSecARef = useRef<number>(0);
  const seqElapsedSecARef = useRef<number>(0);
  const seqTotalSecBRef = useRef<number>(0);
  const seqElapsedSecBRef = useRef<number>(0);
  const isUserSeekingARef = useRef(false);
  const isUserSeekingBRef = useRef(false);
  const isDraggingProposalSeekARef = useRef(false);
  const isDraggingProposalSeekBRef = useRef(false);

  const [playerSrcA, setPlayerSrcA] = useState<string | null>(null);
  const [playerSrcB, setPlayerSrcB] = useState<string | null>(null);
  const pendingLocalTimeARef = useRef<number | null>(null);
  const pendingLocalTimeBRef = useRef<number | null>(null);

  // [DUAL_PLAY_GUARD] stale event 방지용 세션 ID
  const playSessionARef = useRef<number>(0);
  const playSessionBRef = useRef<number>(0);

  const lastReportedActiveIdRef = useRef<string | null>(null);

  const reportActiveId = useCallback((id: string | null) => {
    if (id !== lastReportedActiveIdRef.current) {
      lastReportedActiveIdRef.current = id;
      onActiveFragmentChange?.(id);
    }
  }, [onActiveFragmentChange]);

  const cleanupPendingLoadHandler = useCallback((player: "A" | "B") => {
    const ref = player === "A" ? videoRefA : videoRefB;
    const pending = player === "A" ? pendingLoadHandlerARef : pendingLoadHandlerBRef;

    if (ref.current && pending.current) {
      ref.current.removeEventListener("loadeddata", pending.current);
      pending.current = null;
    }
  }, []);

  // [DUAL_PLAY_GUARD] 반대편 player 즉시 hard-stop
  const stopOtherPlayer = useCallback((active: "A" | "B") => {
    if (active === "A") {
      // B를 완전 정지
      playSessionBRef.current += 1;          // invalidate stale B events
      pendingLocalTimeBRef.current = null;   // pending seek 무효화
      isSeqBRef.current = false;
      seqIdxBRef.current = -1;
      seqEndBRef.current = -1;
      if (videoRefB.current && !videoRefB.current.paused) {
        videoRefB.current.pause();
        console.log("[DUAL_PLAY_GUARD] B paused by A");
      }
      setIsPlayingB(false);
    } else {
      // A를 완전 정지
      playSessionARef.current += 1;          // invalidate stale A events
      pendingLocalTimeARef.current = null;   // pending seek 무효화
      isSeqARef.current = false;
      seqIdxARef.current = -1;
      seqEndARef.current = -1;
      if (videoRefA.current && !videoRefA.current.paused) {
        videoRefA.current.pause();
        console.log("[DUAL_PLAY_GUARD] A paused by B");
      }
      setIsPlayingA(false);
    }
  }, []);

  const sameVideoSource = useCallback((currentSrc?: string | null, nextSrc?: string | null) => {
    if (!nextSrc) return true;
    if (!currentSrc) return false;

    try {
      const cur = new URL(currentSrc, window.location.origin);
      const next = new URL(nextSrc, window.location.origin);
      return cur.pathname.split("/").pop() === next.pathname.split("/").pop();
    } catch {
      return currentSrc.split("/").pop() === nextSrc.split("/").pop();
    }
  }, []);

  const getVideoUrlForFrag = useCallback(
    (fragId: string): string | null => {
      if (sourceEntries.length === 0) return videoUrl ?? null;

      for (const entry of sourceEntries) {
        if (entry.fragments.some((f) => f.fragment_id === fragId)) {
          return entry.video_url || videoUrl || null;
        }
      }

      return videoUrl ?? null;
    },
    [sourceEntries, videoUrl]
  );

  const getVideoUrlForProposal = useCallback(
    (proposalKey: "A" | "B"): string | null => {
      const p = proposals?.[proposalKey];
      const firstFragId = p?.key_fragments?.[0] ?? p?.sequence?.[0];
      if (!firstFragId) return videoUrl ?? null;
      return getVideoUrlForFrag(firstFragId);
    },
    [proposals, getVideoUrlForFrag, videoUrl]
  );

  // [PROPOSAL_PREVIEW] proposal.preview_url 우선, 없으면 fragment URL fallback
  const previewUrlA: string | null = (proposals?.A as any)?.preview_url
    ? normalizeMediaUrl((proposals.A as any).preview_url)
    : null;
  const previewUrlB: string | null = (proposals?.B as any)?.preview_url
    ? normalizeMediaUrl((proposals.B as any).preview_url)
    : null;

  const playerVideoUrlA = previewUrlA ?? getVideoUrlForProposal("A") ?? videoUrl ?? null;
  const playerVideoUrlB = previewUrlB ?? getVideoUrlForProposal("B") ?? videoUrl ?? null;

  const buildSeqFrags = useCallback(
    (proposalKey: "A" | "B"): Fragment[] => {
      const p = proposals?.[proposalKey];
      if (!p) return [];

      // [STEP 10-K-C1-R39-R1] resolved_aliases가 있으면 우선적으로 사용하여 가드가 적용된 데이터를 재생에 반영
      const resolved = (p as any).resolved_aliases;
      if (Array.isArray(resolved) && resolved.length > 0) {
        return resolved
          .map((item: any) => {
            const fid = item.fragment_id || item.proposal_fragment_id || item.id;
            return allSourceFragments.find((f) => f.fragment_id === fid);
          })
          .filter(Boolean) as Fragment[];
      }

      const ids: string[] = p.key_fragments ?? p.sequence ?? [];
      return ids
        .map((id) => allSourceFragments.find((f) => f.fragment_id === id))
        .filter(Boolean) as Fragment[];
    },
    [proposals, allSourceFragments]
  );


  const playFrag = useCallback(
    (
      player: "A" | "B",
      frag: Fragment,
      endSecRef: React.MutableRefObject<number>,
      seekOffset: number = 0
    ) => {
      const isA = player === "A";
      const ref = isA ? videoRefA : videoRefB;
      if (!ref.current) return;

      // [DUAL_PLAY_GUARD] 다른 플레이어 즉시 정지 + 세션 ID 증가
      stopOtherPlayer(player);
      if (isA) playSessionARef.current += 1;
      else     playSessionBRef.current += 1;
      // mySession: 향후 stale event 검증에 사용 예정
      void (isA ? playSessionARef.current : playSessionBRef.current);

      const fragUrl = getVideoUrlForFrag(frag.fragment_id) ?? videoUrl ?? undefined;
      const startSec = (frag as any).start_sec
        ?? (frag as any).start
        ?? (frag.start_frame ?? 0) / 30;
      const rawEndSec = (frag as any).end_sec
        ?? (frag as any).end
        ?? (frag.end_frame ?? 0) / 30;
      const endSec = rawEndSec > startSec ? rawEndSec : startSec + 1;

      endSecRef.current = endSec;

      console.log("[PLAYFRAG]", {
        player,
        fragment_id: frag?.fragment_id,
        display_id: (frag as any)?.display_id,
        source_video: (frag as any)?.source_video,
        start_frame: frag?.start_frame,
        end_frame: frag?.end_frame,
        duration_frames: (frag as any)?.duration_frames,
        startSec,
        endSec,
        fps_used: 30,
        frag_fps: (frag as any)?.fps ?? (frag as any)?.source_fps ?? (frag as any)?.metadata?.fps ?? "없음",
        currentTime_before_seek: ref?.current?.currentTime ?? "N/A",
        target_seek: startSec
      });

      console.log(
        "[FPS_AUDIT_PLAYFRAG_JSON]\n" +
        JSON.stringify(
          {
            player,
            fragment_id: frag.fragment_id,
            display_id: (frag as any).display_id,
            source_video: (frag as any).source_video,
            start_frame: frag.start_frame,
            end_frame: frag.end_frame,
            calculated_startSec_30fps: startSec,
            calculated_endSec_30fps: endSec,
            duration_frames: ((frag.end_frame ?? 0) - (frag.start_frame ?? 0)),
            duration_sec_30fps: (((frag.end_frame ?? 0) - (frag.start_frame ?? 0)) / 30),
            fragment_duration_field: (frag as any).duration,
            thumbnail_url: (frag as any).thumbnail?.thumbnail_url,
            direct_thumbnail_url: (frag as any).thumbnail_url,
            intelligence_thumb: (frag as any).intelligence?.thumb_url,
            video_url: getVideoUrlForFrag(frag.fragment_id),
          },
          null,
          2
        )
      );

      const doSeekPlay = () => {
        const v = ref.current;
        if (!v) return;
        v.pause();
        v.currentTime = startSec + seekOffset;
        v.play().catch(() => {});
      };

      if (fragUrl && !sameVideoSource(ref.current.currentSrc || ref.current.src, fragUrl)) {
        console.log("[SRC_CHANGE_REQUEST]", {
          player,
          fragment_id: frag?.fragment_id,
          targetTime: startSec + seekOffset,
          fragUrl,
          currentSrc: ref.current?.currentSrc
        });
        // [STEP 10-K-C1-R11] Unify src control via state instead of ref.current.src
        if (isA) {
          pendingLocalTimeARef.current = startSec + seekOffset;
          setPlayerSrcA(fragUrl);
          console.log("[PENDING_SEEK_SET]", {
            player,
            fragment_id: frag?.fragment_id,
            pendingTime: startSec + seekOffset
          });
        } else {
          pendingLocalTimeBRef.current = startSec + seekOffset;
          setPlayerSrcB(fragUrl);
          console.log("[PENDING_SEEK_SET]", {
            player,
            fragment_id: frag?.fragment_id,
            pendingTime: startSec + seekOffset
          });
        }
      } else {
        doSeekPlay();
      }
    },
    [getVideoUrlForFrag, sameVideoSource, videoUrl, stopOtherPlayer]
  );

  const stopSeq = useCallback(
    (player: "A" | "B") => {
      cleanupPendingLoadHandler(player);

      if (player === "A") {
        isSeqARef.current = false;
        seqIdxARef.current = -1;
        seqEndARef.current = -1;
        videoRefA.current?.pause();
        setIsPlayingA(false);
      } else {
        isSeqBRef.current = false;
        seqIdxBRef.current = -1;
        seqEndBRef.current = -1;
        videoRefB.current?.pause();
        setIsPlayingB(false);
      }

      reportActiveId(null);
    },
    [cleanupPendingLoadHandler, reportActiveId]
  );

  const startSeq = useCallback((player: "A" | "B") => {
    const isA = player === "A";
    const ref = isA ? videoRefA : videoRefB;
    const frags = buildSeqFrags(player);
    if (frags.length === 0) return;

    console.log(
      `[SEQ_FRAGS_AUDIT_JSON] ${player}\n` +
      JSON.stringify(
        frags.map((f: any) => ({
          fragment_id: f.fragment_id,
          display_id: f.display_id,
          source_video: f.source_video,
          start_frame: f.start_frame,
          end_frame: f.end_frame,
          duration: f.duration,
          thumb: f.thumbnail?.thumbnail_url,
          direct_thumb: f.thumbnail_url,
          intelligence_thumb: f.intelligence?.thumb_url,
          // [PREVIEW_CLIP_GATE] preview_clip_url이 여기 있어야 STEP 5 진입 가능
          preview_clip_url: f.preview_clip_url ?? null,
        })),
        null,
        2
      )
    );

    let totalSec = 0;
    frags.forEach(f => {
      const s = (f.start_frame ?? 0) / 30;
      const e = (f.end_frame ?? 0) / 30;
      totalSec += Math.max(e - s, 1);
    });

    if (isA) {
      stopSeq("B");
      seqTotalSecARef.current = totalSec;
      seqElapsedSecARef.current = 0;
      seqFragsARef.current = frags;
      seqIdxARef.current = 0;
      isSeqARef.current = true;
      setActivePlayerSafe("A");
      setIsPlayingA(true);
      reportActiveId(frags[0].fragment_id);
      playFrag("A", frags[0], seqEndARef);
    } else {
      stopSeq("A");
      seqTotalSecBRef.current = totalSec;
      seqElapsedSecBRef.current = 0;
      seqFragsBRef.current = frags;
      seqIdxBRef.current = 0;
      isSeqBRef.current = true;
      setActivePlayerSafe("B");
      setIsPlayingB(true);
      reportActiveId(frags[0].fragment_id);
      playFrag("B", frags[0], seqEndBRef);
    }
  }, [buildSeqFrags, playFrag, stopSeq, reportActiveId, setActivePlayerSafe]);
 
  const reSyncSequence = useCallback((player: "A" | "B", time: number) => {
    const frags = player === "A" ? seqFragsARef.current : seqFragsBRef.current;
    const idxRef = player === "A" ? seqIdxARef : seqIdxBRef;
    const endRef = player === "A" ? seqEndARef : seqEndBRef;
    if (!frags.length) return;
    
    const foundIdx = frags.findIndex(f => {
      const s = (f.start_frame ?? 0) / 30;
      const e = (f.end_frame ?? 0) / 30;
      return time >= s && time < e;
    });
    
    if (foundIdx !== -1) {
      idxRef.current = foundIdx;
      const f = frags[foundIdx];
      endRef.current = (f.end_frame ?? 0) / 30;
      reportActiveId(f.fragment_id);
      
      let newElapsed = 0;
      for(let i=0; i < foundIdx; i++) {
        const pf = frags[i];
        const s = (pf.start_frame ?? 0) / 30;
        const e = (pf.end_frame ?? 0) / 30;
        newElapsed += Math.max(e - s, 1);
      }
      if (player === "A") seqElapsedSecARef.current = newElapsed;
      else seqElapsedSecBRef.current = newElapsed;
    }
  }, [reportActiveId]);

  const resolveProposalTime = useCallback((frags: Fragment[], targetGlobalTime: number) => {
    let acc = 0;
    for (let i = 0; i < frags.length; i++) {
      const f = frags[i];
      const s = (f.start_frame ?? 0) / 30;
      const e = (f.end_frame ?? 0) / 30;
      const dur = Math.max(e - s, 1);
      const next = acc + dur;
      if (targetGlobalTime < next) {
        return {
          index: i,
          offset: targetGlobalTime - acc,
          globalTime: targetGlobalTime,
          prevAccumulated: acc
        };
      }
      acc = next;
    }
    
    // [STEP 10-K-C1-R11] Clamp to the end of last fragment instead of resetting to 0
    const lastIdx = Math.max(0, frags.length - 1);
    if (frags.length > 0) {
      const lf = frags[lastIdx];
      const ls = (lf.start_frame ?? 0) / 30;
      const le = (lf.end_frame ?? 0) / 30;
      const ldur = Math.max(le - ls, 1);
      return {
        index: lastIdx,
        offset: ldur,
        globalTime: targetGlobalTime,
        prevAccumulated: acc - ldur
      };
    }
    return { index: 0, offset: 0, globalTime: 0, prevAccumulated: 0 };
  }, []);

  const seekProposal = useCallback((player: "A" | "B", targetGlobalTime: number) => {
    const isA = player === "A";
    const frags = isA ? seqFragsARef.current : seqFragsBRef.current;
    if (frags.length === 0) return;

    const resolved = resolveProposalTime(frags, targetGlobalTime);
    const video = isA ? videoRefA : videoRefB;
    const isPlaying = isA ? isPlayingA : isPlayingB;

    if (!video.current) return;

    // Update sequence refs
    if (isA) {
      seqIdxARef.current = resolved.index;
      seqElapsedSecARef.current = resolved.prevAccumulated;
      setProposalTimeA(targetGlobalTime);
    } else {
      seqIdxBRef.current = resolved.index;
      seqElapsedSecBRef.current = resolved.prevAccumulated;
      setProposalTimeB(targetGlobalTime);
    }

    reportActiveId(frags[resolved.index].fragment_id);

    // Fragment change might require src change
    const targetFrag = frags[resolved.index];
    const targetUrl = getVideoUrlForFrag(targetFrag.fragment_id) ?? videoUrl ?? undefined;
    
    if (targetUrl && !sameVideoSource(video.current.currentSrc || video.current.src, targetUrl)) {
      playFrag(player, targetFrag, isA ? seqEndARef : seqEndBRef, resolved.offset);
    } else {
      const startSec = (targetFrag.start_frame ?? 0) / 30;
      video.current.currentTime = startSec + resolved.offset;
      if (isPlaying) video.current.play().catch(() => {});
    }
  }, [resolveProposalTime, isPlayingA, isPlayingB, getVideoUrlForFrag, videoUrl, sameVideoSource, playFrag, reportActiveId]);



  useEffect(() => {
    if (!selectedFragment) return;

    if (isSeqARef.current) stopSeq("A");
    if (isSeqBRef.current) stopSeq("B");

    const player = activePlayerRef.current === "B" ? "B" : "A";
    const endRef = player === "B" ? seqEndBRef : seqEndARef;

    setActivePlayerSafe(player);
    reportActiveId(selectedFragment.fragment_id);
    playFrag(player, selectedFragment, endRef);

    if (player === "B") {
      setIsPlayingB(true);
    } else {
      setIsPlayingA(true);
    }
  }, [selectedFragment, playFrag, setActivePlayerSafe, stopSeq]);

  const handleUpload = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files);
      console.log(`[CenterPanel] Files selected:`, files.map(f => f.name));
      
      setExportUrl(null);
      setExportError(null);

      if (onFileSelect) onFileSelect(files[0]);
      if (onAnalyze) {
        const success = await onAnalyze(files[0], files.slice(1));
        if (!success) {
          console.warn("[CenterPanel] Analysis failed or was cancelled.");
        }
      }
    }
  };

  const handleSendFull = useCallback(async () => {
    if (!chatValue.trim()) return;

    const raw = chatValue.trim();
    const cmd = raw.toLowerCase();
    setChatValue("");

    if (cmd === "start") {
      if (onAnalyze) await onAnalyze();
      return;
    }

    const parsedDirection = parseDirectionFromText(raw);
    if (parsedDirection) {
      onReproposal?.(parsedDirection);
    } else {
      // [STEP 10-I.5.28-E9-R2] Fallback to raw text for narrative intent
      onReproposal?.(raw as any);
    }
  }, [chatValue, onAnalyze, onReproposal]);

  const getProposalPoster = useCallback(
    (key: "A" | "B") => {
      const p = proposals?.[key];
      const firstFragId = p?.key_fragments?.[0] ?? p?.sequence?.[0];
      if (!firstFragId) return undefined;

      const frag = allSourceFragments.find((f: any) => f.fragment_id === firstFragId);
      if (!frag) return undefined;

      // 1차: thumbnail.thumbnail_url
      if (frag.thumbnail?.thumbnail_url) return frag.thumbnail.thumbnail_url;

      // 2차: 직접 thumbnail_url 필드 (있는 경우)
      if ((frag as any).thumbnail_url) return (frag as any).thumbnail_url;

      // 3차: 없으면 undefined — 브라우저 첫 프레임 자동 표시
      return undefined;
    },
    [proposals, allSourceFragments]
  );

  const handleProposalPreview = useCallback(
    (key: string) => {
      onPreviewProposal?.(key);
    },
    [onPreviewProposal]
  );

  const handleProposalCommit = useCallback(
    (key: string) => {
      if (key !== committedProposalId) {
        setExportUrl(null);
        setExportError(null);
      }

      handleProposalPreview(key);
      onCommitProposal?.(key);
    },
    [committedProposalId, handleProposalPreview, onCommitProposal]
  );

  const handleExportClick = async () => {
    // [STEP 10-I.2] Export 전 유효성 검사 강화 (Physical EDL 정합성 확인)
    if (!committedProposalId || !validateExportClips(exportClips)) {
      setExportError("확정된 조각이 없습니다. A안 또는 B안을 먼저 확정하세요.");
      return;
    }

    setIsExporting(true);
    setExportError(null);
    setExportUrl(null);
    setRenderResult(null);
    setRenderStatus("ExportInput 생성 중...");

    try {
      const proposal = proposals?.[committedProposalId];
      const backendId = proposal?.proposal_id || proposal?.id || committedProposalId;

      // [STEP 10-I.2] fragment_id가 아닌 Physical EDL(exportClips)을 전송
      const exportInputRes = await fetch(`${videoService.API_BASE_URL}/export-input/${backendId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clips: exportClips })
      });
      if (!exportInputRes.ok) throw new Error(`ExportInput 생성 실패 (${exportInputRes.status})`);
      const exportInputData = await exportInputRes.json();

      const exportInputId = exportInputData.export_input_id || exportInputData.export_id || exportInputData.id;
      if (!exportInputId) throw new Error("응답에서 ExportInput ID를 찾을 수 없습니다.");

      setRenderStatus("Render 실행 중...");

      // [STEP 9] 2. Render 실행 (POST /render/{export_input_id})
      const renderRes = await fetch(`${videoService.API_BASE_URL}/render/${exportInputId}`, {
        method: "POST"
      });
      if (!renderRes.ok) throw new Error(`Render 시작 실패 (${renderRes.status})`);
      const renderData = await renderRes.json();

      if (!renderData.success) {
        throw new Error(renderData.message || "Render 엔진 실행 중 대기 혹은 실패");
      }

      // [STEP 9] 3. Render 결과 조회 (GET /render-result/{export_input_id})
      const resultRes = await fetch(`${videoService.API_BASE_URL}/render-result/${exportInputId}`);
      if (!resultRes.ok) throw new Error(`Render 결과 조회 실패 (${resultRes.status})`);
      const resultData = await resultRes.json();

      // [STEP 9] 결과 상태 매핑
      if (resultData.status === "RENDER_SUCCESS") {
        setRenderStatus("완료");
        setExportUrl(resultData.output_url);
        setRenderResult({
          file_size: resultData.file_size,
          duration: resultData.duration,
          status: resultData.status
        });
      } else {
        throw new Error(`렌더링 상태 확인 필요: ${resultData.status}`);
      }

    } catch (e: any) {
      console.error("[STEP 9] Export Flow Error:", e);
      setRenderStatus("실패");
      setExportError(e.message || "서버 연결 오류가 발생했습니다.");
    } finally {
      setIsExporting(false);
    }
  };

  const renderContent = () => {
    if (appState === "empty") {
      return (
        <div className="flex-1 flex items-center justify-center p-6 text-center">
          <div
            className="w-full max-w-[320px] border-2 border-dashed border-primary/20 rounded-3xl p-12 flex flex-col items-center gap-5 hover:border-primary/40 hover:bg-primary/5 transition-all cursor-pointer group shadow-2xl shadow-primary/5"
            onClick={handleUpload}
          >
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center group-hover:scale-110 group-hover:rotate-3 transition-all duration-300">
              <Upload size={24} className="text-primary" />
            </div>

            <div className="space-y-2">
              <h2 className="text-[15px] font-bold text-foreground">새 프로젝트 시작</h2>
              <p className="text-[12px] text-muted-foreground/60 leading-relaxed">
                원본 영상들을 이곳에 끌어다 놓으세요.
                <br />
                AI가 인지 분할하고 편집 제안을 생성합니다.
              </p>
            </div>

            <button
              className="mt-4 px-8 py-2.5 rounded-xl bg-primary text-primary-foreground text-[12px] font-bold hover:opacity-90 hover:translate-y-[-2px] transition-all shadow-xl shadow-primary/20"
              onClick={(e) => {
                e.stopPropagation();
                handleUpload();
              }}
            >
              파일 업로드
            </button>

            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              multiple
              className="hidden"
              onChange={handleFileChange}
            />
          </div>
        </div>
      );
    }

    if (appState === "analyzing") {
      return (
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="flex flex-col items-center gap-6 w-full max-w-[280px]">
            <div className="relative">
              <div className="w-16 h-16 rounded-2xl bg-secondary/60 flex items-center justify-center animate-pulse">
                <Loader2 size={24} className="text-primary animate-spin" />
              </div>
              <div className="absolute -top-1 -right-1 w-4 h-4 bg-primary rounded-full animate-ping opacity-20" />
            </div>

            <div className="text-center space-y-1.5">
              <p className="text-[14px] font-bold text-foreground/90 tracking-tight">
                AI 인지 분석 시퀀스 가동
              </p>
              <p className="text-[11px] text-muted-foreground/60">
                {analyzeMessage || "장면의 맥락과 감정 선을 분석하는 중입니다."}
              </p>
            </div>

            <div className="w-full h-1.5 bg-secondary/40 rounded-full overflow-hidden shadow-inner">
              <div
                className="h-full bg-primary rounded-full transition-all duration-500 ease-out shadow-[0_0_10px_rgba(var(--primary),0.5)]"
                style={{ width: `${Math.min(analyzeProgress, 100)}%` }}
              />
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="flex-1 w-full px-4 pt-4 flex flex-col items-center space-y-4 overflow-y-auto no-scrollbar pb-20">
        
        {/* [STEP 10-I.5.28-E9-R2-R3-R2] ChatGPT Form Narrative Consultation — always visible */}
        {storyPlan && (storyPlan.messages || []).length > 0 && (
          <div className="w-full max-w-[800px] flex flex-col gap-6 py-8 animate-in fade-in duration-700">

            {/* Message History — persists even after confirmed */}
            <div className="flex flex-col gap-8">
              {(storyPlan.messages || []).map((msg) => (
                <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"} animate-in fade-in slide-in-from-bottom-2 duration-500`}>
                  <div className={`flex gap-4 max-w-[85%] ${msg.sender === "user" ? "flex-row-reverse" : "flex-row"}`}>
                    <div className={`w-8 h-8 rounded-lg flex-shrink-0 flex items-center justify-center mt-1 ${msg.sender === "ai" ? "bg-primary/10 text-primary" : "bg-secondary/40 text-muted-foreground"}`}>
                      {msg.sender === "ai" ? <BookOpen size={16} /> : <List size={16} />}
                    </div>
                    <div className={`flex flex-col gap-1.5 ${msg.sender === "user" ? "items-end" : "items-start"}`}>
                      <div className={`px-5 py-3.5 rounded-2xl leading-relaxed text-[14px] whitespace-pre-wrap break-words ${
                        msg.sender === "user"
                          ? "bg-[#161618] border border-white/5 text-foreground/90 rounded-tr-none"
                          : "bg-secondary/10 border border-border/5 text-foreground/90 rounded-tl-none"
                      }`}>
                        {msg.isInterpreting && (
                          <div className="flex items-center gap-2 mb-2 text-primary/60">
                            <Loader2 size={14} className="animate-spin" />
                            <span className="text-[11px] font-medium animate-pulse">AI 해석 중...</span>
                          </div>
                        )}
                        {msg.text}
                      </div>
                      <span className="text-[10px] text-muted-foreground/40 px-1">{new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* Suggestion Chips — hidden after confirmed */}
            {storyPlan.consultation_status !== "confirmed" && (
              <div className="flex flex-col gap-3 mt-4 border-t border-white/5 pt-6">
                <p className="text-[11px] font-bold text-muted-foreground/40 uppercase tracking-widest px-1">의견 제안</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="px-4 py-2 bg-secondary/30 text-muted-foreground border border-white/5 rounded-full text-[12px] font-medium hover:bg-secondary/50 hover:text-foreground transition-all"
                    onClick={() => onConsultation?.("이대로 제안해줘")}
                  >
                    이대로 제안해줘
                  </button>
                  <button
                    className="px-4 py-2 bg-secondary/30 text-muted-foreground border border-white/5 rounded-full text-[12px] font-medium hover:bg-secondary/50 hover:text-foreground transition-all"
                    onClick={() => onConsultation?.("사람 중심으로")}
                  >
                    사람 중심으로
                  </button>
                  <button
                    className="px-4 py-2 bg-secondary/30 text-muted-foreground border border-white/5 rounded-full text-[12px] font-medium hover:bg-secondary/50 hover:text-foreground transition-all"
                    onClick={() => onConsultation?.("풍경은 줄여줘")}
                  >
                    풍경은 줄이고
                  </button>
                  <button
                    className="px-4 py-2 bg-secondary/30 text-muted-foreground border border-white/5 rounded-full text-[12px] font-medium hover:bg-secondary/50 hover:text-foreground transition-all"
                    onClick={() => onConsultation?.("더 빠르게")}
                  >
                    더 빠르게
                  </button>
                  <button
                    className="px-4 py-2 bg-secondary/30 text-muted-foreground border border-white/5 rounded-full text-[12px] font-medium hover:bg-secondary/50 hover:text-foreground transition-all"
                    onClick={() => onConsultation?.("여러 영상 골고루")}
                  >
                    여러 영상 골고루
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        
        {/* [STEP 10-I.5.28-E9-R1-R1] Story Direction Adjustment Bar (Only after confirmed) */}
        {storyPlan && storyPlan.consultation_status === "confirmed" && (
          <div className="w-full max-w-[800px] bg-secondary/10 border border-border/10 rounded-xl px-4 py-2.5 shadow-sm">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 overflow-hidden">
                <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
                  <BookOpen size={14} className="text-primary" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">이야기 방향</span>
                  <p className="text-[11px] text-foreground font-medium truncate">
                    {storyPlan.detected_theme.replace("프로젝트", "")} 중심 · A안 빠르게 · B안 자연스럽게
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5 flex-shrink-0">
                {storyPlan.direction_options.map((opt) => (
                  <button
                    key={opt.id}
                    className={`px-3 py-1 rounded-full text-[10px] font-bold transition-all ${
                      storyPlan.selected_direction === opt.id
                        ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/20'
                        : 'bg-secondary/40 text-muted-foreground hover:text-foreground hover:bg-secondary/60'
                    }`}
                    onClick={() => {
                        const status = opt.id === "market_highlight" || opt.id === "user_memory" ? "confirmed" : "adjusted";
                        onStoryPlanConfirm?.({ ...storyPlan, selected_direction: opt.id, confirmation_status: status });
                    }}
                  >
                    {opt.label.replace("이대로 제안", "이대로").replace("시장형 ", "").replace("사용자친화형 ", "")}
                  </button>
                ))}
              </div>
            </div>

            {storyPlan.confirmation_status === "adjusted" && (
              <div className="mt-2 flex items-center gap-2 px-3 py-1 bg-amber-500/5 border border-amber-500/10 rounded-lg">
                <AlertCircle size={12} className="text-amber-500/80" />
                <p className="text-[9px] text-amber-200/60 font-medium">선택한 방향은 다음 재제안 단계에서 반영됩니다.</p>
              </div>
            )}
          </div>
        )}

        {/* [STEP 10-I.5.28-E9-R2] Proposals Grid (Visible only after confirmation or proposals exist) */}
        {(storyPlan?.consultation_status === "confirmed" || !!proposals) && (
          <>
          <div className="grid grid-cols-2 gap-4 w-full">
          <div className="flex flex-col items-center space-y-4">
            <div
              className="relative w-full aspect-[16/8] rounded-2xl bg-black overflow-hidden border border-white/8 cursor-pointer group/player"
              onClick={() => {
                if (!videoRefA.current) return;

                if (previewUrlA) {
                  // [PROPOSAL_PREVIEW_PLAY] preview mp4 직접 재생 — seek 없음
                  stopOtherPlayer("A");
                  setActivePlayerSafe("A");
                  // [PREVIEW_MODE_GUARD] fragment seq 상태 초기화
                  seqEndARef.current = -1;
                  isSeqARef.current = false;
                  seqIdxARef.current = 0;
                  pendingLocalTimeARef.current = null;
                  const v = videoRefA.current;
                  if (v.paused || v.ended) {
                    if (!sameVideoSource(v.currentSrc || v.src, previewUrlA)) {
                      v.src = previewUrlA;
                      v.load();
                    }
                    v.currentTime = 0;
                    v.play().catch(() => {});
                    console.log("[PROPOSAL_PREVIEW_PLAY]", { variant: "A", preview_url: previewUrlA, currentTime: 0 });
                  } else {
                    v.pause();
                  }
                  handleProposalPreview("A");
                  return;
                }

                // fallback: preview_url 없을 때만 fragment 시퀀스 재생
                console.warn("[PROPOSAL_PREVIEW_MISSING]", { variant: "A", proposal_id: (proposals?.A as any)?.proposal_id });
                if (!isSeqARef.current || videoRefA.current.paused) {
                  startSeq("A");
                  handleProposalPreview("A");
                } else {
                  stopSeq("A");
                }
              }}
            >
              {(playerVideoUrlA ?? videoUrl) ? (
                <>
                  <video
                    ref={videoRefA}
                    src={playerSrcA ?? playerVideoUrlA ?? videoUrl ?? undefined}
                    poster={getProposalPoster("A")}
                    className="w-full h-full object-contain bg-black"
                    onPlay={() => {
                      // [DUAL_PLAY_GUARD] A가 play되면 B 즉시 정지
                      stopOtherPlayer("A");
                      setActivePlayerSafe("A");
                      setIsPlayingA(true);
                    }}
                    onPause={() => setIsPlayingA(false)}
                    onTimeUpdate={(e) => {
                      // [DUAL_PLAY_GUARD] inactive player는 advance 차단
                      if (activePlayerRef.current !== "A") return;
                      if (isDraggingProposalSeekARef.current) return;
                      // [PREVIEW_MODE_GUARD] preview_url 재생 중 fragment seq 개입 차단
                      if (previewUrlA) {
                        setProposalTimeA(e.currentTarget.currentTime);
                        return;
                      }
                      const v = e.currentTarget;
                      if (isSeqARef.current && seqTotalSecARef.current > 0) {
                        const fragStart = (seqFragsARef.current[seqIdxARef.current]?.start_frame ?? 0) / 30;
                        const global = seqElapsedSecARef.current + Math.max(0, v.currentTime - fragStart);
                        setProposalTimeA(global);
                      }

                      const near =
                        seqEndARef.current > 0 && !v.seeking && v.currentTime >= seqEndARef.current;
                      if (!near) return;

                      if (near) {
                        console.log("[NEAR_TRUE_A]", {
                          currentTime: v.currentTime,
                          seqEndRef: seqEndARef.current,
                          seqIdx: seqIdxARef.current,
                          isSeq: isSeqARef.current
                        });
                      }

                      if (isSeqARef.current) {
                        const nextIdx = seqIdxARef.current + 1;
                        const frags = seqFragsARef.current;

                        if (nextIdx < frags.length) {
                          const curFrag = frags[seqIdxARef.current];
                          const cs = (curFrag.start_frame ?? 0) / 30;
                          const ce = (curFrag.end_frame ?? 0) / 30;
                          
                          seqElapsedSecARef.current += Math.max(ce - cs, 1);
                          seqIdxARef.current = nextIdx;
                          setProposalTimeA(seqElapsedSecARef.current);
                          reportActiveId(frags[nextIdx].fragment_id);
                          playFrag("A", frags[nextIdx], seqEndARef);
                        } else {
                          isSeqARef.current = false;
                          seqIdxARef.current = -1;
                          seqEndARef.current = -1;
                          v.pause();
                          setIsPlayingA(false);
                          reportActiveId(null);
                        }
                      } else {
                        v.pause();
                        setIsPlayingA(false);
                      }
                    }}
                    onLoadedMetadata={(e) => {
                      setDurationA(e.currentTarget.duration);
                      // [DUAL_PLAY_GUARD] inactive player는 seek+play 차단
                      if (activePlayerRef.current !== "A") {
                        console.log("[DUAL_PLAY_GUARD] onLoadedMetadata A skipped (inactive)");
                        pendingLocalTimeARef.current = null;
                        return;
                      }
                      const pending = pendingLocalTimeARef.current;
                      if (pending !== null) {
                        console.log("[LOADED_METADATA_PENDING]", {
                          player: "A",
                          pending,
                          currentTimeBeforeSet: e.currentTarget.currentTime,
                          duration: e.currentTarget.duration
                        });
                        pendingLocalTimeARef.current = null;
                        const tgt = e.currentTarget;
                        const target = pending;
                        let seekDone = false;

                        const onPendingSeeked = () => {
                          if (seekDone) return;
                          seekDone = true;
                          tgt.removeEventListener("seeked", onPendingSeeked);
                          if (Math.abs(tgt.currentTime - target) <= 0.5) {
                            console.log("[PENDING_SEEKED_PLAY]", { player: "A", currentTime: tgt.currentTime, target });
                            tgt.play().catch(() => {});
                          } else {
                            console.warn("[PENDING_SEEK_MISMATCH]", { player: "A", currentTime: tgt.currentTime, target });
                          }
                        };

                        tgt.addEventListener("seeked", onPendingSeeked);
                        tgt.currentTime = target;

                        setTimeout(() => {
                          if (seekDone) return;
                          seekDone = true;
                          tgt.removeEventListener("seeked", onPendingSeeked);
                          if (Math.abs(tgt.currentTime - target) <= 0.5) {
                            tgt.play().catch(() => {});
                          } else {
                            console.warn("[PENDING_SEEK_TIMEOUT_ABORT]", { player: "A", currentTime: tgt.currentTime, target });
                          }
                        }, 300);
                      }
                    }}
                    preload="auto"
                    playsInline
                  />

                  {!isPlayingA && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/15 pointer-events-none group-hover/player:bg-black/5 transition-all">
                      <Play
                        size={40}
                        className="text-white fill-white opacity-40 drop-shadow-2xl transition-all group-hover/player:scale-110 group-hover/player:opacity-60"
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-col items-center justify-center h-full opacity-10">
                  <Play size={40} className="text-muted-foreground" />
                </div>
              )}

              <div className="absolute top-4 left-6 pointer-events-none">
                <span className="text-[10px] font-black tracking-widest text-primary/60 uppercase">
                  Draft A
                </span>
              </div>

              <div 
                className="absolute bottom-0 left-0 right-0 h-6 z-40 flex items-end px-2 pb-1"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  type="range"
                  min={0}
                  max={previewUrlA ? (videoRefA.current?.duration || 100) : (seqTotalSecARef.current || 100)}
                  step={0.01}
                  value={proposalTimeA}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    isDraggingProposalSeekARef.current = true;
                  }}
                  onChange={(e) => {
                    e.stopPropagation();
                    setProposalTimeA(Number(e.target.value));
                  }}
                  onPointerUp={(e) => {
                    e.stopPropagation();
                    isDraggingProposalSeekARef.current = false;
                    // [PREVIEW_MODE_GUARD] preview mode에서는 video.currentTime만 변경
                    if (previewUrlA && videoRefA.current) {
                      videoRefA.current.currentTime = Number(e.currentTarget.value);
                      setProposalTimeA(Number(e.currentTarget.value));
                      return;
                    }
                    seekProposal("A", Number(e.currentTarget.value));
                  }}
                  className="proposal-seekbar w-full h-1 bg-white/20 accent-primary cursor-pointer appearance-none hover:h-1.5 transition-all rounded-full"
                  style={{
                    background: `linear-gradient(to right, hsl(var(--primary)) 0%, hsl(var(--primary)) ${(proposalTimeA / (previewUrlA ? (videoRefA.current?.duration || 1) : (seqTotalSecARef.current || 1))) * 100}%, rgba(255,255,255,0.1) ${(proposalTimeA / (previewUrlA ? (videoRefA.current?.duration || 1) : (seqTotalSecARef.current || 1))) * 100}%, rgba(255,255,255,0.1) 100%)`
                  }}
                />
              </div>
            </div>

            <button
              onClick={() => handleProposalCommit("A")}
              disabled={!proposals || !proposals.A}
              className={`text-[14px] font-black tracking-[0.5em] transition-all uppercase group relative py-2 ${committedProposalId === "A"
                ? "text-primary"
                : !proposals || !proposals.A
                  ? "text-muted-foreground/10 cursor-not-allowed"
                  : "text-foreground/60 hover:text-primary"
                }`}
            >
              {committedProposalId === "A" ? "✓ A안 확정됨" : "A안 선택"}
              <div
                className={`absolute bottom-0 left-0 h-[2px] bg-primary transition-all duration-300 ${committedProposalId === "A" ? "w-full" : "w-0 group-hover:w-full"
                  }`}
              />
            </button>
          </div>

          <div className="flex flex-col items-center space-y-4">
            <div
              className="relative w-full aspect-[16/8] rounded-2xl bg-black overflow-hidden border border-white/8 cursor-pointer group/player"
              onClick={() => {
                if (!videoRefB.current) return;

                if (previewUrlB) {
                  // [PROPOSAL_PREVIEW_PLAY] preview mp4 직접 재생 — seek 없음
                  stopOtherPlayer("B");
                  setActivePlayerSafe("B");
                  // [PREVIEW_MODE_GUARD] fragment seq 상태 초기화
                  seqEndBRef.current = -1;
                  isSeqBRef.current = false;
                  seqIdxBRef.current = 0;
                  pendingLocalTimeBRef.current = null;
                  const v = videoRefB.current;
                  if (v.paused || v.ended) {
                    if (!sameVideoSource(v.currentSrc || v.src, previewUrlB)) {
                      v.src = previewUrlB;
                      v.load();
                    }
                    v.currentTime = 0;
                    v.play().catch(() => {});
                    console.log("[PROPOSAL_PREVIEW_PLAY]", { variant: "B", preview_url: previewUrlB, currentTime: 0 });
                  } else {
                    v.pause();
                  }
                  handleProposalPreview("B");
                  return;
                }

                // fallback: preview_url 없을 때만 fragment 시퀀스 재생
                console.warn("[PROPOSAL_PREVIEW_MISSING]", { variant: "B", proposal_id: (proposals?.B as any)?.proposal_id });
                if (!isSeqBRef.current || videoRefB.current.paused) {
                  startSeq("B");
                  handleProposalPreview("B");
                } else {
                  stopSeq("B");
                }
              }}
            >
              {(playerVideoUrlB ?? videoUrl) ? (
                <>
                  <video
                    ref={videoRefB}
                    src={playerSrcB ?? playerVideoUrlB ?? videoUrl ?? undefined}
                    poster={getProposalPoster("B")}
                    className="w-full h-full object-contain bg-black"
                    onPlay={() => {
                      // [DUAL_PLAY_GUARD] B가 play되면 A 즉시 정지
                      stopOtherPlayer("B");
                      setActivePlayerSafe("B");
                      setIsPlayingB(true);
                    }}
                    onPause={() => setIsPlayingB(false)}
                    onTimeUpdate={(e) => {
                      // [DUAL_PLAY_GUARD] inactive player는 advance 차단
                      if (activePlayerRef.current !== "B") return;
                      if (isDraggingProposalSeekBRef.current) return;
                      // [PREVIEW_MODE_GUARD] preview_url 재생 중 fragment seq 개입 차단
                      if (previewUrlB) {
                        setProposalTimeB(e.currentTarget.currentTime);
                        return;
                      }
                      const v = e.currentTarget;
                      if (isSeqBRef.current && seqTotalSecBRef.current > 0) {
                        const fragStart = (seqFragsBRef.current[seqIdxBRef.current]?.start_frame ?? 0) / 30;
                        const global = seqElapsedSecBRef.current + Math.max(0, v.currentTime - fragStart);
                        setProposalTimeB(global);
                      }

                      const near =
                        seqEndBRef.current > 0 && !v.seeking && v.currentTime >= seqEndBRef.current;
                      if (!near) return;

                      if (near) {
                        console.log("[NEAR_TRUE_B]", {
                          currentTime: v.currentTime,
                          seqEndRef: seqEndBRef.current,
                          seqIdx: seqIdxBRef.current,
                          isSeq: isSeqBRef.current
                        });
                      }

                      if (isSeqBRef.current) {
                        const nextIdx = seqIdxBRef.current + 1;
                        const frags = seqFragsBRef.current;

                        if (nextIdx < frags.length) {
                          const curFrag = frags[seqIdxBRef.current];
                          const cs = (curFrag.start_frame ?? 0) / 30;
                          const ce = (curFrag.end_frame ?? 0) / 30;

                          seqElapsedSecBRef.current += Math.max(ce - cs, 1);
                          seqIdxBRef.current = nextIdx;
                          setProposalTimeB(seqElapsedSecBRef.current);
                          reportActiveId(frags[nextIdx].fragment_id);
                          playFrag("B", frags[nextIdx], seqEndBRef);
                        } else {
                          isSeqBRef.current = false;
                          seqIdxBRef.current = -1;
                          seqEndBRef.current = -1;
                          v.pause();
                          setIsPlayingB(false);
                          reportActiveId(null);
                        }
                      } else {
                        v.pause();
                        setIsPlayingB(false);
                      }
                    }}
                    onLoadedMetadata={(e) => {
                      setDurationB(e.currentTarget.duration);
                      // [DUAL_PLAY_GUARD] inactive player는 seek+play 차단
                      if (activePlayerRef.current !== "B") {
                        console.log("[DUAL_PLAY_GUARD] onLoadedMetadata B skipped (inactive)");
                        pendingLocalTimeBRef.current = null;
                        return;
                      }
                      const pending = pendingLocalTimeBRef.current;
                      if (pending !== null) {
                        console.log("[LOADED_METADATA_PENDING]", {
                          player: "B",
                          pending,
                          currentTimeBeforeSet: e.currentTarget.currentTime,
                          duration: e.currentTarget.duration
                        });
                        pendingLocalTimeBRef.current = null;
                        const tgt = e.currentTarget;
                        const target = pending;
                        let seekDone = false;

                        const onPendingSeeked = () => {
                          if (seekDone) return;
                          seekDone = true;
                          tgt.removeEventListener("seeked", onPendingSeeked);
                          if (Math.abs(tgt.currentTime - target) <= 0.5) {
                            console.log("[PENDING_SEEKED_PLAY]", { player: "B", currentTime: tgt.currentTime, target });
                            tgt.play().catch(() => {});
                          } else {
                            console.warn("[PENDING_SEEK_MISMATCH]", { player: "B", currentTime: tgt.currentTime, target });
                          }
                        };

                        tgt.addEventListener("seeked", onPendingSeeked);
                        tgt.currentTime = target;

                        setTimeout(() => {
                          if (seekDone) return;
                          seekDone = true;
                          tgt.removeEventListener("seeked", onPendingSeeked);
                          if (Math.abs(tgt.currentTime - target) <= 0.5) {
                            tgt.play().catch(() => {});
                          } else {
                            console.warn("[PENDING_SEEK_TIMEOUT_ABORT]", { player: "B", currentTime: tgt.currentTime, target });
                          }
                        }, 300);
                      }
                    }}
                    preload="auto"
                    playsInline
                  />

                  {!isPlayingB && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/15 pointer-events-none group-hover/player:bg-black/5 transition-all">
                      <Play
                        size={40}
                        className="text-white fill-white opacity-40 drop-shadow-2xl transition-all group-hover/player:scale-110 group-hover/player:opacity-60"
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-col items-center justify-center h-full opacity-10">
                  <Play size={40} className="text-muted-foreground" />
                </div>
              )}

              <div className="absolute top-4 left-6 pointer-events-none">
                <span className="text-[10px] font-black tracking-widest text-ccut-indigo/60 uppercase">
                  Draft B
                </span>
              </div>

              <div 
                className="absolute bottom-0 left-0 right-0 h-6 z-40 flex items-end px-2 pb-1"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  type="range"
                  min={0}
                  max={previewUrlB ? (videoRefB.current?.duration || 100) : (seqTotalSecBRef.current || 100)}
                  step={0.01}
                  value={proposalTimeB}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    isDraggingProposalSeekBRef.current = true;
                  }}
                  onChange={(e) => {
                    e.stopPropagation();
                    setProposalTimeB(Number(e.target.value));
                  }}
                  onPointerUp={(e) => {
                    e.stopPropagation();
                    isDraggingProposalSeekBRef.current = false;
                    // [PREVIEW_MODE_GUARD] preview mode에서는 video.currentTime만 변경
                    if (previewUrlB && videoRefB.current) {
                      videoRefB.current.currentTime = Number(e.currentTarget.value);
                      setProposalTimeB(Number(e.currentTarget.value));
                      return;
                    }
                    seekProposal("B", Number(e.currentTarget.value));
                  }}
                  className="proposal-seekbar w-full h-1 bg-white/20 accent-ccut-indigo cursor-pointer appearance-none hover:h-1.5 transition-all rounded-full"
                  style={{
                    background: `linear-gradient(to right, #6366f1 0%, #6366f1 ${(proposalTimeB / (previewUrlB ? (videoRefB.current?.duration || 1) : (seqTotalSecBRef.current || 1))) * 100}%, rgba(255,255,255,0.1) ${(proposalTimeB / (previewUrlB ? (videoRefB.current?.duration || 1) : (seqTotalSecBRef.current || 1))) * 100}%, rgba(255,255,255,0.1) 100%)`
                  }}
                />
              </div>
            </div>

            <button
              onClick={() => handleProposalCommit("B")}
              disabled={!proposals || !proposals.B}
              className={`text-[14px] font-black tracking-[0.5em] transition-all uppercase group relative py-2 ${committedProposalId === "B"
                ? "text-ccut-indigo"
                : !proposals || !proposals.B
                  ? "text-muted-foreground/10 cursor-not-allowed"
                  : "text-foreground/60 hover:text-ccut-indigo"
                }`}
            >
              {committedProposalId === "B" ? "✓ B안 확정됨" : "B안 선택"}
              <div
                className={`absolute bottom-0 left-0 h-[2px] bg-ccut-indigo transition-all duration-300 ${committedProposalId === "B" ? "w-full" : "w-0 group-hover:w-full"
                  }`}
              />
            </button>
          </div>
        </div>
      </>
    )}

      <div className="w-full grid grid-cols-2 gap-4">
          {proposals ? (
            Object.entries(proposals).map(([key, p]: [string, any]) => (
              <div
                key={key}
                className="p-5 rounded-2xl bg-white/[0.01] border border-white/5 space-y-2"
              >
                <div className="flex items-center justify-between opacity-30 transition-opacity">
                  <span
                    className={`text-[11px] font-black tracking-widest uppercase ${key === "A" ? "text-primary" : "text-ccut-indigo"
                      }`}
                  >
                    제안 상세
                  </span>
                  <span className="text-[10px] font-bold text-muted-foreground/40">
                    {p.score}
                  </span>
                </div>

                <div className="space-y-3">
                  <h4 className="text-[16px] font-bold text-foreground transition-colors">
                    {p.title}
                  </h4>
                  <p className="text-[13px] text-foreground/80 leading-relaxed font-medium transition-colors">
                    {p.desc}
                  </p>

                  {/* [STEP 10-I.5.25-A] Story & Explanation UI */}
                  {(p.proposal_story || p.proposal_explanation) && (
                    <div className="mt-4 pt-4 border-t border-white/5 space-y-4 animate-in fade-in duration-500">
                      {/* 1. 편집 스토리 (Summary) */}
                      {p.proposal_story && (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 opacity-80">
                            <BookOpen size={10} className="text-primary" />
                            <span className="text-[10px] font-bold uppercase tracking-wider">편집 스토리</span>
                          </div>
                          <p className="text-[11px] text-foreground/75 leading-relaxed">
                            {p.proposal_story.story_summary}
                          </p>
                        </div>
                      )}

                      {/* 2. 스토리라인 (Steps) - Collapsible */}
                      {p.proposal_explanation?.storyline && (
                        <details className="group/details">
                          <summary className="flex items-center justify-between cursor-pointer list-none opacity-70 hover:opacity-100 transition-all">
                            <div className="flex items-center gap-1.5">
                              <List size={10} className="text-primary" />
                              <span className="text-[10px] font-bold uppercase tracking-wider">전개 과정</span>
                            </div>
                            <ChevronDown size={10} className="group-open/details:rotate-180 transition-transform" />
                          </summary>
                          <div className="mt-2 space-y-2 border-l border-white/5 pl-3 py-1">
                            {p.proposal_explanation.storyline.map((step: any) => (
                              <div key={step.step} className="space-y-0.5">
                                <div className="flex items-center gap-2">
                                  <span className="text-[9px] font-black text-primary/70">0{step.step}</span>
                                  <span className="text-[10px] font-bold text-foreground/80">{step.role.toUpperCase()}</span>
                                </div>
                                <p className="text-[10px] text-foreground/60 leading-snug">
                                  {step.description}
                                </p>
                              </div>
                            ))}
                          </div>
                        </details>
                      )}

                      {/* 3. 소스별 요약 - Collapsible */}
                      {p.proposal_explanation?.source_summaries && (
                        <details className="group/details">
                          <summary className="flex items-center justify-between cursor-pointer list-none opacity-70 hover:opacity-100 transition-all">
                            <div className="flex items-center gap-1.5">
                              <Package size={10} className="text-primary" />
                              <span className="text-[10px] font-bold uppercase tracking-wider text-foreground/80">영상별 분석</span>
                            </div>
                            <ChevronDown size={10} className="group-open/details:rotate-180 transition-transform" />
                          </summary>
                          <div className="mt-2 grid grid-cols-1 gap-2 border-l border-white/5 pl-3 py-1">
                            {(() => {
                              const selectedCountBySourceId = new Map<string, number>();
                              const proposalFragments =
                                p.sequence ||
                                p.fragments ||
                                p.key_fragments ||
                                p.resolved_fragments ||
                                [];

                              proposalFragments.forEach((f: any) => {
                                const sid = extractSourceIdFromAny(f);
                                if (sid) selectedCountBySourceId.set(sid, (selectedCountBySourceId.get(sid) || 0) + 1);
                              });

                              // Diagnostic log (One-time check per render loop)
                              const totalFound = Array.from(selectedCountBySourceId.values()).reduce((a, b) => a + b, 0);
                              if (proposalFragments.length > 0 && totalFound === 0) {
                                console.warn("[proposal-usage-count] all usage counts are zero", {
                                  proposalKeys: Object.keys(p || {}),
                                  sampleSequence: proposalFragments.slice(0, 5),
                                  sourceEntries: sourceEntries?.slice(0, 5),
                                });
                              }

                              return p.proposal_explanation.source_summaries
                                .filter((src: any) => sourceLabelMap[src.source_id])
                                .map((src: any, idx: number) => {
                                  const entry = sourceEntries?.find(e => e.source_id === src.source_id);
                                  const sidKey = extractSourceIdFromAny(src.source_id) || src.source_id;
                                  const realProposedCount = selectedCountBySourceId.get(sidKey) || selectedCountBySourceId.get(src.source_id) || 0;

                                  return (
                                    <div key={`${src.source_id}-${idx}`} className="flex flex-col">
                                      <div className="flex items-center gap-2">
                                        <span className="text-[10px] font-bold text-foreground/80">
                                          영상 {sourceLabelMap[src.source_id] || src.source_label || labels[idx] || `S${idx + 1}`}
                                        </span>
                                        <span className="text-[9px] text-foreground/50 font-medium">
                                          · {formatMB(entry?.file_size_bytes)} · {formatDuration(entry?.duration_sec)}
                                        </span>
                                        <span className="text-[9px] px-1.5 py-0.5 bg-white/5 rounded text-foreground/60 ml-auto">{src.dominant_topic}</span>
                                      </div>
                                      <div className="flex items-center gap-2 mt-0.5">
                                        <p className="text-[9px] text-foreground/60">
                                          {src.visual_character}
                                        </p>
                                        <div className="flex gap-2 text-[9px] font-medium">
                                          <span className="text-foreground/50">분석된 의미 조각: {src.fragment_count}개</span>
                                          <span className="text-primary/70">제안 사용 조각: {realProposedCount}개</span>
                                        </div>
                                      </div>
                                    </div>
                                  );
                                });
                            })()}
                          </div>
                        </details>
                      )}

                      {/* 4. 품질 경고 (Quality Warnings) */}
                      {p.proposal_explanation?.quality_warnings?.length > 0 && (
                        <div className="pt-2">
                          <div className="flex items-center gap-1.5 opacity-80 mb-1.5">
                            <AlertCircle size={10} className="text-amber-500" />
                            <span className="text-[10px] font-bold uppercase tracking-wider text-amber-500">데이터 품질 안내</span>
                          </div>
                          <ul className="space-y-1 list-none">
                            {p.proposal_explanation.quality_warnings.map((warn: string, i: number) => (
                              <li key={i} className="text-[9px] text-amber-200/70 leading-relaxed flex gap-1.5 items-start">
                                <span className="mt-1 w-1 h-1 rounded-full bg-amber-500/40 shrink-0" />
                                {warn}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="col-span-2 p-10 rounded-2xl bg-red-500/5 border border-red-500/10 flex flex-col items-center gap-2">
              <span className="text-[12px] font-bold text-red-400/60 uppercase tracking-widest">
                Analysis Pipeline Failure
              </span>
              <p className="text-[11px] text-muted-foreground/40">
                제안을 생성하지 못했습니다. 원본 영상 상태를 확인하거나 다시 분석을 시도해 주세요.
              </p>
            </div>
          )}
        </div>

        {committedProposalId && (
          <div className="flex flex-col items-center gap-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
            <button
              onClick={handleExportClick}
              disabled={isExporting}
              className="px-10 py-3 rounded-xl bg-primary text-primary-foreground text-[13px] font-bold hover:opacity-90 disabled:opacity-40 transition-all shadow-xl shadow-primary/20 flex items-center gap-2"
            >
              {isExporting ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  {renderStatus || "처리 중..."}
                </>
              ) : (
                <>
                  <Package size={16} />
                  {exportUrl
                    ? `${committedProposalId}안 다시 내보내기`
                    : `${committedProposalId}안 내보내기`}
                </>
              )}
            </button>

            {exportUrl && (
              <div className="flex flex-col items-center gap-4 mt-2 p-6 rounded-2xl bg-white/5 border border-white/10 w-full animate-in fade-in zoom-in duration-300">
                <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-black shadow-2xl">
                  <video
                    src={normalizeMediaUrl(exportUrl)}
                    controls
                    className="w-full h-full"
                  />
                </div>

                <div className="flex flex-col items-center gap-2">
                  <div className="flex items-center gap-6 text-[11px] text-muted-foreground/60 font-medium">
                    <span className="flex items-center gap-1.5">
                      <CheckCircle2 size={12} className="text-primary" />
                      상태: {renderResult?.status}
                    </span>
                    <span>크기: {renderResult?.file_size?.toLocaleString() || 0} bytes</span>
                    <span>길이: {renderResult?.duration || 0}초</span>
                  </div>

                  <a
                    href={normalizeMediaUrl(exportUrl)}
                    target="_blank"
                    rel="noopener noreferrer"
                    download
                    className="flex items-center gap-2 px-8 py-2.5 rounded-lg bg-primary/10 text-primary text-[12px] font-bold hover:bg-primary/20 transition-all"
                  >
                    <Send size={14} />
                    최종 영상 다운로드
                  </a>
                </div>
              </div>
            )}

            {exportError && <p className="text-[11px] text-red-400/80">{exportError}</p>}
          </div>
        )}

        {guidanceMessage && (
          <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
            <div className="border-l border-primary/20 pl-4">
              <p className="text-[11px] font-bold text-primary/60 uppercase tracking-widest">
                {guidanceMessage}
              </p>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#0a0a0b] items-center overflow-hidden relative">
      {renderContent()}

      {/* [STEP 10-I.5.28-E9-R2-R3-R2] ChatGPT-style auto-grow Composer */}
      {storyPlan && (
        <div className="sticky bottom-0 z-20 w-full border-t border-zinc-800/70 bg-black/90 px-5 py-4">
          <div className="mx-auto flex w-full max-w-3xl items-end gap-3 rounded-[28px] border border-zinc-700/70 bg-zinc-900/80 px-5 py-3 shadow-sm">
            <textarea
              ref={consultationTextareaRef}
              value={consultationInput}
              rows={1}
              placeholder="편하게 말씀해 주세요. 예: 사람 중심으로 / 더 빠르게 / 풍경 줄여"
              disabled={appState === "analyzing"}
              onChange={(e) => {
                setConsultationInput(e.target.value);
                resizeConsultationTextarea(e.currentTarget);
              }}
              onKeyDown={(e) => {
                if (e.nativeEvent.isComposing) return;
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmitConsultation();
                }
              }}
              className="min-h-[44px] max-h-[160px] flex-1 resize-none overflow-y-auto bg-transparent py-2 text-sm leading-relaxed text-zinc-100 outline-none placeholder:text-zinc-500 whitespace-pre-wrap break-words disabled:opacity-40"
            />
            <button
              type="button"
              onClick={handleSubmitConsultation}
              disabled={!consultationInput.trim() || appState === "analyzing"}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-zinc-950 disabled:opacity-30 transition-opacity"
              aria-label="의견 보내기"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Legacy global chat bar (non-consultation states) */}
      {!storyPlan && (
        <div className="absolute bottom-10 w-full max-w-3xl px-8 pointer-events-none z-50">
          <div className="relative flex items-center pointer-events-auto">
            <input
              type="text"
              value={chatValue}
              onChange={(e) => setChatValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSendFull();
              }}
              disabled={appState === "analyzing"}
              placeholder={
                appState === "analyzing"
                  ? "분석 중에는 잠시만 기다려 주세요..."
                  : "편하게 말씀해 주세요. 예: 사람 중심으로 / 더 빠르게 / 풍경 줄여"
              }
              className={`w-full bg-[#161618] border border-white/5 rounded-full px-10 py-5 text-[14px] focus:outline-none focus:border-white/10 shadow-2xl transition-all ${appState === "analyzing" ? "opacity-40" : "placeholder:text-muted-foreground/30"
                }`}
            />
            <button
              onClick={handleSendFull}
              className="absolute right-3 p-2.5 rounded-full bg-primary/20 text-primary hover:bg-primary hover:text-primary-foreground transition-all"
            >
              <Send size={20} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default CenterPanel;