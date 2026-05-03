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
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRefA = useRef<HTMLVideoElement>(null);
  const videoRefB = useRef<HTMLVideoElement>(null);

  const [activePlayer, setActivePlayer] = useState<"A" | "B" | null>(null);
  const activePlayerRef = useRef<"A" | "B" | null>(null);

  const setActivePlayerSafe = useCallback((player: "A" | "B" | null) => {
    activePlayerRef.current = player;
    setActivePlayer(player);
  }, []);

  const [isPlayingA, setIsPlayingA] = useState(false);
  const [isPlayingB, setIsPlayingB] = useState(false);
  const [chatValue, setChatValue] = useState("");
  const [progressA, setProgressA] = useState(0);
  const [progressB, setProgressB] = useState(0);
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

  const isSeekingARef = useRef<boolean>(false);
  const isSeekingBRef = useRef<boolean>(false);

  const cleanupPendingLoadHandler = useCallback((player: "A" | "B") => {
    const ref = player === "A" ? videoRefA : videoRefB;
    const pending = player === "A" ? pendingLoadHandlerARef : pendingLoadHandlerBRef;

    if (ref.current && pending.current) {
      ref.current.removeEventListener("loadeddata", pending.current);
      pending.current = null;
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

  const playerVideoUrlA = getVideoUrlForProposal("A") ?? videoUrl ?? null;
  const playerVideoUrlB = getVideoUrlForProposal("B") ?? videoUrl ?? null;

  const buildSeqFrags = useCallback(
    (proposalKey: "A" | "B"): Fragment[] => {
      const p = proposals?.[proposalKey];
      const ids: string[] = p?.key_fragments ?? p?.sequence ?? [];
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
      endSecRef: React.MutableRefObject<number>
    ) => {
      const ref = player === "A" ? videoRefA : videoRefB;
      if (!ref.current) return;

      const fragUrl = getVideoUrlForFrag(frag.fragment_id) ?? videoUrl ?? undefined;
      const startSec = (frag.start_frame ?? 0) / 30;
      const rawEndSec = (frag.end_frame ?? 0) / 30;
      const endSec = rawEndSec > startSec ? rawEndSec : startSec + 1;

      endSecRef.current = endSec;

      const doSeekPlay = () => {
        if (!ref.current) return;
        ref.current.currentTime = startSec;
        ref.current.play().catch(() => { });
      };

      cleanupPendingLoadHandler(player);

      if (fragUrl && !sameVideoSource(ref.current.currentSrc || ref.current.src, fragUrl)) {
        ref.current.pause();
        ref.current.src = fragUrl;

        const onLoaded = () => {
          cleanupPendingLoadHandler(player);
          doSeekPlay();
        };

        if (player === "A") pendingLoadHandlerARef.current = onLoaded;
        else pendingLoadHandlerBRef.current = onLoaded;

        ref.current.addEventListener("loadeddata", onLoaded);
        ref.current.load();
      } else {
        doSeekPlay();
      }
    },
    [cleanupPendingLoadHandler, getVideoUrlForFrag, sameVideoSource, videoUrl]
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
    },
    [cleanupPendingLoadHandler]
  );

  const startSeq = useCallback((player: "A" | "B") => {
    const isA = player === "A";
    const ref = isA ? videoRefA : videoRefB;
    const frags = buildSeqFrags(player);
    if (frags.length === 0) return;

    // 전체 시퀀스 길이 계산
    const totalSec = frags.reduce((acc, f) => {
      const s = (f.start_frame ?? 0) / 30;
      const e = (f.end_frame ?? 0) / 30;
      return acc + Math.max(e - s, 1);
    }, 0);

    if (isA) {
      stopSeq("B");
      seqTotalSecARef.current = totalSec;
      seqElapsedSecARef.current = 0;
      seqFragsARef.current = frags;
      seqIdxARef.current = 0;
      isSeqARef.current = true;
      setActivePlayerSafe("A");
      setIsPlayingA(true);
      setProgressA(0);
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
      setProgressB(0);
      playFrag("B", frags[0], seqEndBRef);
    }
  }, [buildSeqFrags, playFrag, setActivePlayerSafe, stopSeq]);

  useEffect(() => {
    if (appState !== "complete") return;

    stopSeq("A");
    stopSeq("B");

    if (videoRefA.current) {
      videoRefA.current.load();
      videoRefA.current.currentTime = 0;
    }

    if (videoRefB.current) {
      videoRefB.current.load();
      videoRefB.current.currentTime = 0;
    }
  }, [appState, playerVideoUrlA, playerVideoUrlB, stopSeq]);

  useEffect(() => {
    if (appState !== "complete" || !proposals) return;

    const setThumbnailPosition = (
      ref: React.RefObject<HTMLVideoElement>,
      player: "A" | "B"
    ) => {
      const p = proposals[player];
      const firstFragId = p?.key_fragments?.[0] ?? p?.sequence?.[0];
      if (!ref.current || !firstFragId) return;

      const firstFrag = allSourceFragments.find((f: any) => f.fragment_id === firstFragId);
      if (!firstFrag) return;

      const targetUrl = getVideoUrlForProposal(player);
      const seekTime = (firstFrag.start_frame ?? 0) / 30;
      const isA = player === "A";

      const performSeek = () => {
        if (!ref.current) return;
        if (isA) isSeekingARef.current = true; else isSeekingBRef.current = true;
        if (isA) setProgressA(0); else setProgressB(0);

        ref.current.currentTime = seekTime;
        console.log(`[seek-sync] ${player} seek to ${seekTime}`);

        const timer1 = setTimeout(() => {
          if (isA) setProgressA(0); else setProgressB(0);
          const timer2 = setTimeout(() => {
            if (isA) {
              setProgressA(0);
              isSeekingARef.current = false;
            } else {
              setProgressB(0);
              isSeekingBRef.current = false;
            }
            console.log(`[seek-sync] ${player} unlocked`);
          }, 100);
        }, 50);
      };

      if (targetUrl && !sameVideoSource(ref.current.currentSrc || ref.current.src, targetUrl)) {
        ref.current.src = targetUrl;
        ref.current.load();
        const onLoaded = () => {
          performSeek();
          ref.current?.removeEventListener("loadeddata", onLoaded);
        };
        ref.current.addEventListener("loadeddata", onLoaded);
      } else {
        performSeek();
      }
    };

    const t = setTimeout(() => {
      setThumbnailPosition(videoRefA, "A");
      setThumbnailPosition(videoRefB, "B");
      // thumbnail seek로 인한 progress bar 오염 방지
      setTimeout(() => {
        setProgressA(0);
        setProgressB(0);
      }, 100);
    }, 300);

    return () => clearTimeout(t);
  }, [appState, proposals, allSourceFragments, getVideoUrlForProposal, sameVideoSource]);

  useEffect(() => {
    if (!selectedFragment) return;

    if (isSeqARef.current) stopSeq("A");
    if (isSeqBRef.current) stopSeq("B");

    const player = activePlayerRef.current === "B" ? "B" : "A";
    const endRef = player === "B" ? seqEndBRef : seqEndARef;

    setActivePlayerSafe(player);
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
      setProgressA(0);
      setProgressB(0);

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
        
        {/* [STEP 10-I.5.28-E9-R2] Pre-Proposal Narrative Consultation View */}
        {storyPlan && storyPlan.consultation_status !== "confirmed" && (
          <div className="w-full max-w-[800px] bg-card/60 border border-primary/30 rounded-3xl p-8 shadow-2xl backdrop-blur-md animate-in fade-in zoom-in duration-500 mt-4">
            <div className="flex flex-col gap-6">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-2xl bg-primary/20 flex items-center justify-center">
                  <BookOpen size={24} className="text-primary" />
                </div>
                <div>
                  <h2 className="text-[18px] font-bold text-foreground">편집스토리 초안 협의</h2>
                  <p className="text-[12px] text-muted-foreground/70">분석 데이터를 기반으로 먼저 이야기 흐름을 구성했습니다.</p>
                </div>
              </div>

              <div className="bg-secondary/20 rounded-2xl p-6 border border-border/10 leading-relaxed text-[14px] text-foreground/90 whitespace-pre-wrap italic">
                "{storyPlan.narrative_draft}"
              </div>

              <div className="space-y-4">
                <p className="text-[12px] font-semibold text-primary/80 uppercase tracking-widest">이 방향이 맞을까요?</p>
                <div className="flex flex-wrap gap-2">
                  <button 
                    className="px-6 py-2.5 bg-primary text-primary-foreground rounded-xl text-[13px] font-bold hover:opacity-90 shadow-xl shadow-primary/20 transition-all hover:scale-105"
                    onClick={() => onStoryPlanConfirm?.({ ...storyPlan, consultation_status: "confirmed", confirmation_status: "confirmed" })}
                  >
                    좋아, 이대로 제안해줘
                  </button>
                  <button 
                    className="px-5 py-2.5 bg-secondary/40 text-foreground rounded-xl text-[13px] font-medium hover:bg-secondary/60 transition-all"
                    onClick={() => onReproposal?.("사람 중심으로")}
                  >
                    사람 중심
                  </button>
                  <button 
                    className="px-5 py-2.5 bg-secondary/40 text-foreground rounded-xl text-[13px] font-medium hover:bg-secondary/60 transition-all"
                    onClick={() => onReproposal?.("풍경 줄이기")}
                  >
                    풍경 줄이기
                  </button>
                  <button 
                    className="px-5 py-2.5 bg-secondary/40 text-foreground rounded-xl text-[13px] font-medium hover:bg-secondary/60 transition-all"
                    onClick={() => onReproposal?.("더 빠르게")}
                  >
                    더 빠르게
                  </button>
                  <button 
                    className="px-5 py-2.5 bg-secondary/40 text-foreground rounded-xl text-[13px] font-medium hover:bg-secondary/60 transition-all"
                    onClick={() => onReproposal?.("여러 영상을 골고루")}
                  >
                    여러 영상을 골고루
                  </button>
                </div>
                <p className="text-[11px] text-muted-foreground/50 italic">아래 채팅창에 원하는 편집 방향을 자유롭게 말씀하셔도 됩니다.</p>
              </div>

              {storyPlan.consultation_status === "user_requested_change" && (
                <div className="mt-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-2xl flex items-center gap-3">
                  <AlertCircle size={18} className="text-amber-500" />
                  <div>
                    <p className="text-[12px] font-bold text-amber-200">의견이 반영되었습니다</p>
                    <p className="text-[11px] text-amber-200/60">"{storyPlan.user_notes}" 방향을 고려하여 제안을 준비합니다. 완료되면 '이대로 제안해줘'라고 말씀하세요.</p>
                  </div>
                </div>
              )}
            </div>
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

        {/* [STEP 10-I.5.28-E9-R2] Proposals Grid (Visible only after confirmation) */}
        {storyPlan?.consultation_status === "confirmed" && (
          <div className="grid grid-cols-2 gap-4 w-full">
          <div className="flex flex-col items-center space-y-4">
            <div
              className="relative w-full aspect-[16/8] rounded-2xl bg-black overflow-hidden border border-white/8 cursor-pointer group/player"
              onClick={() => {
                if (!videoRefA.current) return;

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
                    src={playerVideoUrlA ?? videoUrl ?? undefined}
                    poster={getProposalPoster("A")}
                    className="w-full h-full object-contain bg-black"
                    onPlay={() => {
                      setActivePlayerSafe("A");
                      setIsPlayingA(true);
                    }}
                    onPause={() => setIsPlayingA(false)}
                    onTimeUpdate={(e) => {
                      if (isSeekingARef.current) return;
                      const v = e.currentTarget;
                      if (isSeqARef.current && seqTotalSecARef.current > 0) {
                        const fragStart = (seqFragsARef.current[seqIdxARef.current]?.start_frame ?? 0) / 30;
                        const elapsed = seqElapsedSecARef.current + Math.max(0, v.currentTime - fragStart);
                        setProgressA((elapsed / seqTotalSecARef.current) * 100);
                      } else if (v.duration) {
                        setProgressA((v.currentTime / v.duration) * 100);
                      }

                      const near =
                        seqEndARef.current > 0 && v.currentTime >= seqEndARef.current - 0.08;
                      if (!near) return;

                      if (isSeqARef.current) {
                        const nextIdx = seqIdxARef.current + 1;
                        const frags = seqFragsARef.current;

                        if (nextIdx < frags.length) {
                          const curFragA = seqFragsARef.current[seqIdxARef.current];
                          const csA = (curFragA?.start_frame ?? 0) / 30;
                          const ceA = (curFragA?.end_frame ?? 0) / 30;
                          seqElapsedSecARef.current += Math.max(ceA - csA, 1);
                          seqIdxARef.current = nextIdx;
                          playFrag("A", frags[nextIdx], seqEndARef);
                        } else {
                          isSeqARef.current = false;
                          seqIdxARef.current = -1;
                          seqEndARef.current = -1;
                          v.pause();
                          setIsPlayingA(false);
                        }
                      } else {
                        v.pause();
                        setIsPlayingA(false);
                        seqEndARef.current = -1;
                      }
                    }}
                    onLoadedMetadata={(e) => setDurationA(e.currentTarget.duration)}
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

              <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/10 z-30">
                <div
                  className="h-full bg-primary/70 transition-all duration-100"
                  style={{ width: `${progressA}%` }}
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
                    src={playerVideoUrlB ?? videoUrl ?? undefined}
                    poster={getProposalPoster("B")}
                    className="w-full h-full object-contain bg-black"
                    onPlay={() => {
                      setActivePlayerSafe("B");
                      setIsPlayingB(true);
                    }}
                    onPause={() => setIsPlayingB(false)}
                    onTimeUpdate={(e) => {
                      if (isSeekingBRef.current) return;
                      const v = e.currentTarget;
                      if (isSeqBRef.current && seqTotalSecBRef.current > 0) {
                        const fragStart = (seqFragsBRef.current[seqIdxBRef.current]?.start_frame ?? 0) / 30;
                        const elapsed = seqElapsedSecBRef.current + Math.max(0, v.currentTime - fragStart);
                        setProgressB((elapsed / seqTotalSecBRef.current) * 100);
                      } else if (v.duration) {
                        setProgressB((v.currentTime / v.duration) * 100);
                      }

                      const near =
                        seqEndBRef.current > 0 && v.currentTime >= seqEndBRef.current - 0.08;
                      if (!near) return;

                      if (isSeqBRef.current) {
                        const nextIdx = seqIdxBRef.current + 1;
                        const frags = seqFragsBRef.current;

                        if (nextIdx < frags.length) {
                          const curFragB = seqFragsBRef.current[seqIdxBRef.current];
                          const csB = (curFragB?.start_frame ?? 0) / 30;
                          const ceB = (curFragB?.end_frame ?? 0) / 30;
                          seqElapsedSecBRef.current += Math.max(ceB - csB, 1);
                          seqIdxBRef.current = nextIdx;
                          playFrag("B", frags[nextIdx], seqEndBRef);
                        } else {
                          isSeqBRef.current = false;
                          seqIdxBRef.current = -1;
                          seqEndBRef.current = -1;
                          v.pause();
                          setIsPlayingB(false);
                        }
                      } else {
                        v.pause();
                        setIsPlayingB(false);
                        seqEndBRef.current = -1;
                      }
                    }}
                    onLoadedMetadata={(e) => setDurationB(e.currentTarget.duration)}
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

              <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/10 z-30">
                <div
                  className="h-full bg-ccut-indigo/70 transition-all duration-100"
                  style={{ width: `${progressB}%` }}
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
                ? "AI 인지 분석 중에는 명령을 입력할 수 없습니다..."
                : "예: 더 감성적으로 / 더 빠르게 / 웃긴 장면 살려 / 시장형으로 다시"
            }
            className={`w-full bg-[#121214]/80 backdrop-blur-xl border border-white/5 rounded-full px-10 py-5 text-[14px] focus:outline-none focus:border-white/10 shadow-2xl transition-all ${appState === "analyzing" ? "opacity-40" : "placeholder:text-muted-foreground/10"
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
    </div>
  );
};

export default CenterPanel;