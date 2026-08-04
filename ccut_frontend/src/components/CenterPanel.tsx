// CCUT 1.0.4 - R9.1 Rollback Verified
import React, { useRef, useEffect, useLayoutEffect, useState, useCallback, useMemo } from "react";
import { UploadStagingView, probeFileMeta, type StagedMeta, type IntakeAnswers } from "@/components/views/UploadStagingView";
import { setKnownPersonNames } from "@/hooks/useProposalState";
// [CHAT-SKIN 2026-08-02] BookOpen(책 펼침) 아이콘은 프로젝트에서 완전히 뺐다 — 국장 지시.
import { Play, Loader2, Send, ArrowUp, Plus, CheckCircle2, Package, List, ChevronDown, AlertCircle } from "lucide-react";
import { Fragment } from "@/data/fragmentData";
import { videoService } from "@/services/videoService";
import { Direction, StoryPlanPreview } from "@/proposal/proposalTypes";
import { PhysicalClip, validateExportClips } from "@/utils/exportClipBuilder";
import { collectFragmentAliases } from "@/utils/proposalFragmentResolver";
import { EmptyProjectView } from "@/components/views/EmptyProjectView";
import { AnalysisLoadingView } from "@/components/views/AnalysisLoadingView";
import { ExportPanelSection } from "@/components/views/ExportPanelSection";
import { FragSearchPanel } from "@/components/views/FragSearchPanel";
import { ComposerSection } from "@/components/views/ComposerSection";
import { DEBUG_LOG } from "@/utils/debugFlags";
// [STORY-GATE P3] 승인 전에는 편집 결과물 대신 '원고'를 무대에 세운다.
import { useStoryGate } from "@/hooks/useStoryGate";
import { fragmentTranscriptText, FRAGMENT_TEXT_FONT, FRAGMENT_TEXT_STYLE, FRAGMENT_SILENT_STYLE } from "@/lib/fragmentText";
// [CHATLOG-STACK-01] storyStageVisible import 제거 — 중앙은 택일하지 않는다(누적).
//   이 유틸의 소비처는 이제 Index의 rightStoryMode 하나다.

import type { AppState, SourceEntry } from "@/types";

const AUDIO_SPLICE_FADE_MS = 8;

function playWithAudioRamp(video: HTMLVideoElement) {
  video.volume = 0;
  const startedAt = performance.now();
  const ramp = () => {
    const pct = Math.min(1, (performance.now() - startedAt) / AUDIO_SPLICE_FADE_MS);
    video.volume = pct;
    if (pct < 1 && !video.paused) requestAnimationFrame(ramp);
  };
  video.play().catch(() => {
    video.volume = 1;
  });
  requestAnimationFrame(ramp);
}

function readFragmentStartSec(fragment: any): number {
  return Number(fragment?.start_sec ?? fragment?.start_time ?? fragment?.start ?? ((fragment?.start_frame ?? 0) / 30));
}

function readFragmentEndSec(fragment: any): number {
  const start = readFragmentStartSec(fragment);
  const raw = Number(fragment?.end_sec ?? fragment?.end_time ?? fragment?.end ?? ((fragment?.end_frame ?? 0) / 30));
  return raw > start ? raw : start + 1;
}

function readFragmentDurationSec(fragment: any): number {
  return Math.max(readFragmentEndSec(fragment) - readFragmentStartSec(fragment), 0.001);
}

/**
 * [PLAYSTABILITY-FIX-01 3번] 재생 시 end를 실제 영상 길이로 클램프 (파생 보정만).
 *   실측: SF_B2425A_SRC_F6A1092E 의 end 18.0 > 소스 duration 17.995465 (4.5ms 초과).
 *   경계 판정은 `currentTime >= end - LEAD`인데, 초과분이 LEAD(0.02s)보다 크면 도달 자체가
 *   불가능해 경계가 영원히 안 걸린다(= 그 조각에서 멈춤). duration을 넘지 않게 깎는다.
 *   ★DB의 조각 좌표는 건드리지 않는다 — 재생 순간의 파생값만 보정한다.
 */
function clampEndToDuration(endSec: number, duration: number | undefined | null): number {
  const d = Number(duration);
  if (!Number.isFinite(d) || d <= 0) return endSec;   // 아직 모르면 그대로 (metadata 전)
  return endSec > d ? d : endSec;
}

function physicalClipToFragment(clip: PhysicalClip, sourceLabelMap: Record<string, string> = {}): Fragment {
  const start = clip.start_sec;
  const end = clip.end_sec;
  return {
    fragment_id: clip.fragment_id,
    fragment_uid: (clip as any).clip_of ?? clip.display_id ?? `${clip.fragment_id}_${clip.order}`,
    source_id: clip.source_id,
    // [STATE-DRIFT 수리 2026-07-22] source_video는 '소스 문자 라벨'이어야 한다(원본ID 금지).
    //   sourceLabelMap(source_id→라벨)로 문자를 얻는다. 미매핑이면 ""(방어선이 경고).
    source_video: sourceLabelMap[clip.source_id] || "",
    display_id: clip.display_id ?? (clip as any).clip_of ?? clip.fragment_id,
    start_sec: start,
    end_sec: end,
    start_time: start,
    end_time: end,
    start_frame: Math.round(start * 30),
    end_frame: Math.max(Math.round(start * 30) + 1, Math.round(end * 30)),
    duration: Math.max(1, Math.round((end - start) * 30)),
    video_url: (clip as any).video_url,
    selection_state: "S",
    status: "committed",
  } as any;
}

interface StoryLedgerItem {
  timeline_item_id: string;
  fragment_id?: string;
  selected?: boolean;
  play_order?: number;
  removed?: boolean;
  missing?: unknown;
  place?: string | null;
  source_title?: string | null;
  source_id?: string | null;
  words?: Array<{ w: string }> | null;
  dialogue?: string | null;
  stage_direction?: string | null;
}

interface StoryLedgerResponse {
  ok?: boolean;
  items?: StoryLedgerItem[];
}

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
  analysisLogs?: string[];
  videoUrl?: string | null;
  sources?: any[];
  proposals?: any;
  /** [#22-b] 재편집 세션 — 이 프로젝트를 '다시 편집'으로 열었는가. 중앙도 스토리 상태 강제. */
  reEditActive?: boolean;
  committedProposalId?: string | null;
  // [#28 재생원 일원화] 조각맵에 현재 깔린 제안(committed ?? selected) — 그 제안의 라이브 재생은
  // fragments prop(조각맵 파생)만 쓴다. 화면과 재생은 같은 진실 (헌장 §5).
  displayProposalId?: string | null;
  // [F1 하나의 강물] 재생 불가 안내를 지휘부 채팅에 흘리는 위임 콜백 (toast 폐지 — SEE FAIL 1)
  onPlaybackNotice?: (text: string) => void;
  onPreviewProposal?: (key: string) => void;
  onCommitProposal?: (key: string) => void;
  onPreviewNext?: () => void;
  guidanceMessage?: string;
  onNextProposals?: () => void;
  sourceFragments?: Fragment[];
  sourceId?: string | null;
  sourceEntries?: SourceEntry[];
  fragments?: Fragment[];
  /** [SEQ_INV-BASE] 승인된 스토리의 fid 순서 — Export(ledger EDL)와 같은 권위(ui_state.story.fids). */
  storyFids?: string[];
  exportClips?: PhysicalClip[];
  modeGateEnabled?: boolean;
  storyPlan?: StoryPlanPreview | null;
  onStoryPlanConfirm?: (plan: StoryPlanPreview) => void;
  onActiveFragmentChange?: (id: string | null, origin?: "sequence" | "user") => void;
  activeFragmentId?: string | null;
  activeStoryFragmentId?: string | null;
  storyReplacement?: React.ReactNode;
  roughCutStage?: React.ReactNode;
  /** [LAYER-SPLIT 2026-08-04 ②] 저장된 버전 아이콘 줄. 채팅창 바로 위 한 줄. */
  versionBar?: React.ReactNode;
  programId?: string | null;
  programTitle?: string | null;
  onExportDone?: () => void;
  onStoryEditStateChanged?: () => void;
  storyRefreshNonce?: number;
  // [FLOW] 제안 세대 기록 — 타임라인에 흘려보내고 옛 제안을 무대로 복원
  proposalHistory?: Array<{ id: string; ts: number; pair: any }>;
  activeProposalEntryId?: string | null;
  // [CHAT-FOLD 3-1] onRestoreProposalEntry 폐지 — '이 원고로 재작업' 버튼 전용 배선이었다.
  //   ★ Index.tsx:3456 이 아직 이 prop 을 넘기고 있다(무해: 받는 쪽이 안 쓴다).
  //     Index 쪽 handleRestoreProposalEntry 정리는 별건 — 국장 보고 목록에 올렸다.
  // [UI-③⑤] 문진 답변 (영상 설명, 화면/사운드 기준) → story_intent에 주입
  onIntake?: (answers: IntakeAnswers) => void;
  // [UI-⑧] 컴포저 + 버튼 → 영상 추가 파일창 열기 / 드래그된 파일 직접 추가
  onRequestAddVideos?: () => void;
  onAddVideoFiles?: (files: File[]) => void;
  // [TIMELINE-PAGE 2026-08-02] 300행 절단 복구 — 서버가 has_more 를 주는데 듣는 코드가
  //   0이었다(실측: Merope 614행 중 314행 도달 불가). 서버·서비스 계층은 손대지 않고
  //   호출처만 잇는다. 버튼 방식인 이유는 아래 렌더부 주석에.
  timelineHasMore?: boolean;
  timelineLoadingMore?: boolean;
  onLoadOlderTimeline?: () => void;
  /** [TIMELINE-REF 2026-08-02] 전사가 대화에 등장한 시각(원장 transcript_ref).
   *  null 이면 기록이 없다는 뜻 — 그때는 종전대로 맨 위(ts=0). */
  transcriptRefTs?: number | null;
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

export const formatMB = (bytes?: number) => {
  if (!bytes) return "0MB";
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
};

export const formatDuration = (seconds?: number) => {
  if (!seconds) return "0초";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins > 0) return `${mins}분 ${secs}초`;
  return `${secs}초`;
};

const getProposalSelfCheck = (proposal: any) => {
  return proposal?.self_check || proposal?.proposal_reason?.self_check || null;
};

const getSelfCheckIssueCount = (selfCheck: any) => {
  if (!selfCheck) return 0;
  return Number(selfCheck.mismatch_count || 0) +
    Number(selfCheck.ambiguous_count || 0) +
    Number(selfCheck.omitted_count || 0);
};

const renderSelfCheckPill = (proposal: any) => {
  const selfCheck = getProposalSelfCheck(proposal);
  const status = String(selfCheck?.status || "").toUpperCase();
  if (!selfCheck || status === "PASS") return null;

  const issueCount = getSelfCheckIssueCount(selfCheck);
  const totalCount = Number(selfCheck.total_count || 0);
  const isFail = status === "FAIL";
  const color = isFail ? "text-red-200 bg-red-500/20 border-red-400/30" : "text-amber-100 bg-amber-500/20 border-amber-400/30";

  return (
    <div className={`mt-1 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-bold tracking-normal ${color}`}>
      <AlertCircle size={11} />
      <span>검증 {status} · {issueCount}/{totalCount || "?"}</span>
    </div>
  );
};

const renderSelfCheckNotice = (proposals: any) => {
  const entries = (["A", "B"] as const)
    .map((key) => ({ key, selfCheck: getProposalSelfCheck(proposals?.[key]) }))
    .filter(({ selfCheck }) => selfCheck && String(selfCheck.status || "").toUpperCase() !== "PASS");

  if (entries.length === 0) return null;

  const hasFail = entries.some(({ selfCheck }) => String(selfCheck.status || "").toUpperCase() === "FAIL");
  const primary = entries[0].selfCheck;
  const color = hasFail ? "border-red-500/20 bg-red-500/8 text-red-100" : "border-amber-500/20 bg-amber-500/8 text-amber-100";

  return (
    <div className={`w-full rounded-lg border px-4 py-3 ${color}`}>
      <div className="flex items-start gap-2">
        <AlertCircle size={15} className="mt-0.5 shrink-0" />
        <div className="min-w-0">
          <div className="text-[11px] font-black uppercase tracking-wider">
            편집 조건 검증 {hasFail ? "FAIL" : "WARN"}
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-current/85">
            {primary?.message || "요청 조건과 일부 어긋나거나 애매한 컷이 포함됐습니다."}
          </p>
        </div>
      </div>
    </div>
  );
};

/**
 * [STEP 10-I.5.27-E6-R5] Robust Fragment Source ID Extraction Fallback
 */
export function extractSourceIdFromAny(value: any): string {
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

// [SHOW 2026-07-05] 조회 결과 카드 — "OO 보여줘/있나"의 답. 사람 말 명칭
// (원본 제목 · m:ss–m:ss)만 보여주고 내부 ID는 노출하지 않는다.
// 클릭 = 카드 그 자리에서 해당 구간 재생 (자체완결 URL — pool 상태 무관).
const SearchResultCards: React.FC<{ results: any[] }> = ({ results }) => {
  const [playingId, setPlayingId] = React.useState<string | null>(null);
  return (
    <div className="grid grid-cols-3 gap-2 mt-1 w-full max-w-[560px]">
      {results.map((r) => (
        <div
          key={r.fragment_id}
          className="rounded-lg overflow-hidden border border-border/30 bg-secondary/20 cursor-pointer group hover:border-primary/40 transition-colors"
          onClick={() => setPlayingId(playingId === r.fragment_id ? null : r.fragment_id)}
        >
          <div className="relative aspect-video bg-black/40">
            {playingId === r.fragment_id && r.video_url ? (
              <video
                src={r.video_url}
                className="absolute inset-0 w-full h-full object-cover"
                autoPlay controls playsInline
                onLoadedMetadata={(e) => { e.currentTarget.currentTime = r.start ?? 0; }}
                onTimeUpdate={(e) => {
                  const v = e.currentTarget;
                  if (r.end && v.currentTime >= r.end) v.pause();
                }}
                onClick={(e) => e.stopPropagation()}
              />
            ) : r.thumbnail_url ? (
              <>
                <img src={r.thumbnail_url} className="absolute inset-0 w-full h-full object-cover" draggable={false} />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30">
                  <Play size={18} className="text-white fill-white/40" />
                </div>
              </>
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-muted-foreground">
                <Play size={16} />
                <span className="text-[10px]">눌러서 재생</span>
              </div>
            )}
          </div>
          <div className="px-2 py-1.5">
            <div className="text-[11px] text-foreground truncate">{r.title}</div>
            <div className="text-[10px] text-muted-foreground">{r.time}</div>
          </div>
        </div>
      ))}
    </div>
  );
};

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
  analysisLogs,
  videoUrl,
  proposals,
  reEditActive,
  committedProposalId,
  displayProposalId,
  onPlaybackNotice,
  onPreviewProposal,
  onCommitProposal,
  sourceId,
  sourceEntries = [],
  fragments = [],
  storyFids = [],
  exportClips = [],
  modeGateEnabled,
  storyPlan,
  onStoryPlanConfirm,
  onActiveFragmentChange,
  activeFragmentId,
  activeStoryFragmentId: activeStoryFragmentIdProp,
  storyReplacement,
  roughCutStage,
  versionBar,
  programId,
  programTitle,
  onExportDone,
  onStoryEditStateChanged,
  storyRefreshNonce,
  proposalHistory = [],
  activeProposalEntryId = null,
  onIntake,
  onRequestAddVideos,
  onAddVideoFiles,
  timelineHasMore = false,
  timelineLoadingMore = false,
  onLoadOlderTimeline,
  transcriptRefTs = null,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRefA = useRef<HTMLVideoElement>(null);
  const videoRefB = useRef<HTMLVideoElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  // [CHATSCROLL-FIX-01] 표준 채팅 규칙 — 사용자가 하단 근처에 있을 때만 따라간다.
  //   구판은 새 내용이 늘어나면 무조건 chatEnd로 흘러내렸다(:673 block:"end").
  //   실측: 중간(S1=1200, 남은거리 2272)에서 새 메시지 1건 -> +2193px 하단 점프.
  //   위로 올려 읽는 중에는 끌어내리지 않고 '새 내용' 버튼만 띄운다.
  const chatScrollRef = useRef<HTMLDivElement>(null);
  // [LAYER-SPLIT 2026-08-04 ①] 전사층 펼침. 기본은 접힘 — 전사가 화면을 다 차지하기 때문이다.
  //   ★이 상태는 표시만 바꾼다. 몸통은 접혀도 마운트를 유지한다(8/3 교훈).
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const CHAT_BOTTOM_SLACK = 120; // 하단 근접 판정(px)
  const chatAtBottomRef = useRef(true);
  const [chatHasNew, setChatHasNew] = useState(false);
  const isChatNearBottom = useCallback(() => {
    const el = chatScrollRef.current;
    if (!el) return true;                                   // 아직 없음 = 따라가도 무해
    if (el.scrollHeight <= el.clientHeight + 4) return true; // 스크롤 자체가 없음 = 항상 하단
    return el.scrollHeight - el.scrollTop - el.clientHeight <= CHAT_BOTTOM_SLACK;
  }, []);
  // [CHATSCROLL-FIX-02 2026-07-27] '위로 올려 읽는 중'은 사용자 손짓이 있었을 때만이다.
  //   실사고(국장 화면, 앱 켜자마자): [CHATSCROLL][HOLD]{msgs:64,gens:11,
  //     reason:'user_scrolled_up'} — 사용자는 스크롤한 적이 없다.
  //   원인: 아래 handleChatScroll 이 '왜 스크롤됐는지'를 구분하지 못했다.
  //     (a) scrollIntoView({behavior:'smooth'})가 중간 위치마다 scroll 이벤트를 쏜다
  //     (b) 썸네일·영상이 뒤늦게 로드되며 높이가 늘어 하단이 밀린다
  //   둘 다 사용자 행동이 아닌데 추종을 꺼서, 이후 새 글이 중간에 놓이고
  //   '새 내용 ↓'를 일일이 눌러야 했다.
  //   → 손짓(휠·터치·키보드·스크롤바 드래그) 없이 일어난 이동으로는 추종을 끄지 않는다.
  const chatUserGestureRef = useRef(false);
  const handleChatScroll = useCallback(() => {
    const near = isChatNearBottom();
    if (near) {
      chatAtBottomRef.current = true;
      chatUserGestureRef.current = false;
      setChatHasNew(false);
      return;
    }
    // 하단이 아님 — 사용자가 직접 올린 경우에만 추종을 끈다.
    if (chatUserGestureRef.current) chatAtBottomRef.current = false;
    // else: 프로그램 스크롤·늦은 이미지 로드 — 판정 보류(추종 유지)
  }, [isChatNearBottom]);
  const scrollChatToBottom = useCallback(() => {
    chatAtBottomRef.current = true;
    chatUserGestureRef.current = false;
    setChatHasNew(false);
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);
  // [CHATSCROLL-FIX-02] 하단 정착 — 늦게 로드되는 썸네일·영상이 높이를 늘려 하단이
  //   밀리는 구간(앱 최초 로드)에서만 잠깐 더 붙잡는다. 3회·900ms 로 한정하고,
  //   그 사이 사용자가 손으로 올리면 chatAtBottomRef 가 꺼져 전부 무효가 된다.
  const settleChatToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    [200, 500, 900].forEach((ms) => setTimeout(() => {
      if (chatAtBottomRef.current) {
        chatEndRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
      }
    }, ms));
  }, []);
  // [CHATSCROLL-FIX-02] 사용자 손짓 감지 — 이것이 있을 때만 '올려 읽는 중'으로 본다.
  useEffect(() => {
    const el = chatScrollRef.current;
    if (!el) return;
    const mark = () => { chatUserGestureRef.current = true; };
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "]
          .includes(e.key)) mark();
    };
    const onMouseDown = (e: MouseEvent) => {
      // 스크롤바 영역 클릭(드래그 시작)만 손짓으로 본다 — 메시지 클릭은 아니다.
      const r = el.getBoundingClientRect();
      if (e.clientX > r.left + el.clientWidth) mark();
    };
    el.addEventListener("wheel", mark, { passive: true });
    el.addEventListener("touchmove", mark, { passive: true });
    el.addEventListener("keydown", onKey);
    el.addEventListener("mousedown", onMouseDown);
    return () => {
      el.removeEventListener("wheel", mark);
      el.removeEventListener("touchmove", mark);
      el.removeEventListener("keydown", onKey);
      el.removeEventListener("mousedown", onMouseDown);
    };
  }, []);
  const consultationTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [activePlayer, setActivePlayer] = useState<"A" | "B" | null>(null);
  const activePlayerRef = useRef<"A" | "B" | null>(null);

  // [LAYOUT] A/B 편집제안 세로 아코디언 — 기본 둘 다 접힘, 클릭 시 하나만 펼침
  // [CHATLOG-STACK-01 1번] 아코디언 폐지 — expandedProposal 제거.
  //   채팅은 기록이다. A를 고르면 B가 접히던 구조(탭·아코디언)는 확정 설계에 어긋난다.
  //   이제 A·B는 항상 펼친 채 세로로 누적되고, 선택은 '재생 위치'만 옮긴다.
  // [#19 스토리박스] 승인 전(story mode) 제안 세대를 채팅 흐름에 경량 스토리박스로 상주시킨다.
  // 기본 접힘(append-only 이력이 쌓여도 흐름이 스캔 가능하게 — E 판단). 헤더 클릭으로 펼침.
  // [CHAT-SKIN 2026-08-02] 지난 원고 펼침 상태 — CHAT-FOLD 3-1 에서 없앴다가 되살린다.
  //   없애야 했던 것은 안내 문구와 '재작업' 버튼(옛것만의 특별 취급)이지 내용이 아니었다.
  //   내용까지 없애니 클릭해도 아무것도 안 나왔다 — 국장 지적으로 확인된 내 잘못이다.
  const [openStoryBox, setOpenStoryBox] = useState<string | null>(null);
  // toggleProposal / playProposal / 기본 B 펼침 효과는 재생 의존성(previewUrl·startSeq 등)
  // 정의 이후(하단)에 배치한다. (여기서 참조하면 TDZ)
  const [consultationInput, setConsultationInput] = useState("");
  // [FLOW-STAGE] 무대가 이식될 타임라인 내 슬롯 (활성 제안 카드 위치)
  // [CHAT-FLOW 2026-08-02] 무대 접힘 상태 폐지.
  //   CHAT-ROOT 에서 무대를 스트림 위에 고정하며 접기를 뒀는데, 국장 확정으로 붙박이 자체가
  //   사라졌다 — 무대가 흐름 속 한 지점이 되었으니 접을 대상도, 접기 버튼도 없다.
  //
  // [CHAT-FOLD 2026-08-02] A 를 벗어나면 개켠다.
  //   국장 확정 규칙:
  //     (1) A(지금 보고 있는 화면) 안의 컨텐츠 — 접기·펴기는 오직 사용자가 정한다
  //     (2) A 를 크게 벗어나 올라간 컨텐츠 — 자동으로 아이콘화
  //   ★국장 눈앞에서 시스템이 접는 일은 없어야 한다. 그래서 경계를 A 가 아니라
  //     A + FOLD_MARGIN×A 로 둔다 — 화면에서 사라지고도 한참 뒤에 접힌다.
  //   ★한 번 접힌 것은 사용자 클릭으로만 펴진다. 다시 A 안으로 돌아와도 저절로 펴지지
  //     않는다(A 안은 사용자 주권). 펴놓은 것이 다시 밖으로 나가면 또 접힌다.
  //   ★아래쪽은 접지 않는다 — 아래는 새 것이 오는 방향이다.
  //   ★scroll 이벤트에 의존하지 않는다. 이 환경 실측(7/28)에서 scroll 이벤트는 0건
  //     발화했다. IntersectionObserver 로만 판정한다.
  const FOLD_MARGIN = 1.5;                    // 감시범위 = A + 1.5A = 2.5A (국장 조정용 상수)
  const [foldedIds, setFoldedIds] = useState<Set<string>>(() => new Set());
  const foldNodeRefs = useRef<Record<string, HTMLDivElement | null>>({});
  // 접기로 줄어든 높이를 되갚기 위한 예약 — 넉 달 싸운 '화면 튐'이 여기서 갈린다.
  const pendingFoldFixRef = useRef<{ id: string; h1: number } | null>(null);
  const unfoldItem = useCallback((id: string) => {
    setFoldedIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  // [CHAT-FOLD STEP 1] 높이 붕괴 보정 — ★이것이 먼저다.
  //   A 위쪽 아이템이 접히면 위 높이가 (h1-h2) 만큼 줄어 보던 화면이 그만큼 밀려 올라간다.
  //   넉 달 싸운 '화면 튐'이 정확히 이 모양이었다. 줄어든 만큼 scrollTop 에서 되갚는다.
  //   ★기존 스크롤 함수(scrollChatToBottom·settleChatToBottom·HOLD)는 건드리지 않는다.
  //     이 보정만 따로 선다.
  useLayoutEffect(() => {
    const fix = pendingFoldFixRef.current;
    if (!fix) return;
    pendingFoldFixRef.current = null;
    const el = foldNodeRefs.current[fix.id];
    const root = chatScrollRef.current;
    if (!el || !root) return;
    const h2 = el.getBoundingClientRect().height;
    const delta = fix.h1 - h2;
    if (delta > 0) {
      root.scrollTop = Math.max(0, root.scrollTop - delta);
      if (import.meta.env.DEV) {
        console.log("[CHAT-FOLD][HEIGHT-FIX]", { id: fix.id, h1: fix.h1, h2, delta });
      }
    }
  }, [foldedIds]);

  // [TIMELINE-PAGE 2026-08-02] 옛 기록이 위에 붙을 때 화면을 그대로 붙잡는다.
  //   위쪽에 노드가 생기면 그만큼 문서가 길어져 보던 자리가 아래로 밀린다 —
  //   CHAT-FOLD 의 '높이 붕괴'와 부호만 반대인 같은 문제다. 그래서 같은 방식으로 갚는다
  //   (새 스크롤 구현을 만들지 않는다 · 기존 HOLD·배지·전송하강 무접촉).
  //   ★판정 좌표는 §4-2 규약대로 앵커의 viewport rect.top 이다. scrollTop 은 늘어난
  //     높이만큼 당연히 변하므로 그것으로 성패를 가르지 않는다.
  const pendingOlderFixRef = useRef<{ h1: number; top1: number } | null>(null);
  const requestOlderTimeline = useCallback(() => {
    const root = chatScrollRef.current;
    if (root) pendingOlderFixRef.current = { h1: root.scrollHeight, top1: root.scrollTop };
    onLoadOlderTimeline?.();
  }, [onLoadOlderTimeline]);
  useLayoutEffect(() => {
    const fix = pendingOlderFixRef.current;
    const root = chatScrollRef.current;
    if (!fix || !root) return;
    const grew = root.scrollHeight - fix.h1;
    if (grew <= 0) return;            // 아직 안 붙었다 — 다음 렌더에서 다시 본다
    pendingOlderFixRef.current = null;
    root.scrollTop = fix.top1 + grew;
    if (import.meta.env.DEV) {
      console.log("[TIMELINE-PAGE][ANCHOR-FIX]", { h1: fix.h1, h2: root.scrollHeight, grew });
    }
  }, [storyPlan?.messages?.length]);

  // [CHAT-FOLD STEP 2] A + 1.5A 밖으로 올라간 컨텐츠만 접는다.
  //   root 는 채팅 스크롤 컨테이너, rootMargin top 을 FOLD_MARGIN 배만큼 넓혀
  //   '화면에서 사라짐'과 '한참 멀어짐'을 가른다 — 국장 눈앞에서는 접히지 않는다.
  useEffect(() => {
    const root = chatScrollRef.current;
    if (!root || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          const id = (e.target as HTMLElement).dataset.foldId;
          if (!id || e.isIntersecting) return;
          // 위로 벗어난 것만 접는다. 아래쪽(새 것이 오는 방향)은 건드리지 않는다.
          const rb = e.rootBounds;
          if (rb && e.boundingClientRect.bottom > rb.top) return;
          setFoldedIds((prev) => {
            if (prev.has(id)) return prev;
            const el = foldNodeRefs.current[id];
            // 접기 직전 높이를 여기서 잡아둔다 — 접힌 뒤에는 잴 수 없다.
            if (el) pendingFoldFixRef.current = { id, h1: el.getBoundingClientRect().height };
            const next = new Set(prev);
            next.add(id);
            return next;
          });
        });
      },
      { root, rootMargin: `${FOLD_MARGIN * 100}% 0px 0px 0px`, threshold: 0 },
    );
    Object.values(foldNodeRefs.current).forEach((el) => { if (el) io.observe(el); });
    return () => io.disconnect();
  }, [foldedIds, storyPlan?.messages?.length, proposalHistory.length]);
  // [STORY-GATE P3] 승인 관문 — 게이트 OFF면 enabled=false로 아무것도 바뀌지 않는다 (I-4)
  // [LAB-48] programId 는 프로젝트 id 와 화면 이름("__new__"·"upload"…)을 겸한다.
  //   LAB-21 이 Index.tsx 에 같은 가드를 넣었는데 이 호출부는 빠져 있었다 — 그래서
  //   프로젝트를 지우면 activeNavItem 이 "__new__" 로 바뀌고, 그 값이 여기로 흘러
  //   /api/story/__new__ 를 계속 노크했다(404 유령 폴). 유효 프로젝트가 아니면 폴하지 않는다.
  const storyGate = useStoryGate(
    programId?.startsWith("proj_") ? programId : null,
    appState === "complete",
  );
  const [storyViewKey, setStoryViewKey] = useState(0);       // '반영하기' 누를 때만 원고 재로드 (S5)
  const storyRefreshNonceRef = useRef(storyRefreshNonce);
  // [GATE-LOOP-01 2-1] 실재하는 무대 게이트 — 구판 hideEditUI는 정의만 있고 소비처가 0인
  // dead code였다(FLOWORDER-AUDIT 3-1 실측). 그래서 "승인 전엔 A/B를 내지 않는다"는 계약이
  // 문서에만 있었고, 판정 전(story=null) 구간엔 A/B가 기본 화면으로 떴다 — 위반 (1)의 원인.
  // 이제 이 값이 실제로 무대 택일을 지배한다(:finalContent).
  //   게이트 OFF → 현행 유지(무대)          로딩 중 → 무대 금지(아직 모른다)
  //   재편집 세션 → 스토리                  그 외 → 승인된 경우에만 무대
  const editStageAllowed = !storyGate.enabled
    ? true
    : storyGate.loading || reEditActive
      ? false
      : storyGate.approved;

  // [CHATLOG-STACK-01 1번] centerShowStory 제거 — 소비처 0.
  //   '무엇을 대신 보여줄까'(택일)를 판정하던 값이었다. 누적 구조에서는 택일이 없다:
  //   원고는 늘 있고, 무대(A/B)는 승인 시 그 아래로 붙는다(editStageAllowed).
  //   우측 패널의 rightStoryMode(Index)는 storyStageVisible을 계속 쓴다 — 그쪽은 옷 갈아입기다.
  useEffect(() => {
    if (storyRefreshNonceRef.current === storyRefreshNonce) return;
    storyRefreshNonceRef.current = storyRefreshNonce;
    void storyGate.reload();
    setStoryViewKey((k) => k + 1);
  }, [storyGate.reload, storyRefreshNonce]);
  // [R8 유령 4호 후속 2026-07-20] 새 제안 '세대'(컨설팅·재제안)가 생기면 원고 상태를 즉시
  // 새로고침한다. centerShowStory가 item_count 기반 storyStageVisible로 통일되며 구
  // `||!!proposals` 지름길이 사라졌으므로, 원고 카드가 폴링(≤10s)을 기다리지 않고 바로 뜨도록
  // 즉시성을 '데이터 새로고침'으로 대체한다. 기준은 proposal_id 시그니처라 A/B '확정'(id 불변)
  // 에는 반응하지 않는다 → 확정 왕복 중 무대는 흔들리지 않는다(검증 ②). stale 가드가 중복 흡수.
  const lastProposalSigRef = useRef<string | null>(null);
  useEffect(() => {
    const sig = proposals
      ? `${(proposals.A as any)?.proposal_id ?? "A"}|${(proposals.B as any)?.proposal_id ?? "B"}`
      : null;
    if (sig && sig !== lastProposalSigRef.current) {
      lastProposalSigRef.current = sig;
      void storyGate.reload();
    }
  }, [proposals, storyGate.reload]);
  // [STORY-TRACK-A A-5] 중앙 채팅창 = 표현(보기)만. 편집은 우측 조각맵으로 이전됐고,
  // 여기선 '활성 텍스트조각만' 읽기전용으로 보여준다(스토리 카드). 단일 진실(/ledger)
  // 공유 — 우측에서 활성/비활성 바꾸면 storyRefreshNonce/storyViewKey로 여기도 갱신.
  const [activeStoryItems, setActiveStoryItems] = useState<Array<{
    id: string;
    fragmentId: string;
    label: string;
    dialogue: string;
  stageDirection: string;
  }>>([]);
  const [activeStoryFragmentId, setActiveStoryFragmentId] = useState<string | null>(null);
  useEffect(() => {
    if (activeFragmentId) setActiveStoryFragmentId(activeFragmentId);
  }, [activeFragmentId]);
  useEffect(() => {
    // [CHATLOG-STACK-01 1번] centerShowStory 조건 제거 — 전사는 단계와 무관하게 유지한다.
    //   구판은 편집 단계(centerShowStory=false)에서 목록을 비워, 누적해도 빈 블록만 남았다.
    //   원고가 있으면(item_count>0) 항상 싣는다. 기록은 단계가 바뀌어도 사라지지 않는다.
    if (!programId || (storyGate.story?.item_count ?? 0) === 0) {
      setActiveStoryItems([]);
      return;
    }
    let dead = false;
    fetch(`/api/ledger/${encodeURIComponent(programId)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: StoryLedgerResponse | null) => {
        if (dead || !d?.ok) return;
        const ledgerItems = (d.items ?? []).filter((it) => !it.missing);
        const ledgerByFragmentId = new Map(ledgerItems.map((it) => [it.fragment_id, it]));
        const visibleItems = modeGateEnabled && fragments.length > 0
          ? fragments.map((f: any) => ledgerByFragmentId.get(f.fragment_id)).filter(Boolean) as StoryLedgerItem[]
          : ledgerItems
            .filter((it) => it.selected !== false && !it.removed)
            .sort((a, b) => (a.play_order ?? Number.MAX_SAFE_INTEGER) - (b.play_order ?? Number.MAX_SAFE_INTEGER));
        const rows = visibleItems
          .map((it) => {
            const source = sourceEntries.find((s) => s.source_id === it.source_id);
            const ordered = source?.fragments ?? [];
            const idx = ordered.findIndex((f: any) => f.fragment_id === it.fragment_id);
            const label = source?.label && idx >= 0 ? `${source.label}${idx + 1}` : "";
            return {
              id: it.timeline_item_id,
              fragmentId: String((it as any).fragment_id ?? (it as any).source_fragment_id ?? it.timeline_item_id),
              label,
              dialogue: fragmentTranscriptText(it),
              stageDirection: (it.stage_direction ?? "").trim(),
            };
          });
        setActiveStoryItems(rows);
      })
      .catch(() => { if (!dead) setActiveStoryItems([]); });
    return () => { dead = true; };
  }, [programId, storyGate.story?.item_count, storyViewKey, storyRefreshNonce, sourceEntries, modeGateEnabled, fragments]);
  // [UI-①] 업로드 스테이징 (null=비활성)
  const [stagedFiles, setStagedFiles] = useState<StagedMeta[] | null>(null);
  // [PERSON-PALETTE] 이름을 물어볼 얼굴 군집 + 방금 저장한 이름 안내
  const [pendingPersons, setPendingPersons] = useState<Array<{ person_id: string; face_url: string; appearances: number }>>([]);
  const [personNameDraft, setPersonNameDraft] = useState<Record<string, string>>({});
  const [personSavedNote, setPersonSavedNote] = useState<string | null>(null);
  // [PERSON-PALETTE→FLOW 국장지시] 팔레트가 흐름 밖 하단 고정이면 새 대화가 그 '위'에
  // 생기는 것처럼 보인다 — 첫 등장 시각을 잡아 흐름 속 아이템으로 흘려보낸다
  const paletteTsRef = useRef<number | null>(null);
  useEffect(() => {
    if ((pendingPersons.length > 0 || personSavedNote) && paletteTsRef.current === null) {
      paletteTsRef.current = Date.now();
    }
  }, [pendingPersons.length, personSavedNote]);

  useEffect(() => {
    // 프로젝트가 열리고 분석이 끝나 있으면 얼굴 스캔(멱등) 후 미명명 군집 조회
    // [CHAT-SKIN 2026-08-02 국장 지시] "초반에만" — 편집안이 한 번이라도 나온 뒤에는 묻지 않는다.
    //   구판은 appState 가 complete 이기만 하면 언제든 떴다. 그래서 한참 편집하다가
    //   뜬금없이 "이 사람 누구냐"가 끼어들었다(국장: "그러면 짜증나").
    //   인물 이름은 편집을 시작하기 전에 받아야 쓸모가 있다.
    if (!programId || !programId.startsWith("proj_") || appState !== "complete"
        || proposalHistory.length > 0) {
      setPendingPersons([]);
      return;
    }
    let alive = true;
    (async () => {
      try {
        await fetch(`/api/persons/scan/${programId}`, { method: "POST" });
        const res = await fetch(`/api/persons/pending?project_id=${programId}`);
        const data = await res.json();
        if (alive && data?.persons) setPendingPersons(data.persons);
        // 저장된 이름들을 편집 명령 문지기에 주입 ("은한이 나오는 장면만"이 명령으로 인식되게)
        const nres = await fetch(`/api/persons/names`);
        const ndata = await nres.json();
        if (alive && ndata?.names) setKnownPersonNames(ndata.names);
      } catch (e) {
        console.warn("[PERSON-PALETTE] scan/pending failed:", e);
      }
    })();
    return () => { alive = false; };
  }, [programId, appState, proposalHistory.length]);

  const savePersonName = async (pid: string) => {
    const name = (personNameDraft[pid] || "").trim();
    if (!name) return;
    try {
      const res = await fetch(`/api/persons/${pid}/name`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (data?.status === "OK") {
        setPendingPersons((prev) => prev.filter((p) => p.person_id !== pid));
        setPersonSavedNote(`${name}님으로 기억했어요 — 조각 ${data.tagged_fragments}개에 이름을 새겼습니다. 이제 "${name} 나오는 장면만"처럼 말씀하실 수 있어요.`);
      }
    } catch (e) { console.warn("[PERSON-PALETTE] name failed:", e); }
  };

  const rejectPerson = async (pid: string) => {
    try {
      await fetch(`/api/persons/${pid}`, { method: "DELETE" });
      setPendingPersons((prev) => prev.filter((p) => p.person_id !== pid));
    } catch (e) { console.warn("[PERSON-PALETTE] reject failed:", e); }
  };

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

  // [INTENT-ROUTER Phase 0] 모든 채팅의 단일 진입점(향후 인텐트 라우터 삽입 지점).
  // 검색 의도를 상태 무관 우선 처리 → 컨설팅 중에도 "찾아줘/불러와"가 동작.
  const dispatchCommand = useCallback(async (rawInput: string) => {
    const raw = rawInput.trim();
    if (!raw) return;

    // "start"는 분석 시작 (비컨설팅 한정 — 컨설팅 흐름 보존)
    if (!storyPlan && raw.toLowerCase() === "start") {
      if (onAnalyze) await onAnalyze();
      return;
    }

    // [SHOW 2026-07-05] 컨설팅 모드에서는 검색 가로채기 금지 — 조회/편집 판단은
    // 종업원(route-edit)이 한다. 구식 가로채기는 결과를 흐름 밖 상단 패널에 띄우고
    // 사용자 메시지를 대화·저장에서 누락시키던 원인("다 사라짐" 증상).
    if (storyPlan) {
      onConsultation?.(raw);
      return;
    }

    // [FRAGMENT-SEARCH] (레거시 입력구 한정) 검색 의도면 조각 검색 먼저.
    try {
      setFragSearch({ query: raw, searching: true, results: [], done: false });
      // [LAB-50 ④] 현재 프로젝트로 검색 스코프 한정 — videoService 는 이미 program_id 를
      //   실어 보내는데 호출부가 넘기지 않아 전 아카이브를 뒤지고 있었다.
      const sr = await videoService.chatFragmentSearch(raw, {
        top_k: 12,
        program_id: programId ?? undefined,
      });
      if (sr.is_search) {
        setFragSearch({ query: sr.query, searching: false, results: sr.results, done: true });
        return;
      }
      setFragSearch(null);
    } catch (e) {
      console.warn("[CenterPanel] fragment search failed, fallback to chat:", e);
      setFragSearch(null);
    }
    const parsedDirection = parseDirectionFromText(raw);
    if (parsedDirection) {
      onReproposal?.(parsedDirection);
    } else {
      // [LAB-50 ①] 판별 실패의 기본값을 '편집'에서 '상담'으로 반전한다.
      //   구판은 파싱에 실패해도 원문을 그대로 재제안으로 보냈다(onReproposal(raw)).
      //   그래서 "분석중인건가?" 같은 질문이 편집 지시로 오배송돼, 조각 0개 상태에서
      //   제안 생성을 태우고 빈 결과로 돌아왔다(실측 2026-07-30: sequenceLength A:0 B:0).
      //   모르면 사용자에게 되묻는 쪽이 맞다 — 위 713행의 consultation 경로를 그대로 쓴다.
      onConsultation?.(raw);
    }
  }, [storyPlan, onAnalyze, onConsultation, onReproposal]);

  const handleSubmitConsultation = useCallback(() => {
    const text = consultationInput.trim();
    if (!text) return;
    setConsultationInput("");
    resetConsultationTextarea();
    // [CHAT-FLOW-2 2026-08-02] 내가 보냈으면 내려간다 (국장 확정).
    //   남이 보낸 것이 도착할 때는 안 끌려간다(INV-1, 현행 HOLD+배지 그대로).
    //   전송은 다르다 — "대화로 돌아간다"는 사용자 의사표시이므로 억지 이동이 아니다.
    //   ★ 배지 클릭이 쓰는 그 함수를 그대로 부른다. 새 스크롤 구현을 만들지 않는다.
    //     이 함수 하나가 HOLD 해제(chatAtBottomRef·chatUserGestureRef·chatHasNew)와
    //     하단 이동을 함께 한다 — 해제 코드를 따로 쓰지 않는 이유다.
    scrollChatToBottom();
    dispatchCommand(text);
  }, [consultationInput, dispatchCommand, resetConsultationTextarea, scrollChatToBottom]);

  // [F 스크롤 앵커] 새 메시지/새 제안 세대가 실제로 '늘어날' 때만 하단으로 흐른다.
  // 과거 제안 소환(activeProposalEntryId 변경)은 스크롤을 끌어내리지 않는다 — 무대가
  // 중간 슬롯으로 이동하는데 하단으로 튕기던 '흘러내림'을 절단. 소환 고지 메시지는
  // length 증가로 자연히 하단 정렬(그건 최신 사건이므로 정상).
  // [TIMELINE-PAGE 2026-08-02] '늘었다'가 아니라 '아래에 붙었다'로 판정한다.
  //   실측 사고(이 차수 1회차): 이전 기록 303행을 위에 붙였더니 이 효과가 개수 증가만
  //   보고 '새 메시지 도착'으로 읽어 settleChatToBottom 을 태웠다 —
  //   앵커 viewport rect.top 이 42 -> -12211 (delta -12253px). 화면을 통째로 빼앗겼다.
  //   길이는 위에 붙여도 늘고 아래에 붙여도 는다. 구분하는 것은 ★맨 끝의 정체다.
  const _prevChatLenRef = useRef({ msgs: 0, gens: 0, activeGen: null as string | null,
                                   lastMsgId: null as string | null });
  useEffect(() => {
    const msgList = storyPlan?.messages ?? [];
    const msgs = msgList.length;
    const lastMsgId = msgs ? String((msgList[msgs - 1] as any)?.id ?? "") : null;
    const gens = proposalHistory.length;
    const activeGen = activeProposalEntryId ?? null;
    const prev = _prevChatLenRef.current;
    // 개수가 늘고 ★맨 끝이 바뀌었을 때만 새 사건이 아래에 도착한 것이다.
    const msgsGrew = msgs > prev.msgs && lastMsgId !== prev.lastMsgId;
    // [LAB-38 C 2회차] 세대 증가는 **무대가 그 세대로 이동했을 때만** 하단 추종한다.
    //   실측(SCROLL_XRAY 2026-07-29): 승인 후 백그라운드 생성 도착 순간 이 효과의 gens
    //   트리거가 settleChatToBottom을 발화, 채팅 컬럼(chatScrollRef)이 새 카드로
    //   smooth 활강(34134→35371px)해 재생 중 화면을 빼앗았다. LAB-37이 무대를
    //   제자리에 붙잡았으므로(출처 게이트) 스크롤도 같은 출처를 따른다:
    //   무대 이동 없는 세대 증가(백그라운드 도착)는 카드만 쌓고 '새 내용' 배지만 켠다.
    //   메시지 증가(대화 사건)는 기존대로 추종 — 소환(activeGen만 변경)도 기존대로 무추종.
    const stageMoved = activeGen !== prev.activeGen;
    const gensGrew = gens > prev.gens;
    _prevChatLenRef.current = { msgs, gens, activeGen, lastMsgId };
    const grew = msgsGrew || (gensGrew && stageMoved);
    if (!grew) {
      if (gensGrew) setChatHasNew(true); // 도착 사실 알림은 유지 — 화면만 빼앗지 않는다
      return;
    }
    // [CHATSCROLL-FIX-01] 하단 근처일 때만 따라간다 — 위에서 읽는 중이면 알림만.
    if (chatAtBottomRef.current || isChatNearBottom()) {
      chatAtBottomRef.current = true;
      // [CHATSCROLL-FIX-02] 늦게 로드되는 썸네일이 높이를 늘려도 하단에 붙어 있게.
      settleChatToBottom();
    } else {
      import.meta.env.DEV && console.log("[CHATSCROLL][HOLD]", {
        msgs, gens, reason: "user_scrolled_up",
        // [CHATSCROLL-FIX-02] 손짓 없이 HOLD 가 찍히면 그건 오판이다 — 근거를 남긴다.
        gesture: chatUserGestureRef.current,
      });
      setChatHasNew(true);
    }
  }, [storyPlan?.messages?.length, proposalHistory.length, activeProposalEntryId,
      isChatNearBottom, settleChatToBottom]);

  const setActivePlayerSafe = useCallback((player: "A" | "B" | null) => {
    activePlayerRef.current = player;
    setActivePlayer(player);
  }, []);

  const [isPlayingA, setIsPlayingA] = useState(false);
  const [isSrcLoadingA, setIsSrcLoadingA] = useState(false);
  const [isSrcLoadingB, setIsSrcLoadingB] = useState(false);
  const [isPlayingB, setIsPlayingB] = useState(false);
  const [chatValue, setChatValue] = useState("");
  // [FRAGMENT-SEARCH] 채팅 자연어 조각 검색 결과
  const [fragSearch, setFragSearch] = useState<{
    query: string;
    searching: boolean;
    results: any[];
    done: boolean;
  } | null>(null);
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

  const isProposalEmpty = useCallback((proposal: any): boolean => {
    if (!proposal) return false;
    const keyCount = Array.isArray(proposal.key_fragments) ? proposal.key_fragments.length : null;
    const sequenceCount = Array.isArray(proposal.sequence) ? proposal.sequence.length : null;
    if (keyCount === 0) return true;
    return keyCount === null && sequenceCount === 0;
  }, []);

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

  // [SINGLEPLAY-EXPAND-01] 단일 조각 재생의 구간 큐. **시퀀스 계약(isSeq)과 별개**로 둔다 —
  //   단일 재생은 isSeq=false·seqIdx=-1 을 유지해야 하므로 시퀀스 refs를 빌려 쓸 수 없다.
  //   구간 자체는 시퀀스와 같은 expandTileToItems 결과다 (전개 로직 2벌 금지).
  const singleSegsARef = useRef<Fragment[]>([]);
  const singleIdxARef = useRef<number>(-1);
  const singleSegsBRef = useRef<Fragment[]>([]);
  const singleIdxBRef = useRef<number>(-1);

  const seqTotalSecARef = useRef<number>(0);
  const seqElapsedSecARef = useRef<number>(0);
  const seqTotalSecBRef = useRef<number>(0);
  const seqElapsedSecBRef = useRef<number>(0);
  const isUserSeekingARef = useRef(false);
  const isUserSeekingBRef = useRef(false);
  const isDraggingProposalSeekARef = useRef(false);
  const isDraggingProposalSeekBRef = useRef(false);
  const isSeekingRefA = useRef(false);
  const isSeekingRefB = useRef(false);

  const [playerSrcA, setPlayerSrcA] = useState<string | null>(null);
  const [playerSrcB, setPlayerSrcB] = useState<string | null>(null);
  const pendingLocalTimeARef = useRef<number | null>(null);
  const pendingLocalTimeBRef = useRef<number | null>(null);

  // [DUAL_PLAY_GUARD] stale event 방지용 세션 ID
  const playSessionARef = useRef<number>(0);
  const playSessionBRef = useRef<number>(0);

  const lastReportedActiveIdRef = useRef<string | null>(null);

  // ── [PLAYSTABILITY-FIX-01 1번] 두 신호를 출처로 가른다 ────────────────────────
  //   (a) 시퀀스 진행 보고 = "지금 이 조각 재생 중" — 표시용. 재생 제어 금지.
  //   (b) 사용자 선택      = "이 조각 틀어줘"     — 시퀀스 중단 + 단일 재생.
  // 구판은 둘이 같은 경로(selectedFragment)로 흘러, 시퀀스가 다음 조각을 보고할 때마다
  // 선택 effect가 stopSeq를 불러 **시퀀스가 자기를 죽였다** — 실측: 2번째 조각에서 정지
  // (BOUNDARY_HIT에 seqIdx=-1·isSeq=false, PLAYFRAG 중복 2회).
  // 상태(isSeq)로 가르면 '재생 중 사용자 클릭'까지 막히므로, **출처를 표시**해서 가른다.
  const seqAutoReportedFidRef = useRef<string | null>(null);

  /** (a) 시퀀스가 스스로 진행을 알린다 — 이 보고로 촉발된 선택 변경은 재생을 제어하지 않는다. */
  const reportSeqProgress = useCallback((id: string | null) => {
    seqAutoReportedFidRef.current = id;
    if (id !== lastReportedActiveIdRef.current) {
      lastReportedActiveIdRef.current = id;
      onActiveFragmentChange?.(id, "sequence");   // 표시용 — 스크롤로 따라가지 않는다
    }
  }, [onActiveFragmentChange]);

  /** (b) 그 밖의 보고(사용자 클릭·seek·정지) — 출처 표시를 지운다. */
  const reportActiveId = useCallback((id: string | null) => {
    seqAutoReportedFidRef.current = null;
    if (id !== lastReportedActiveIdRef.current) {
      lastReportedActiveIdRef.current = id;
      onActiveFragmentChange?.(id, "user");
    }
  }, [onActiveFragmentChange]);

  /** [PLAYSTABILITY-FIX-01 2번-b] onEnded는 경계감시의 **보조**다 — 이미 진행했으면 또 진행하지 않는다.
   *  진행 경로가 둘(경계감시 :1182 / onEnded :2030·:2306)인데 4번 클램프로 seqEnd가 파일 EOF와
   *  정확히 같아지자(A idx3 = 17.995465) 둘이 동시에 발동했다 — 실측: BOUNDARY_HIT 없이 PLAYFRAG가
   *  4ms 간격 2건, idx4(SF_BD21A3)가 4ms만 재생되고 건너뛰어졌다.
   *  시각(디바운스)이 아니라 **재생 위치**로 가른다: 지금 미디어가 시퀀스가 믿는 조각의 끝에
   *  실제로 도달했을 때만 보조 진행을 허용한다. 경계감시가 방금 진행했으면 endRef는 이미
   *  '다음 조각의 끝'이고 currentTime은 그 조각의 시작 근처이므로 여기서 걸린다.
   */
  const endedShouldAdvance = useCallback(
    (v: HTMLVideoElement | null, endRef: React.MutableRefObject<number>, player: "A" | "B") => {
      const end = endRef.current;
      if (!v || !(end > 0)) return false;
      const ok = v.currentTime >= end - 0.25;
      if (!ok) {
        import.meta.env.DEV && console.log(`[SEQ_ENDED_SKIP_${player}]`, {
          currentTime: v.currentTime, seqEnd: end, reason: "boundary_watch_already_advanced",
        });
      }
      return ok;
    },
    []
  );

  const cleanupPendingLoadHandler = useCallback((player: "A" | "B") => {
    const ref = player === "A" ? videoRefA : videoRefB;
    const pending = player === "A" ? pendingLoadHandlerARef : pendingLoadHandlerBRef;

    if (ref.current && pending.current) {
      ref.current.removeEventListener("loadeddata", pending.current);
      pending.current = null;
    }
  }, []);

  // [R2 정지 정밀화] span 경계 감시 rAF 핸들 (A/B 각 1개) — 재생 정지·전환 시 반드시 취소.
  const boundaryRafARef = useRef<number | null>(null);
  const boundaryRafBRef = useRef<number | null>(null);
  // [R2 가짜 발화 차단] 소스 교체(pending) 경로의 지연 무장용 — seek 착지 전 구 소스
  // currentTime이 새 span end와 비교돼 span을 건너뛰는 경합을 막는다 (검증 중 실측된 결함).
  const pendingSeqEndARef = useRef<number | null>(null);
  const pendingSeqEndBRef = useRef<number | null>(null);
  const stopBoundaryWatch = useCallback((player: "A" | "B") => {
    const ref = player === "A" ? boundaryRafARef : boundaryRafBRef;
    if (ref.current !== null) {
      cancelAnimationFrame(ref.current);
      ref.current = null;
    }
  }, []);

  // [DUAL_PLAY_GUARD] 반대편 player 즉시 hard-stop
  const stopOtherPlayer = useCallback((active: "A" | "B") => {
    if (active === "A") {
      // B를 완전 정지
      stopBoundaryWatch("B");                // [R2] 경계 감시 루프 취소 (누수 금지)
      pendingSeqEndBRef.current = null;      // [R2] 지연 무장 잔재 소거
      playSessionBRef.current += 1;          // invalidate stale B events
      pendingLocalTimeBRef.current = null;   // pending seek 무효화
      isSeqBRef.current = false;
      seqIdxBRef.current = -1;
      seqEndBRef.current = -1;
      if (videoRefB.current && !videoRefB.current.paused) {
        videoRefB.current.pause();
        DEBUG_LOG && console.log("[DUAL_PLAY_GUARD] B paused by A");
      }
      setIsPlayingB(false);
    } else {
      // A를 완전 정지
      stopBoundaryWatch("A");                // [R2] 경계 감시 루프 취소 (누수 금지)
      pendingSeqEndARef.current = null;      // [R2] 지연 무장 잔재 소거
      playSessionARef.current += 1;          // invalidate stale A events
      pendingLocalTimeARef.current = null;   // pending seek 무효화
      isSeqARef.current = false;
      seqIdxARef.current = -1;
      seqEndARef.current = -1;
      if (videoRefA.current && !videoRefA.current.paused) {
        videoRefA.current.pause();
        DEBUG_LOG && console.log("[DUAL_PLAY_GUARD] A paused by B");
      }
      setIsPlayingA(false);
    }
  }, [stopBoundaryWatch]);

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
      // [R1 #34] 문자열만 수용 — 객체/undefined가 오면 조용히 죽지 않고 명시적 거부.
      // (RED 1: key_fragments 소진 시 sequence 객체가 흘러들어 fragId.match 크래시 → 앱 먹통)
      if (typeof fragId !== "string" || !fragId) {
        console.error("[VIDEO_URL_RESOLVE][REJECT] fragId가 문자열이 아님 — 재생원 해석 거부", { fragId });
        return null;
      }
      if (sourceEntries.length === 0) return videoUrl ?? null;

      const allPossibleFragments = [
        ...(fragments || []),
        ...(sourceFragments || []),
        ...sourceEntries.flatMap(e => e.fragments || [])
      ];

      const targetFrag = allPossibleFragments.find(f => collectFragmentAliases(f).includes(fragId));
      const queryAliases = targetFrag ? collectFragmentAliases(targetFrag) : [fragId];

      for (const entry of sourceEntries) {
        for (const f of entry.fragments) {
          const fAliases = collectFragmentAliases(f);
          const hasMatch = fAliases.some(alias => queryAliases.includes(alias));
          if (hasMatch) {
            const resolvedVideoUrl = entry.video_url || videoUrl || null;
            DEBUG_LOG && import.meta.env.DEV && console.log(`[VIDEO_URL_RESOLVE] fragId=${fragId} matchedAlias=${f.fragment_id} resolvedVideoUrl=${resolvedVideoUrl} fallbackUsed=0`);
            return resolvedVideoUrl;
          }
        }
      }

      // [PLAYBACK-ORPHAN-A] fragId alias 매칭 실패 = 고아 제안(재분석으로 semantic 조각 재생성되어
      // 제안 시퀀스의 옛 fragId가 사라진 상태). 전역 1번영상으로 떨어지지 않고,
      // fragId에 박힌 source_id(SF_<hash>_SRC_<srcid>)로 해당 소스 영상을 해석한다.
      const sidMatch = fragId.match(/SRC_[0-9A-Za-z]+/);
      if (sidMatch) {
        const sid = sidMatch[0];
        const srcEntry = sourceEntries.find(e => e.source_id === sid);
        if (srcEntry && srcEntry.video_url) {
          DEBUG_LOG && import.meta.env.DEV && console.log(`[VIDEO_URL_RESOLVE] fragId=${fragId} matchedAlias=null resolvedBy=source_id:${sid} resolvedVideoUrl=${srcEntry.video_url} fallbackUsed=2`);
          return srcEntry.video_url;
        }
      }

      // [PLAYBACK-ORPHAN-B 2026-07-05] sourceEntries에도 없는 소스 = 하이드레이션 이후
      // 합류한 소스(세션 중 아카이브 포함 등). fid의 SRC 토큰으로 업로드 경로 직접 구성
      // (업로드 파일명 = {source_id}.mp4 실측 규칙). 잘못된 영상 대체보다 언제나 낫다.
      if (sidMatch) {
        const directUrl = `/static/uploads/${sidMatch[0]}.mp4`;
        DEBUG_LOG && import.meta.env.DEV && console.log(`[VIDEO_URL_RESOLVE] fragId=${fragId} matchedAlias=null resolvedBy=fid-direct resolvedVideoUrl=${directUrl} fallbackUsed=2.5`);
        return directUrl;
      }

      // source_id 로도 못 찾음 → 전역 1번영상 반복 금지(클립별 오재생 방지). null 반환, 상위에서 처리.
      DEBUG_LOG && import.meta.env.DEV && console.log(`[VIDEO_URL_RESOLVE] fragId=${fragId} matchedAlias=null source_id 해석 실패 -> null fallbackUsed=3`);
      return null;
    },
    [fragments, sourceFragments, sourceEntries, videoUrl]
  );

  const getVideoUrlForProposal = useCallback(
    (proposalKey: "A" | "B"): string | null => {
      const p = proposals?.[proposalKey];
      if (isProposalEmpty(p)) return null;
      // [R1 #34] sequence(객체 배열) 폴백 절단 — key_fragments가 비면 null.
      // 조각맵이 비었으면 비었다고 말한다. 옛 시퀀스를 꺼내오지 않는다 (#3·#28 계열, 헌장 §5).
      const firstFragId = p?.key_fragments?.[0];
      if (!firstFragId) return null;
      return getVideoUrlForFrag(firstFragId);
    },
    [proposals, getVideoUrlForFrag, isProposalEmpty]
  );

  // [PROPOSAL_PREVIEW] proposal.preview_url 우선, 없으면 fragment URL fallback
  // 만약 현재 제안서가 확정되어 편집 중(committedProposalId)이거나, 이미 편집한 상태(customEditFragments 존재)인 경우
  // preview_url을 무시하고 dynamic sequence로 재생하도록 강제
  const previewUrlA: string | null = !isProposalEmpty(proposals?.A) && (proposals?.A as any)?.preview_url && committedProposalId !== "A" && !(proposals?.A as any)?.customEditFragments
    ? normalizeMediaUrl((proposals.A as any).preview_url)
    : null;
  const previewUrlB: string | null = !isProposalEmpty(proposals?.B) && (proposals?.B as any)?.preview_url && committedProposalId !== "B" && !(proposals?.B as any)?.customEditFragments
    ? normalizeMediaUrl((proposals.B as any).preview_url)
    : null;

  // [RENDER-LOOP-A1] 메모이즈 — onTimeUpdate→setProposalTime 재렌더마다 getVideoUrlForProposal
  // (→getVideoUrlForFrag+console.log)이 재실행되어 로그 폭주·메인스레드 점유하던 핫패스 차단.
  const playerVideoUrlA = useMemo(
    () => isProposalEmpty(proposals?.A) ? null : previewUrlA ?? getVideoUrlForProposal("A") ?? videoUrl ?? null,
    [previewUrlA, getVideoUrlForProposal, videoUrl, proposals, isProposalEmpty]
  );
  const playerVideoUrlB = useMemo(
    () => isProposalEmpty(proposals?.B) ? null : previewUrlB ?? getVideoUrlForProposal("B") ?? videoUrl ?? null,
    [previewUrlB, getVideoUrlForProposal, videoUrl, proposals, isProposalEmpty]
  );

  // ── [PUNCH-1 R1] 펀치인 = 화면 변환. 재생 경로에도 같은 진실을 건다 ──────────────
  //   확정된 안은 previewUrl이 null이라(위 1015행) 렌더된 mp4를 쓰지 않는다.
  //   그래서 백엔드 ffmpeg 줌이 화면에 도달하지 못했다(국장 "차이를 모르겠다").
  //   좌표를 새로 만들지 않고 백엔드 punch_spec(진실 하나)을 그대로 받아 CSS로 건다.
  const [punchSpecs, setPunchSpecs] = useState<Record<string, { at: number; zoom: number; basis: string }>>({});
  const [punchRampSec, setPunchRampSec] = useState(0.12);
  const [punchScaleA, setPunchScaleA] = useState(1);
  useEffect(() => {
    if (!programId) return;
    let dead = false;
    (async () => {
      try {
        const r = await fetch(`${videoService.API_BASE_URL}/punch/${programId}`).then((x) => x.json());
        if (dead || !r?.ok) return;
        setPunchSpecs(r.specs || {});
        if (typeof r.ramp_sec === "number") setPunchRampSec(r.ramp_sec);
        console.log("[PUNCH] specs 수신", { count: r.count, approval_id: r.approval_id, mode_technique: r.mode_technique });
      } catch (e) {
        console.log("[PUNCH] specs 수신 실패 (비차단)", e);
      }
    })();
    return () => { dead = true; };
  }, [programId]);
  /** A(punch_in)만 확대한다. B(as_is)는 항상 1배 — 여기가 A/B가 갈리는 유일한 지점. */
  const applyPunchA = useCallback((curTimeSec: number) => {
    const frag: any = seqFragsARef.current?.[seqIdxARef.current];
    const spec = frag ? punchSpecs[String(frag.fragment_id ?? "")] : undefined;
    const next = spec && curTimeSec >= spec.at ? spec.zoom : 1;
    setPunchScaleA((prev) => (prev === next ? prev : next));
  }, [punchSpecs]);
  // 재생이 끝나면 원래 배율로 — 확대된 채 멈춰 있으면 다음 재생의 첫 조각이 오염된다.
  useEffect(() => { if (!isPlayingA) setPunchScaleA(1); }, [isPlayingA]);

  /**
   * [SEQFRAGS-INV-01 2번] 타일 1개 -> 재생 항목 N개 전개. **해석과 시퀀스 구성의 분리 중 '전개' 축**.
   *   조각은 자동 분할되지 않는다(헌장 §6) — 타일은 계속 1개다. 다만 내부 제외(중간삭제)가 있으면
   *   그 조각을 "생존 구간 수"만큼 이어 틀어야 지운 구간이 다시 들리지 않는다(국장 판정 ①-나, 05723b0f).
   *   실측(Merope): fragment_edit_state.excluded_ranges_json 이 SF_88B1F4=1구간, SF_BC1A6C=2구간
   *   -> 슬롯 2개·3개. 11타일이 14슬롯이 되는 유일한 근원이 이것이다(alias 1:N·파생조각·조인 아님).
   */
  const expandTileToItems = useCallback((f: any): Fragment[] => {
    const spans: Array<[number, number]> | null =
      Array.isArray(f?.spans_ms) && f.spans_ms.length > 1 ? f.spans_ms : null;
    if (!spans) return [f];   // span 0·1개 = 타일 좌표가 이미 그 구간
    return spans.map(([s, e]) => ({
      ...f,
      start_sec: s / 1000, end_sec: e / 1000,
      start_time: s / 1000, end_time: e / 1000,
      start_frame: Math.round((s / 1000) * 30),
      end_frame: Math.round((e / 1000) * 30),
      duration: Math.max(1, Math.round(((e - s) / 1000) * 30)),
    })) as Fragment[];
  }, []);

  /** [SEQ_INV-BASE] 직전 buildSeqFrags가 어느 진실에서 재생 배열을 만들었는가.
   *  렌더가 아니라 buildSeqFrags 호출 안에서만 쓰며, startSeq가 같은 tick에 바로 읽는다. */
  const seqOriginRef = useRef<"story" | "proposal">("proposal");

  /** 계약 원본(승인 시퀀스)의 fid 순서. 런타임 실측: proposals[X].key_fragments 11건, A·B 동일. */
  const contractFidsOf = useCallback((proposalKey: "A" | "B"): string[] => {
    const p = proposals?.[proposalKey] as any;
    const raw = Array.isArray(p?.key_fragments) ? p.key_fragments
      : Array.isArray(p?.sequence) ? p.sequence : [];
    return raw
      .map((x: any) => String(typeof x === "string" ? x : (x?.fragment_id ?? x?.id ?? "")))
      .filter(Boolean);
  }, [proposals]);

  /**
   * [SEQFRAGS-INV-01 3번] 재생 계층 INV 검산기. 재생 시작 직전 최후 방어선.
   *   판정 기준은 **고유 fid의 집합과 순서**다 — 슬롯 수가 아니다.
   *   슬롯 수는 내부 제외 전개로 정당하게 늘 수 있고(위 expandTileToItems), 그걸 위반으로 보면
   *   사용자가 지운 구간을 되살리게 된다. 그래서 늘어난 슬롯은 위반이 아니라 **명시 신고**한다.
   *   집합·순서가 어긋나면 계약 원본으로 재구성하고, 해석 실패 조각은 건너뛰되 남긴다.
   */
  const enforceSeqContract = useCallback((proposalKey: "A" | "B", frags: Fragment[]): Fragment[] => {
    // [SEQ_INV-BASE] 기준선은 **재생 배열을 만든 그 출처**여야 한다.
    //   구판은 출처와 무관하게 프론트 메모리 proposals(key_fragments)를 계약으로 삼았다.
    //   그런데 조각맵 경로(buildSeqFrags :1262)는 A·B가 같은 스토리 파생이고, 스토리의 권위는
    //   ui_state.story.fids — Export(ledger EDL)가 쓰는 바로 그 진실이다. 제안 재생성은
    //   승인 직후 await 없이 던져지므로(Index.tsx:246), 그 사이 재생하면 **낡은 제안**이
    //   계약 노릇을 하며 사용자가 방금 정한 스토리를 덮어썼다(실측 Acrux: 4조각 -> 14조각 복원).
    //   진실이 둘이면 한쪽은 반드시 거짓말을 한다 — 기준선을 출처에 맞춘다.
    if (seqOriginRef.current === "story") {
      const story = (storyFids ?? []).map(String).filter(Boolean);
      const played = frags
        .map((f: any) => String(f?.fragment_id ?? ""))
        .filter((id, i, a) => id && (i === 0 || a[i - 1] !== id));
      if (story.length && (story.length !== played.length || story.some((id, i) => id !== played[i]))) {
        // 신고만 한다. 재구성하지 않는다 — 스토리 경로에서 재생은 조각맵의 순수 파생이고,
        // 조각·순서는 사용자 결정이다(INV-0). 07-26 A/B 분열 보호는 아래 제안 경로에 그대로 남는다.
        console.warn(`[SEQ_INV][STORY] ${proposalKey} 스토리와 재생이 다름 — 사용자 결정 우선, 재구성 안 함`, {
          story_n: story.length, played_unique_n: played.length, played_slots: frags.length,
        });
      }
      return frags;
    }
    const contract = contractFidsOf(proposalKey);
    if (contract.length === 0) {
      console.warn(`[SEQ_INV][NO_CONTRACT] ${proposalKey} 계약 원본(key_fragments)이 없어 판정 불가 — 슬롯 ${frags.length} 그대로 재생`);
      return frags;
    }
    // 연속 반복(=전개된 같은 조각)을 접어 고유 fid 순서를 얻는다.
    const collapsed = frags
      .map((f: any) => String(f?.fragment_id ?? ""))
      .filter((id, i, a) => id && (i === 0 || a[i - 1] !== id));
    const same = collapsed.length === contract.length && collapsed.every((id, i) => id === contract[i]);

    if (same) {
      if (frags.length !== contract.length) {
        const per: Record<string, number> = {};
        frags.forEach((f: any) => {
          const id = String(f?.fragment_id ?? "");
          per[id] = (per[id] ?? 0) + 1;
        });
        console.log(`[SEQ_INV][EXPAND] ${proposalKey} 내부 제외 전개 — 계약 ${contract.length}조각 / 재생 슬롯 ${frags.length}`,
          Object.fromEntries(Object.entries(per).filter(([, n]) => n > 1)));
      }
      return frags;
    }

    console.error(`[SEQ_INV][RESTORE] ${proposalKey} 재생 시퀀스가 계약과 다름 — 계약 원본으로 재구성`, {
      expected_n: contract.length, got_unique_n: collapsed.length, got_slots: frags.length,
      added: collapsed.filter((id) => !contract.includes(id)).slice(0, 5),
      removed: contract.filter((id) => !collapsed.includes(id)).slice(0, 5),
      order_only: collapsed.length === contract.length,
    });

    const byFid = new Map<string, any>();
    (fragments ?? []).forEach((f: any) => {
      const id = String(f?.fragment_id ?? "");
      if (id && !f.excluded && !byFid.has(id)) byFid.set(id, f);
    });
    const missing: string[] = [];
    const rebuilt = contract.flatMap((fid) => {
      const tile = byFid.get(fid) ?? allSourceFragments.find((f) => f.fragment_id === fid);
      if (!tile) { missing.push(fid); return []; }
      return expandTileToItems(tile);
    });
    if (missing.length) {
      console.warn(`[SEQ_INV][SKIP] ${proposalKey} 계약 조각 해석 실패 ${missing.length}건 — 건너뜀`, missing);
    }
    console.log(`[SEQ_INV][RESTORED] ${proposalKey} 고유 ${new Set(rebuilt.map((f: any) => f.fragment_id)).size} / 슬롯 ${rebuilt.length}`);
    return rebuilt;
  }, [contractFidsOf, fragments, allSourceFragments, expandTileToItems, storyFids]);

  const buildSeqFrags = useCallback(
    (proposalKey: "A" | "B"): Fragment[] => {
      // [#28 재생원 일원화 (가') 국장 승인 2026-07-17] 조각맵에 깔린 제안의 라이브 재생 =
      // 조각맵 상태(fragments prop)의 순수 파생 — 보류 제외·순서·트림이 이미 반영된 배열.
      // 서버 ledger EDL 클립 선점(구 backendEdlApplies 1순위)·저장된 제안 시퀀스
      // (customEditFragments 캐시·resolved_aliases·key_fragments)로 떨어지지 않는다:
      // 세 진실(EDL 15클립·제안 9키·조각맵 1타일)이 갈라질 때 화면과 재생이 어긋나던 병
      // 절단 (헌장 §5 — 화면과 재생은 같은 진실). 빈 조각맵이면 빈 배열 — 옛 시퀀스 부활 금지.
      // 내부 제외 정밀 스킵: 타일 동봉 spans_ms(05723b0f, ms 정수)를 소비해 span당 재생
      // 항목 1개로 전개 — 근사 후퇴 없음 (e96d8d18 스킵·끝정지·재재생 자산 보존).
      // [SEQFRAGS-INV-02 국장 결정 (가)] 편집 상태는 **스토리에 속한다** — A도 B도 같은 편집을 받는다.
      //   구판은 `proposalKey === (displayProposalId ?? committedProposalId)` 로 갈라서 선택된 안만
      //   편집 반영본으로 재생하고 나머지는 저장본(anchor 좌표)으로 재생했다.
      //   실측(Merope A idx7 SF_BC1A6C): 저장본 13.21~31.2 를 연속 재생 — 트림(15.35~29.31) 무시,
      //   내부 제외 2구간 부활. 같은 잣대로 A/B를 비교할 수 없고 A를 확정하면 편집이 사라진다.
      //   ★저장본에 좌표를 굽지 않는다(진실 이중화 금지) — 재생 시점에 조각맵 상태에서 파생한다.
      const tiles = (fragments ?? []).filter((f) => !f.excluded);
      if (tiles.length > 0) {
        seqOriginRef.current = "story";
        return tiles.flatMap(expandTileToItems);
      }
      seqOriginRef.current = "proposal";
      // 빈 조각맵: 표시 중인 안은 옛 시퀀스 부활 금지(헌장 §5) — 빈 배열 그대로.
      if (proposalKey === (displayProposalId ?? committedProposalId)) {
        return [];
      }

      // 조각맵에 깔리지 않은(비표시) 제안 중 확정본은 서버 EDL 클립으로 재생 (기존 경로 보존).
      const backendEdlApplies =
        !!programId &&
        programId.startsWith("proj_") &&
        exportClips.length > 0 &&
        proposalKey === (committedProposalId ?? "B");
      if (backendEdlApplies) {
        return exportClips.map((c) => physicalClipToFragment(c, sourceLabelMap));
      }

      const p = proposals?.[proposalKey];
      if (!p) return [];
      if (isProposalEmpty(p)) return [];

      // 조각맵에 깔리지 않은(비표시) 제안의 비교 재생 — 저장본 시퀀스 사용은 정당.
      const cachedFrags = (p as any)?.customEditFragments;
      if (cachedFrags && cachedFrags.length > 0) {
        return cachedFrags.filter((f: any) => !f.excluded);
      }

      // [STEP 10-K-C1-R39-R1] resolved_aliases가 있으면 우선적으로 사용하여 가드가 적용된 데이터를 재생에 반영
      const resolved = (p as any).resolved_aliases;
      if (Array.isArray(resolved) && resolved.length > 0) {
        // [SEQFRAGS-INV-01 2번] 조용한 드롭 금지 — 해석 실패는 건너뛰되 반드시 남긴다.
        const rMissing: string[] = [];
        const out = resolved.flatMap((item: any) => {
          const fid = String(item.fragment_id || item.proposal_fragment_id || item.id || "");
          const hit = allSourceFragments.find((f) => f.fragment_id === fid);
          if (!hit) { rMissing.push(fid); return []; }
          return [hit];
        }) as Fragment[];
        if (rMissing.length) {
          console.warn(`[SEQ_INV][SKIP] ${proposalKey} resolved_aliases 해석 실패 ${rMissing.length}건 — 건너뜀`, rMissing);
        }
        return out;
      }

      const ids: string[] = p.key_fragments ?? p.sequence ?? [];
      const iMissing: string[] = [];
      const byIds = ids.flatMap((id) => {
        const fid = String(typeof id === "string" ? id : ((id as any)?.fragment_id ?? (id as any)?.id ?? ""));
        const hit = allSourceFragments.find((f) => f.fragment_id === fid);
        if (!hit) { iMissing.push(fid); return []; }
        return [hit];
      }) as Fragment[];
      if (iMissing.length) {
        console.warn(`[SEQ_INV][SKIP] ${proposalKey} key_fragments 해석 실패 ${iMissing.length}건 — 건너뜀`, iMissing);
      }
      return byIds;
    },
    [proposals, allSourceFragments, committedProposalId, displayProposalId, fragments, exportClips, programId, isProposalEmpty, expandTileToItems]
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

      // [SELF-CONTAINED-SEQ 2026-07-05] 시퀀스 조각이 동봉한 video_url 우선 → 해석기.
      // 전역 1번영상(videoUrl) 대체 금지 — "다른 영상이 조용히 재생"되던 오염의 직접 원인.
      const fragUrl = (frag as any).video_url ?? getVideoUrlForFrag(frag.fragment_id) ?? undefined;
      if (!fragUrl) {
        console.error(`[PLAYFRAG][BLOCKED] ${frag.fragment_id}: 영상 경로 해석 실패 — 오재생 방지를 위해 재생하지 않음`);
        return;
      }
      const startSec = readFragmentStartSec(frag);
      const endSec = readFragmentEndSec(frag);

      // [R2 가짜 발화 차단] 무장 시점 분리 — 동일 소스 seek(동기)는 즉시,
      // 소스 교체(pending·비동기)는 seek 착지(onLoadedMetadata pending 소비) 때 무장.
      const willSwapSrc = !!fragUrl && !sameVideoSource(ref.current.currentSrc || ref.current.src, fragUrl);
      if (willSwapSrc) {
        endSecRef.current = -1;
        // 새 소스의 duration은 아직 모른다 — pending 소비(onLoadedMetadata)에서 클램프한다.
        (isA ? pendingSeqEndARef : pendingSeqEndBRef).current = endSec;
      } else {
        // [PLAYSTABILITY-FIX-01 3번] 같은 소스: duration을 이미 아니 즉시 클램프.
        endSecRef.current = clampEndToDuration(endSec, ref.current.duration);
      }

      import.meta.env.DEV && console.log("[PLAYFRAG]", {
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

      import.meta.env.DEV && console.log(
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
        playWithAudioRamp(v);
      };

      if (fragUrl && !sameVideoSource(ref.current.currentSrc || ref.current.src, fragUrl)) {
        console.log("[SRC_CHANGE_REQUEST]", {
          player,
          fragment_id: frag?.fragment_id,
          targetTime: startSec + seekOffset,
          fragUrl,
          currentSrc: ref.current?.currentSrc
        });
        // [LAB-37 A] 소스 교체 순간 poster를 들어오는 조각의 썸네일로 바꾼다.
        //   증거 3중(XRAY poster 값·국장 육안·아카이브 대조군 0회): 경계 노출 틈에 보이던 것은
        //   제안 대표 poster(항상 1번 조각 썸네일)였다. 이제 그 틈에는 다음 장면이 미리 보인다.
        //   썸네일 URL은 조각맵 <img>가 이미 로드한 것과 동일 — 캐시 적중이라 프리로드 불필요.
        //   React의 poster 속성(getProposalPoster)은 자기 값이 변할 때만 DOM을 다시 쓰므로
        //   재생 중의 이 명령형 갱신을 덮지 않는다 (제안 교체 렌더 시에만 되돌아가며, 그때
        //   video는 프레임을 쥐고 있어 poster가 보이지 않는다).
        const nextPoster =
          (frag as any).thumbnail?.thumbnail_url ?? (frag as any).thumbnail_url ?? null;
        if (nextPoster) ref.current.poster = nextPoster;
        // [STEP 10-K-C1-R11] Unify src control via state instead of ref.current.src
        if (isA) {
          pendingLocalTimeARef.current = startSec + seekOffset;
          setIsSrcLoadingA(true);
          setPlayerSrcA(fragUrl);
          console.log("[PENDING_SEEK_SET]", {
            player,
            fragment_id: frag?.fragment_id,
            pendingTime: startSec + seekOffset
          });
        } else {
          pendingLocalTimeBRef.current = startSec + seekOffset;
          setIsSrcLoadingB(true);
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

  // [R2 정지 정밀화 — 국장 승인 (가) rAF] span 경계 도달 시 전환/정지의 단일 처리부.
  // 트리거 2원: ① rAF 루프(가시 탭, ≈16ms 주기 — 정밀도 결정) ② timeupdate 백스톱
  // (백그라운드 탭 — 브라우저가 rAF를 정지시키는 환경에서 현행 등가 동작 보존).
  // 중복 발화 봉쇄: 처리 즉시 endRef를 -1로 소거 — 두 트리거 중 먼저 온 쪽만 유효.
  // 착지 = 미달 방향: currentTime >= end - LEAD 에서 끊는다 (지운 말이 들리는 것보다 낫다).
  /** [CLIP_SWITCH_GUARD — #40 A·B 동형] 구간/조각 전환 중 잔상·seek 중간 프레임 숨김.
   *  구판은 B 전용 비대칭(:2083)이었음 — A·B는 같은 동작이어야 한다 (국장 판정).
   *  시퀀스 전환과 단일 재생 구간 전환이 같은 것을 쓴다 (2벌 금지). */
  const hideUntilSeeked = useCallback((gv: HTMLVideoElement) => {
    gv.style.opacity = "0";
    let restored = false;
    const onSeekedOnce = () => {
      if (restored) return;
      restored = true;
      gv.removeEventListener("seeked", onSeekedOnce);
      gv.style.opacity = "1";
    };
    gv.addEventListener("seeked", onSeekedOnce);
    setTimeout(() => {
      if (restored) return;
      restored = true;
      gv.style.opacity = "1";
    }, 400);
  }, []);

  const BOUNDARY_LEAD_SEC = 0.02; // rAF 1주기(≈16.7ms) 예산 — 초과 0 / 미달 ≤20ms
  const handleSpanBoundary = useCallback((player: "A" | "B") => {
    const isA = player === "A";
    const v = (isA ? videoRefA : videoRefB).current;
    if (!v) return;
    const endRef = isA ? seqEndARef : seqEndBRef;
    if (endRef.current <= 0) return; // 이미 처리됨 (중복 발화 금지)
    const isSeqRef = isA ? isSeqARef : isSeqBRef;
    const idxRef = isA ? seqIdxARef : seqIdxBRef;
    const fragsRef = isA ? seqFragsARef : seqFragsBRef;
    const elapsedRef = isA ? seqElapsedSecARef : seqElapsedSecBRef;
    import.meta.env.DEV && console.log(`[BOUNDARY_HIT_${player}]`, {
      currentTime: v.currentTime, seqEnd: endRef.current,
      overshoot_ms: Math.round((v.currentTime - endRef.current) * 1000),
      seqIdx: idxRef.current, isSeq: isSeqRef.current,
    });
    endRef.current = -1;
    if (isSeqRef.current) {
      const nextIdx = idxRef.current + 1;
      const frags = fragsRef.current;
      if (nextIdx < frags.length) {
        elapsedRef.current += readFragmentDurationSec(frags[idxRef.current]);
        idxRef.current = nextIdx;
        (isA ? setProposalTimeA : setProposalTimeB)(elapsedRef.current);
        reportSeqProgress(frags[nextIdx].fragment_id);
        hideUntilSeeked(v);
        playFrag(player, frags[nextIdx], endRef);
      } else {
        isSeqRef.current = false;
        idxRef.current = -1;
        v.pause();
        (isA ? setIsPlayingA : setIsPlayingB)(false);
        reportActiveId(null);
      }
    } else {
      // [SINGLEPLAY-EXPAND-01] 단일 조각도 내부 제외를 건너뛰며 구간을 이어 재생한다.
      //   같은 조각은 어떻게 재생하든 같게 들려야 한다 — 시퀀스와 같은 전개 결과를 소비한다.
      //   ★isSeq는 계속 false, seqIdx는 계속 -1 (단일 재생 계약 불변).
      const segs = isA ? singleSegsARef.current : singleSegsBRef.current;
      const sIdxRef = isA ? singleIdxARef : singleIdxBRef;
      const nextS = sIdxRef.current + 1;
      if (segs.length > 1 && nextS < segs.length) {
        sIdxRef.current = nextS;
        import.meta.env.DEV && console.log(`[SINGLE_SEG_${player}]`, {
          fragment_id: (segs[nextS] as any)?.fragment_id,
          seg: `${nextS + 1}/${segs.length}`,
          startSec: readFragmentStartSec(segs[nextS]), endSec: readFragmentEndSec(segs[nextS]),
        });
        hideUntilSeeked(v);
        playFrag(player, segs[nextS], endRef);
        return;
      }
      sIdxRef.current = -1;
      (isA ? singleSegsARef : singleSegsBRef).current = [];
      v.pause();
      (isA ? setIsPlayingA : setIsPlayingB)(false);
    }
  }, [playFrag, reportActiveId, hideUntilSeeked]);

  const startBoundaryWatch = useCallback((player: "A" | "B") => {
    const isA = player === "A";
    const rafRef = isA ? boundaryRafARef : boundaryRafBRef;
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current); // 단일 루프 보장
    const tick = () => {
      rafRef.current = null;
      const v = (isA ? videoRefA : videoRefB).current;
      const end = (isA ? seqEndARef : seqEndBRef).current;
      // 정지·seek 중·경계 소거 상태면 루프 종료 — play/seeked에서 재무장
      if (!v || end <= 0 || v.paused || v.seeking) return;
      if (v.currentTime >= end - BOUNDARY_LEAD_SEC) {
        handleSpanBoundary(player);
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [handleSpanBoundary]);

  // [R2] 언마운트 시 감시 루프 취소 (누수 금지)
  useEffect(() => () => { stopBoundaryWatch("A"); stopBoundaryWatch("B"); }, [stopBoundaryWatch]);

  const stopSeq = useCallback(
    (player: "A" | "B") => {
      stopBoundaryWatch(player); // [R2] 경계 감시 루프 취소
      (player === "A" ? pendingSeqEndARef : pendingSeqEndBRef).current = null; // [R2] 지연 무장 잔재 소거
      cleanupPendingLoadHandler(player);

      // [SINGLEPLAY-EXPAND-01] 단일 구간 큐도 함께 소거 — 두 재생 방식이 서로 오염되지 않게.
      (player === "A" ? singleSegsARef : singleSegsBRef).current = [];
      (player === "A" ? singleIdxARef : singleIdxBRef).current = -1;

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
    [cleanupPendingLoadHandler, reportActiveId, stopBoundaryWatch]
  );

  const startSeq = useCallback((player: "A" | "B") => {
    const isA = player === "A";
    const ref = isA ? videoRefA : videoRefB;
    const frags = enforceSeqContract(player, buildSeqFrags(player));   // [SEQFRAGS-INV-01 3번]
    if (frags.length === 0) {
      // [건3 빈 조각맵 정직 안내 + F1 하나의 강물] 침묵 무반응·옛 시퀀스 폴백 금지 (헌장 §5).
      // 안내는 지휘부 채팅으로 흐른다 (toast 폐지 — 헌장 §3부칙 F1, SEE FAIL 1 수리).
      if (player === (displayProposalId ?? committedProposalId)) {
        onPlaybackNotice?.("재생할 조각이 없습니다 — 보류맵에서 조각을 되돌리시면 재생됩니다.");
      } else {
        onPlaybackNotice?.(`재생할 조각이 없습니다 — ${player}안에 재생 가능한 조각이 없어요.`);
      }
      return;
    }

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
      totalSec += readFragmentDurationSec(f);
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
      reportSeqProgress(frags[0].fragment_id);
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
      reportSeqProgress(frags[0].fragment_id);
      playFrag("B", frags[0], seqEndBRef);
    }
  }, [buildSeqFrags, enforceSeqContract, playFrag, stopSeq, reportActiveId, setActivePlayerSafe, displayProposalId, committedProposalId, onPlaybackNotice]);
 
  const reSyncSequence = useCallback((player: "A" | "B", time: number) => {
    const frags = player === "A" ? seqFragsARef.current : seqFragsBRef.current;
    const idxRef = player === "A" ? seqIdxARef : seqIdxBRef;
    const endRef = player === "A" ? seqEndARef : seqEndBRef;
    if (!frags.length) return;
    
    const foundIdx = frags.findIndex(f => {
      const s = readFragmentStartSec(f);
      const e = readFragmentEndSec(f);
      return time >= s && time < e;
    });
    
    if (foundIdx !== -1) {
      idxRef.current = foundIdx;
      const f = frags[foundIdx];
      endRef.current = readFragmentEndSec(f);
      reportActiveId(f.fragment_id);
      
      let newElapsed = 0;
      for(let i=0; i < foundIdx; i++) {
        const pf = frags[i];
        newElapsed += readFragmentDurationSec(pf);
      }
      if (player === "A") seqElapsedSecARef.current = newElapsed;
      else seqElapsedSecBRef.current = newElapsed;
    }
  }, [reportActiveId]);

  const resolveProposalTime = useCallback((frags: Fragment[], targetGlobalTime: number) => {
    let acc = 0;
    for (let i = 0; i < frags.length; i++) {
      const f = frags[i];
      const dur = readFragmentDurationSec(f);
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
      const ldur = readFragmentDurationSec(lf);
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

    reportSeqProgress(frags[resolved.index].fragment_id);

    // Fragment change might require src change
    const targetFrag = frags[resolved.index];
    // [SELF-CONTAINED-SEQ 2026-07-05] 동봉 video_url 우선, 전역 1번영상 대체 금지
    const targetUrl = (targetFrag as any).video_url ?? getVideoUrlForFrag(targetFrag.fragment_id) ?? undefined;

    if (targetUrl && !sameVideoSource(video.current.currentSrc || video.current.src, targetUrl)) {
      playFrag(player, targetFrag, isA ? seqEndARef : seqEndBRef, resolved.offset);
    } else {
      const startSec = readFragmentStartSec(targetFrag);
      if (isA) isSeekingRefA.current = true;
      else isSeekingRefB.current = true;
      video.current.currentTime = startSec + resolved.offset;
      if (isPlaying) video.current.play().catch(() => {});
    }
  }, [resolveProposalTime, isPlayingA, isPlayingB, getVideoUrlForFrag, videoUrl, sameVideoSource, playFrag, reportActiveId]);



  useEffect(() => {
    if (!selectedFragment) return;

    // [PLAYSTABILITY-FIX-01 1-2] (a)와 (b)를 여기서 가른다.
    //   이 조각 변경이 **시퀀스가 스스로 알린 진행**(reportSeqProgress)에서 온 것이면
    //   재생 제어를 하지 않는다 — 시퀀스는 이미 이 조각을 틀고 있고, 여기서 stopSeq를
    //   부르면 시퀀스가 자기를 죽인다(실측: 2번째 조각에서 정지).
    //   표시(강조·스크롤)는 이미 onActiveFragmentChange로 전달됐으므로 할 일이 없다.
    //   반대로 사용자 클릭은 표식이 없으므로 아래 기존 동작(시퀀스 중단 + 단일 재생)을 탄다 —
    //   재생 중 클릭도 정상 작동한다(상태가 아니라 출처로 갈랐기 때문).
    if (seqAutoReportedFidRef.current === selectedFragment.fragment_id) {
      return;
    }

    if (isSeqARef.current) stopSeq("A");
    if (isSeqBRef.current) stopSeq("B");

    const player = activePlayerRef.current === "B" ? "B" : "A";
    const endRef = player === "B" ? seqEndBRef : seqEndARef;

    setActivePlayerSafe(player);
    reportActiveId(selectedFragment.fragment_id);

    // [SINGLEPLAY-EXPAND-01] 조각의 편집 상태(트림·내부제외)는 재생 방식과 무관하게 적용된다.
    //   구판은 타일을 통째로 playFrag에 넘겨 외피 1구간(예: 15.35~29.31)으로 재생했다 —
    //   시퀀스는 3구간인데 클릭 재생만 지운 구간이 들렸다. 같은 전개 함수를 쓴다.
    const segs = expandTileToItems(selectedFragment as any);
    (player === "A" ? singleSegsARef : singleSegsBRef).current = segs;
    (player === "A" ? singleIdxARef : singleIdxBRef).current = 0;
    if (segs.length > 1) {
      import.meta.env.DEV && console.log(`[SINGLE_SEG_${player}]`, {
        fragment_id: (selectedFragment as any)?.fragment_id, seg: `1/${segs.length}`,
        startSec: readFragmentStartSec(segs[0]), endSec: readFragmentEndSec(segs[0]),
      });
    }
    playFrag(player, segs[0], endRef);

    if (player === "B") {
      setIsPlayingB(true);
    } else {
      setIsPlayingA(true);
    }
  }, [selectedFragment, playFrag, setActivePlayerSafe, stopSeq, reportActiveId, expandTileToItems]);

  const handleUpload = () => {
    fileInputRef.current?.click();
  };

  // [UI-①] 파일 선택 → 즉시 분석하지 않고 스테이징에 쌓는다 (넣고/빼고/더 넣기 자유)
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files);
      e.target.value = ""; // 같은 파일 재선택 허용
      console.log(`[CenterPanel] Files staged:`, files.map(f => f.name));

      setExportUrl(null);
      setExportError(null);

      setStagedFiles((prev) => {
        const cur = prev ?? [];
        const fresh = files
          .filter((f) => !cur.some((s) => s.file.name === f.name && s.file.size === f.size))
          .map((f) => ({ file: f, note: "" } as StagedMeta));
        return [...cur, ...fresh];
      });
      // 개략 훑기(브라우저 메타데이터) — 비동기로 채움
      for (const f of files) {
        probeFileMeta(f).then((meta) => {
          setStagedFiles((prev) => prev
            ? prev.map((s) => (s.file.name === f.name && s.file.size === f.size ? { ...s, ...meta } : s))
            : prev);
        });
      }
    }
  };

  // [UI-①③④] 문진 완료 → 분석 시작
  const handleStagingStart = async (answers: IntakeAnswers) => {
    const staged = stagedFiles ?? [];
    if (staged.length === 0) return;
    onIntake?.(answers);
    const files = staged.map((s) => s.file);
    setStagedFiles(null);
    if (onFileSelect) onFileSelect(files[0]);
    if (onAnalyze) {
      const success = await onAnalyze(files[0], files.slice(1));
      if (!success) console.warn("[CenterPanel] Analysis failed or was cancelled.");
    }
  };

  const handleSendFull = useCallback(async () => {
    if (!chatValue.trim()) return;
    const raw = chatValue.trim();
    setChatValue("");
    // [CHAT-FLOW-2 2026-08-02] 내가 보냈으면 내려간다 — 위 handleSubmitConsultation 과 같은 이유.
    scrollChatToBottom();
    await dispatchCommand(raw);
  }, [chatValue, dispatchCommand, scrollChatToBottom]);

  const getProposalPoster = useCallback(
    (key: "A" | "B") => {
      const p = proposals?.[key];
      if (isProposalEmpty(p)) return undefined;
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
    [proposals, allSourceFragments, isProposalEmpty]
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

  // [A/B 제안] 펼친 제안을 항상 '재생'(토글 아님). preview mp4 또는 fragment seq.
  const playProposal = useCallback((key: "A" | "B") => {
    const isA = key === "A";
    const v = (isA ? videoRefA : videoRefB).current;
    if (!v) return;
    const previewUrl = isA ? previewUrlA : previewUrlB;
    stopOtherPlayer(key);
    setActivePlayerSafe(key);
    if (previewUrl) {
      (isA ? seqEndARef : seqEndBRef).current = -1;
      (isA ? isSeqARef : isSeqBRef).current = false;
      (isA ? seqIdxARef : seqIdxBRef).current = 0;
      if (!sameVideoSource(v.currentSrc || v.src, previewUrl)) { v.src = previewUrl; v.load(); }
      v.currentTime = 0;
      v.play().catch(() => {});
    } else {
      startSeq(key);
    }
    handleProposalPreview(key);
  }, [previewUrlA, previewUrlB, startSeq, stopOtherPlayer, setActivePlayerSafe, handleProposalPreview]);

  // [A/B 제안] 헤더 클릭 → 그 제안을 크게 펼치고 재생, 다른 하나는 접고 정지. (항상 하나 열림)
  // [CHATLOG-STACK-01 1번] 접기/펴기가 아니라 '재생을 이 자리로 옮긴다'.
  // 다른 안은 정지시키되(재생은 한 자리에서만) 접지 않는다.
  const toggleProposal = useCallback((key: "A" | "B") => {
    if (key !== "A") videoRefA.current?.pause();
    if (key !== "B") videoRefB.current?.pause();
    playProposal(key); // 직접 클릭(제스처)이라 브라우저가 재생 허용
  }, [playProposal]);


  // [CHATLOG-STACK-01 1번] '기본 B 펼침' effect 폐지 — 접힘이 없으니 펼칠 것도 없다.

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
        body: JSON.stringify({ clips: exportClips, program_id: programId, program_title: programTitle })
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
        onExportDone?.();
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
    // [UI-①③④] 스테이징 활성 시 — 문진 화면이 최우선
    if (stagedFiles !== null && appState !== "analyzing") {
      return (
        <>
          <UploadStagingView
            staged={stagedFiles}
            onAddFiles={handleUpload}
            onRemove={(i) => setStagedFiles((prev) => prev ? prev.filter((_, k) => k !== i) : prev)}
            onNoteChange={(i, note) => setStagedFiles((prev) => prev ? prev.map((s, k) => (k === i ? { ...s, note } : s)) : prev)}
            onStart={handleStagingStart}
            onCancel={() => setStagedFiles(null)}
          />
          <input ref={fileInputRef} type="file" accept="video/*" multiple className="hidden" onChange={handleFileChange} />
        </>
      );
    }

    if (appState === "empty" && (!sourceEntries || sourceEntries.length === 0)) {
      return <EmptyProjectView handleUpload={handleUpload} fileInputRef={fileInputRef} handleFileChange={handleFileChange} />;
    }

    // [LOADING · GATE-LOOP-01 2-2] 로딩은 '분석 중'일 때만이다.
    //   구판은 `complete && proposals && !storyPlan`으로도 로더를 띄웠다 — 제안·대화문이
    //   준비되기를 기다리는 조건이라, 제안을 만들지 않는 승인 전 단계나 대화 기록이 없는
    //   프로젝트(실측: 깨끗한 프로젝트 proj_3e04c17b1669)가 영구 로딩에 갇혔다.
    //   목적지는 원고(스토리)이므로 기다릴 이유가 없다.
    const showAnalyzingLoader = appState === "analyzing";

    if (showAnalyzingLoader) {
      return <AnalysisLoadingView analyzeMessage={analyzeMessage} analysisLogs={analysisLogs} analyzeProgress={analyzeProgress} />;
    }

    // [CHAT-FLOW 2026-08-02] Stage is no longer a fixed wrapper above the stream.
    //   Director's rule: everything flows. Nothing stays pinned.
    //   The stage body is unchanged; only its home moved - it is now a stream item
    //   carrying a ts, so new messages push it upward like any other event.
        const stageBlock = (() => { const stageContent = (
          <>
        {/* [STEP 10-I.5.28-E9-R1-R1] Story Direction Adjustment Bar (Only after confirmed) */}
        {storyPlan && storyPlan.consultation_status === "confirmed" && (
          <div className="w-full max-w-[800px] bg-secondary/10 border border-border/10 rounded-xl px-4 py-2.5 shadow-sm">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 overflow-hidden">
                {/* [CHAT-SKIN] 파란 책 아이콘 제거 (국장 지시) */}
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
          {renderSelfCheckNotice(proposals)}
          <div className="flex flex-col gap-3 w-full">
          {/* [LAYOUT] A안 아코디언 */}
          <div className="w-full rounded-2xl border border-white/8 bg-white/[0.02] overflow-hidden">
          <button type="button" onClick={() => toggleProposal("A")} className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-white/[0.04] transition-colors">
            <span className="relative w-12 h-8 flex-shrink-0 rounded overflow-hidden bg-black/30 flex items-center justify-center">
              {getProposalPoster("A") ? <img src={getProposalPoster("A")} className="w-full h-full object-cover" draggable={false} /> : <Play size={12} className="text-white/40" />}
              <span className="absolute top-0 left-0 px-1 rounded-br text-[9px] font-black leading-tight bg-primary/70 text-primary-foreground">A</span>
            </span>
            <span className="min-w-0 flex-1 text-left text-[13px] font-bold text-foreground/85">시장형 편집 <span className="text-primary">(A)</span></span>
          </button>
          <div className="px-3 pb-3">
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
                // [B4] 사전 렌더 없음 → 라이브 시퀀스 재생은 정상 동작 — 경고 아님, 정보 등급
                console.info("[PROPOSAL_PREVIEW_MISSING]", { variant: "A", proposal_id: (proposals?.A as any)?.proposal_id });
                if (!isSeqARef.current || videoRefA.current.paused) {
                  startSeq("A");
                  handleProposalPreview("A");
                } else {
                  stopSeq("A");
                }
              }}
            >
              {playerVideoUrlA ? (
                <>
                  <video
                    ref={videoRefA}
                    style={{
                      opacity: isSrcLoadingA ? 0 : 1,
                      // [PUNCH-1 R1] A = punch_in. 배율·시각은 백엔드 punch_spec 그대로.
                      transform: `scale(${punchScaleA})`,
                      transformOrigin: 'center center',
                      transition: `opacity 0.05s, transform ${punchRampSec}s linear`,
                    }}
                    src={playerSrcA ?? playerVideoUrlA ?? undefined}
                    poster={getProposalPoster("A")}
                    className="w-full h-full object-contain bg-black"
                    onPlay={(e) => {
                      if (!previewUrlA && seqEndARef.current <= 0) {
                        e.currentTarget.pause();
                        setIsPlayingA(false);
                        return;
                      }
                      // [DUAL_PLAY_GUARD] A가 play되면 B 즉시 정지
                      stopOtherPlayer("A");
                      setActivePlayerSafe("A");
                      setIsPlayingA(true);
                      startBoundaryWatch("A"); // [R2] 경계 감시 무장
                    }}
                    onPause={() => setIsPlayingA(false)}
                    onEnded={() => {
                      // [SEQ-ONENDED] 짧은 영상(≤10s)이 자연 종료되면 onTimeUpdate가 near 감지 전 끝날 수 있음
                      // → sequence advance를 직접 트리거
                      if (activePlayerRef.current !== "A") return;
                      if (!isSeqARef.current) return;
                      if (!endedShouldAdvance(videoRefA.current, seqEndARef, "A")) return;
                      const nextIdx = seqIdxARef.current + 1;
                      const frags = seqFragsARef.current;
                      if (nextIdx < frags.length) {
                        const curFrag = frags[seqIdxARef.current];
                        seqElapsedSecARef.current += readFragmentDurationSec(curFrag);
                        seqIdxARef.current = nextIdx;
                        setProposalTimeA(seqElapsedSecARef.current);
                        reportSeqProgress(frags[nextIdx].fragment_id);
                        playFrag("A", frags[nextIdx], seqEndARef);
                      } else {
                        isSeqARef.current = false;
                        seqIdxARef.current = -1;
                        seqEndARef.current = -1;
                        setIsPlayingA(false);
                        reportActiveId(null);
                      }
                    }}
                    onSeeking={() => {
                      isSeekingRefA.current = true;
                    }}
                    onSeeked={() => {
                      isSeekingRefA.current = false;
                      startBoundaryWatch("A"); // [R2] span 전환 seek 후 재무장 (play 이벤트 없는 동일-src seek 대비)
                    }}
                    onTimeUpdate={(e) => {
                      // [DUAL_PLAY_GUARD] inactive player는 advance 차단
                      if (activePlayerRef.current !== "A") return;
                      if (isDraggingProposalSeekARef.current) return;
                      if (isSeekingRefA.current || e.currentTarget.seeking) return;
                      const v = e.currentTarget;
                      if (!previewUrlA && seqEndARef.current <= 0) {
                        v.pause();
                        setIsPlayingA(false);
                        return;
                      }
                      // [PREVIEW_MODE_GUARD] preview_url 재생 중 fragment seq 개입 차단
                      if (previewUrlA) {
                        setProposalTimeA(v.currentTime);
                        return;
                      }
                      if (isSeqARef.current && seqTotalSecARef.current > 0) {
                        const fragStart = readFragmentStartSec(seqFragsARef.current[seqIdxARef.current]);
                        const global = seqElapsedSecARef.current + Math.max(0, v.currentTime - fragStart);
                        setProposalTimeA(global);
                      }
                      // [PUNCH-1 R1] v.currentTime은 소스 절대초 — punch_spec.at과 같은 좌표계다.
                      applyPunchA(v.currentTime);

                      // [R2] 경계 판정 본체는 rAF 루프(startBoundaryWatch)가 담당 (≈16ms 정밀).
                      // 여기는 백그라운드 탭(브라우저가 rAF 정지) 전용 백스톱 — 동일 처리부 공유,
                      // endRef 소거로 중복 발화 봉쇄.
                      if (seqEndARef.current > 0 && v.currentTime >= seqEndARef.current - BOUNDARY_LEAD_SEC) {
                        handleSpanBoundary("A");
                      }
                    }}
                    onLoadedMetadata={(e) => {
                      setIsSrcLoadingA(false);
                      setDurationA(e.currentTarget.duration);
                      // [DUAL_PLAY_GUARD] inactive player는 seek+play 차단
                      if (activePlayerRef.current !== "A") {
                        DEBUG_LOG && console.log("[DUAL_PLAY_GUARD] onLoadedMetadata A skipped (inactive)");
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
                        // [R2 가짜 발화 차단] 소스 교체 완료 — 이제 span end 무장 (구 소스 시간과의 비교 불가 시점)
                        if (pendingSeqEndARef.current !== null) {
                          // [PLAYSTABILITY-FIX-01 3번] duration을 이제 아니 여기서 클램프.
                          seqEndARef.current = clampEndToDuration(
                            pendingSeqEndARef.current, e.currentTarget.duration);
                          pendingSeqEndARef.current = null;
                        }
                        const tgt = e.currentTarget;
                        const target = pending;
                        let seekDone = false;

                        const onPendingSeeked = () => {
                          if (seekDone) return;
                          seekDone = true;
                          tgt.removeEventListener("seeked", onPendingSeeked);
                          if (Math.abs(tgt.currentTime - target) <= 0.5) {
                            console.log("[PENDING_SEEKED_PLAY]", { player: "A", currentTime: tgt.currentTime, target });
                            playWithAudioRamp(tgt);
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
                            playWithAudioRamp(tgt);
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


              <div 
                className="absolute bottom-0 left-0 right-0 h-6 z-40 flex items-end px-2 pb-1 opacity-0 group-hover/player:opacity-100 transition-opacity duration-200"
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
                  ? "text-muted-foreground/60 cursor-not-allowed"
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
          </div>
          </div>

          {/* [LAYOUT] B안 아코디언 */}
          <div className="w-full rounded-2xl border border-white/8 bg-white/[0.02] overflow-hidden">
          <button type="button" onClick={() => toggleProposal("B")} className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-white/[0.04] transition-colors">
            <span className="relative w-12 h-8 flex-shrink-0 rounded overflow-hidden bg-black/30 flex items-center justify-center">
              {getProposalPoster("B") ? <img src={getProposalPoster("B")} className="w-full h-full object-cover" draggable={false} /> : <Play size={12} className="text-white/40" />}
              <span className="absolute top-0 left-0 px-1 rounded-br text-[9px] font-black leading-tight bg-ccut-indigo/80 text-white">B</span>
            </span>
            <span className="min-w-0 flex-1 text-left text-[13px] font-bold text-foreground/85">사용자친화형 편집 <span className="text-ccut-indigo">(B)</span></span>
          </button>
          <div className="px-3 pb-3">
          <div className="flex flex-col items-center space-y-4">
            <div
              className="relative w-full aspect-[16/8] rounded-2xl bg-black overflow-hidden border border-white/8 cursor-pointer group/player"
              onClick={() => {
                if (!videoRefB.current) return;

                // [CLIP_SEQ_FIRST_B] sequence 조각이 있으면 fragment 재생 우선
                const bSeqFrags = buildSeqFrags("B");
                if (bSeqFrags.length > 0) {
                  if (!isSeqBRef.current || videoRefB.current.paused) {
                    startSeq("B");
                    handleProposalPreview("B");
                  } else {
                    stopSeq("B");
                  }
                  return;
                }

                if (previewUrlB) {
                  // [PROPOSAL_PREVIEW_PLAY] preview mp4 직접 재생 — seek 없음 (fragment 없을 때 fallback)
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
                // [B4] 정보 등급 — 정상 동작을 경고로 표시하지 않는다
                console.info("[PROPOSAL_PREVIEW_MISSING]", { variant: "B", proposal_id: (proposals?.B as any)?.proposal_id });
                if (!isSeqBRef.current || videoRefB.current.paused) {
                  startSeq("B");
                  handleProposalPreview("B");
                } else {
                  stopSeq("B");
                }
              }}
            >
              {playerVideoUrlB ? (
                <>
                  <video
                    ref={videoRefB}
                    style={{ opacity: isSrcLoadingB ? 0 : 1, transition: 'opacity 0.05s' }}
                    src={playerSrcB ?? playerVideoUrlB ?? undefined}
                    poster={getProposalPoster("B")}
                    className="w-full h-full object-contain bg-black"
                    onPlay={(e) => {
                      if (!previewUrlB && seqEndBRef.current <= 0) {
                        e.currentTarget.pause();
                        setIsPlayingB(false);
                        return;
                      }
                      // [DUAL_PLAY_GUARD] B가 play되면 A 즉시 정지
                      stopOtherPlayer("B");
                      setActivePlayerSafe("B");
                      setIsPlayingB(true);
                      startBoundaryWatch("B"); // [R2] 경계 감시 무장
                    }}
                    onPause={() => setIsPlayingB(false)}
                    onEnded={() => {
                      // [SEQ-ONENDED] 짧은 영상이 자연 종료되면 sequence advance 직접 트리거
                      if (activePlayerRef.current !== "B") return;
                      if (!isSeqBRef.current) return;
                      if (!endedShouldAdvance(videoRefB.current, seqEndBRef, "B")) return;
                      const nextIdx = seqIdxBRef.current + 1;
                      const frags = seqFragsBRef.current;
                      if (nextIdx < frags.length) {
                        const curFrag = frags[seqIdxBRef.current];
                        seqElapsedSecBRef.current += readFragmentDurationSec(curFrag);
                        seqIdxBRef.current = nextIdx;
                        setProposalTimeB(seqElapsedSecBRef.current);
                        reportSeqProgress(frags[nextIdx].fragment_id);
                        playFrag("B", frags[nextIdx], seqEndBRef);
                      } else {
                        isSeqBRef.current = false;
                        seqIdxBRef.current = -1;
                        seqEndBRef.current = -1;
                        setIsPlayingB(false);
                        reportActiveId(null);
                      }
                    }}
                    onSeeking={() => {
                      isSeekingRefB.current = true;
                    }}
                    onSeeked={() => {
                      isSeekingRefB.current = false;
                      startBoundaryWatch("B"); // [R2] span 전환 seek 후 재무장
                    }}
                    onTimeUpdate={(e) => {
                      // [DUAL_PLAY_GUARD] inactive player는 advance 차단
                      if (activePlayerRef.current !== "B") return;
                      if (isDraggingProposalSeekBRef.current) return;
                      if (isSeekingRefB.current || e.currentTarget.seeking) return;
                      const v = e.currentTarget;
                      if (!previewUrlB && seqEndBRef.current <= 0) {
                        v.pause();
                        setIsPlayingB(false);
                        return;
                      }
                      // [PREVIEW_MODE_GUARD] preview_url 재생 중 fragment seq 개입 차단
                      if (previewUrlB) {
                        setProposalTimeB(v.currentTime);
                        return;
                      }
                      if (isSeqBRef.current && seqTotalSecBRef.current > 0) {
                        const fragStart = readFragmentStartSec(seqFragsBRef.current[seqIdxBRef.current]);
                        const global = seqElapsedSecBRef.current + Math.max(0, v.currentTime - fragStart);
                        setProposalTimeB(global);
                      }

                      // [R2] 경계 판정 본체는 rAF 루프가 담당 — 여기는 백그라운드 탭 백스톱.
                      // (CLIP_SWITCH_GUARD_B 잔상 숨김은 공유 처리부 handleSpanBoundary로 이관)
                      if (seqEndBRef.current > 0 && v.currentTime >= seqEndBRef.current - BOUNDARY_LEAD_SEC) {
                        handleSpanBoundary("B");
                      }
                    }}
                    onLoadedMetadata={(e) => {
                      setIsSrcLoadingB(false);
                      setDurationB(e.currentTarget.duration);
                      // [DUAL_PLAY_GUARD] inactive player는 seek+play 차단
                      if (activePlayerRef.current !== "B") {
                        DEBUG_LOG && console.log("[DUAL_PLAY_GUARD] onLoadedMetadata B skipped (inactive)");
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
                        // [R2 가짜 발화 차단] 소스 교체 완료 — 이제 span end 무장
                        if (pendingSeqEndBRef.current !== null) {
                          // [PLAYSTABILITY-FIX-01 3번] duration을 이제 아니 여기서 클램프.
                          seqEndBRef.current = clampEndToDuration(
                            pendingSeqEndBRef.current, e.currentTarget.duration);
                          pendingSeqEndBRef.current = null;
                        }
                        const tgt = e.currentTarget;
                        const target = pending;
                        let seekDone = false;

                        const onPendingSeeked = () => {
                          if (seekDone) return;
                          seekDone = true;
                          tgt.removeEventListener("seeked", onPendingSeeked);
                          if (Math.abs(tgt.currentTime - target) <= 0.5) {
                            console.log("[PENDING_SEEKED_PLAY]", { player: "B", currentTime: tgt.currentTime, target });
                            playWithAudioRamp(tgt);
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
                            playWithAudioRamp(tgt);
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


              <div 
                className="absolute bottom-0 left-0 right-0 h-6 z-40 flex items-end px-2 pb-1 opacity-0 group-hover/player:opacity-100 transition-opacity duration-200"
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
                  ? "text-muted-foreground/60 cursor-not-allowed"
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
          </div>
        </div>
      </>
    )}

      <div className="w-full grid grid-cols-2 gap-4 hidden">
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
                  <span className="text-[10px] font-bold text-muted-foreground/70">
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

                </div>
              </div>
            ))
          ) : null}
        </div>

        <ExportPanelSection
          committedProposalId={committedProposalId}
          isExporting={isExporting}
          renderStatus={renderStatus}
          exportError={exportError}
          onExport={handleExportClick}
        />
          </>
        );

        // [#19-b 심판 · GATE-LOOP-01 2-1 · CHATLOG-STACK-01] 무대(A/B)는 '승인됨'일 때만
        // 붙는다(editStageAllowed). 원고(전사)는 단계와 무관하게 늘 위에 남는다.
        const storyContent = (
          <div className="w-full max-w-[800px] rounded-2xl border border-white/8 bg-white/[0.02] overflow-hidden">
            {/* [TRANSCRIPT-POLISH-01] New-story banner is hidden in mode gate view. */}
            {/* [STORY-TRACK-A A-5] 편집기는 우측 조각맵으로 이전. 중앙은 활성 텍스트조각만
                읽기전용으로 표현한다(스토리 카드). 편집은 여기서 못 한다 — 우측에서. */}
            {(storyGate.story?.item_count ?? 0) > 0 ? (
              <div className="px-5 py-4 flex flex-col gap-2 max-h-[70vh] overflow-y-auto">
                <div className="flex items-center gap-2 mb-1">
                  {/* [CHAT-SKIN] 파란 책 아이콘 제거 (국장 지시) */}
                  <span className="text-[12px] font-bold tracking-wider uppercase text-muted-foreground/60">{storyReplacement ? "전사" : "이야기 (고른 장면)"}</span>
                  <span className="ml-auto text-[12px] text-muted-foreground/70">우측 조각맵에서 고르고 빼세요</span>
                </div>
                {storyReplacement ? (
                  storyReplacement
                ) : activeStoryItems.length > 0 ? (
                  activeStoryItems.map((it, i) => {
                    const storyRowActive =
                      activeStoryFragmentId === it.fragmentId ||
                      activeFragmentId === it.fragmentId ||
                      activeStoryFragmentIdProp === it.fragmentId;
                    return (
                    // [#21 잔여] 조각 텍스트 폰트·사이즈를 우측 전사와 완전 동일하게
                    // (FRAGMENT_TEXT_FONT · 15px · leading 1.7). 화면 내 모든 조각 텍스트 동일 폰트.
                    <button
                      key={it.id}
                      type="button"
                      data-story-fragment-row="true"
                      data-story-fragment-active={storyRowActive ? "true" : "false"}
                      data-story-fid={it.fragmentId}
                      onClick={() => {
                        setActiveStoryFragmentId(it.fragmentId);
                        onActiveFragmentChange?.(it.fragmentId, "user");
                      }}
                      className={`w-full text-left text-[12px] leading-snug rounded px-1.5 py-0.5 transition-colors ${storyRowActive ? "text-white" : "text-muted-foreground/65 hover:text-foreground"}`}
                      style={{ fontFamily: FRAGMENT_TEXT_FONT }}
                    >
                      <span className="inline-flex items-baseline gap-1.5 whitespace-normal break-words">
                        <span className="text-[12px] font-mono text-primary/50">{i + 1}.</span>
                        {it.label && <span className="font-black text-primary/80">{it.label}</span>}
                        {it.stageDirection && (
                          <span className="italic">{it.stageDirection}</span>
                        )}
                        {it.dialogue ? (
                          <span style={FRAGMENT_TEXT_STYLE}>{it.dialogue}</span>
                        ) : !it.stageDirection ? (
                          <span style={FRAGMENT_SILENT_STYLE}>(무음)</span>
                        ) : null}
                      </span>
                    </button>
                  );
                  })
                ) : (
                  <p className="py-6 text-center text-[13px] text-foreground/62">
                    아직 고른 장면이 없어요. 우측 조각맵에서 원하는 전사를 눌러 담아주세요.
                  </p>
                )}
              </div>
            ) : (
              <p className="px-6 py-10 text-center text-[13px] text-foreground/64">
                이야기를 엮고 있습니다…
              </p>
            )}
          </div>
        );

        // [CHATLOG-STACK-01 1번] swap → stack. 한 자리에서 갈아끼우지 않고 세로로 누적한다.
        //   구판: `showStory ? storyContent : stageContent` — 편집 단계로 가면 채팅창의
        //   전사가 통째로 사라졌다. 채팅은 기록이므로 사라지지 않고 위로 올라가야 한다.
        //   신판: 확정된 스토리(전사)가 위에 남고, 승인되면 그 아래로 제안 A·B가 붙는다.
        //   탭·아코디언 없음 — 세 블록이 동시에 존재한다.
        // [CHAT-FLOW-3 2026-08-02] 전사와 편집안을 끊는다 (국장 지시:
        //   "편집을 지시하니 전사와 편집본을 통으로 가져온다. 끊어라").
        //   붙어다녀야 할 이유가 있어서가 아니라, 무대가 한 덩이였던 시절의 조립이
        //   가①에서 그대로 흘러온 것이다. 이음새는 이 한 줄뿐이었다.
        //   실측(STEP 1-3): 두 덩이는 서로의 변수를 하나도 공유하지 않는다 —
        //     전사 쪽은 proposals·activeProposalEntryId 참조 0건,
        //     A/B 쪽은 storyGate·activeStoryItems·storyReplacement 참조 0건.
        //   그래서 부품 내부를 한 글자도 건드리지 않고 여기서만 가른다.
        //   ★ 빈 아이템을 만들지 않는다 — 없는 쪽은 null 이고 스트림에 안 들어간다.
        const finalContent = {
          transcript: roughCutStage ?? storyContent,
          proposal: editStageAllowed ? stageContent : null,
        };
        // [CHAT-ROOT 3-2 2026-08-02] 포털 분기 제거 — 주석이 지목한 그 한 줄이다.
        //   구판: `stageSlot ? createPortal(finalContent, stageSlot) : finalContent`
        //   stageSlot 은 처음 null 이라 인라인으로 그렸다가, 슬롯 ref 콜백이 값을 채우면
        //   같은 내용이 포털로 옮겨갔다. React 에게는 부모가 바뀐 것이므로 언마운트 -> 재마운트다.
        //   실측(프로젝트 전환 Freesia -> Adhara):
        //     mount(t=70397) -> unmount(t=70425) -> mount(t=70425) = 28ms 한 틱,
        //     그 결과 /rough-cut/project 가 2회 호출됐다(27ms 간격).
        //   [C1-DIAGNOSED 2026-08-01] 이 재마운트를 기록하며 "다음에 이 포털/인라인 구조를
        //   손대는 사람이 함께 없앨 것"이라 남겼다. 지금이 그때다 — 무대가 스트림 밖 한 자리에
        //   고정되므로 슬롯도 포털도 필요 없다.
        return finalContent; })();

    return (
      <>
        {/* [FRAGMENT-SEARCH] 채팅 자연어 조각 검색 결과 */}
        <FragSearchPanel fragSearch={fragSearch} onClose={() => setFragSearch(null)} />

        {/* [LAYER-SPLIT 2026-08-04 국장 확정 ①] 전사층 — 채팅창 최상단 한 줄.
            ★chatScrollRef 바깥이다. 채팅이 아무리 흘러도 이 층은 닿지 않는다.
              8/3 사고(접힘 한 줄이 조각맵·플레이어·내보내기를 전부 죽임)가
              구조적으로 재발할 수 없는 이유가 이 위치다 — 매달릴 스트림이 없다.
            ★몸통은 항상 마운트하고 display 로만 감춘다. 안 보이는 것과 없는 것을 섞지 않는다. */}
        {roughCutStage ? (
          <div className="w-full flex flex-col items-center px-4 pt-2" data-layer="transcript">
            {/* [LAYER-FIX 2026-08-04 국장 확정 ①] 펼친 전사는 ★겹쳐 뜬다 — 아래를 밀지 않는다.
                구판은 문서 흐름 안에서 자라서 버전 줄을 331px 아래로 밀어냈다(실측 36 -> 367).
                버전 줄은 채팅 바로 위에 고정이어야 하므로, 전사 몸통을 absolute 로 띄운다.
                ★몸통은 접혀도 마운트를 유지한다 — 감추는 것은 display 뿐이다(8/3 교훈 그대로). */}
            <div className="w-full max-w-[800px] relative">
              <button
                type="button"
                onClick={() => setTranscriptOpen((v) => !v)}
                data-transcript-toggle
                aria-expanded={transcriptOpen}
                className="w-full flex items-center gap-2 py-1 text-left text-meta text-muted-foreground hover:text-foreground transition-colors"
              >
                <span className="font-bold">전사</span>
                <ChevronDown
                  size={14}
                  className={`transition-transform ${transcriptOpen ? "" : "-rotate-90"}`}
                />
              </button>
              <div
                data-transcript-body
                className="absolute left-0 right-0 top-full z-30 max-h-[60vh] overflow-y-auto no-scrollbar rounded-xl border border-border/15 bg-background shadow-xl"
                style={transcriptOpen ? undefined : { display: "none" }}
                aria-hidden={transcriptOpen ? undefined : true}
              >
                {roughCutStage}
              </div>
            </div>
          </div>
        ) : null}

        {/* [LAYER-SPLIT 2026-08-04 국장 확정 ②] 버전층 — 채팅창 바로 위 한 줄, 가로 스크롤.
            내용은 Index 가 만들어 넘긴다(데이터가 그쪽에 있다). 여기는 자리만 준다. */}
        {versionBar ? (
          <div className="w-full flex justify-center px-4" data-layer="versionbar">
            <div className="w-full max-w-[800px]">{versionBar}</div>
          </div>
        ) : null}

      <div
        ref={chatScrollRef}
        onScroll={handleChatScroll}
        className="flex-1 w-full px-4 pt-4 flex flex-col items-center space-y-4 overflow-y-auto no-scrollbar pb-20"
      >
        {/* [FLOW] 중앙 타임라인 — 개략·채팅·지난 제안이 하나의 흐름으로 위로 흘러간다.
            현재(활성) 제안 pair만 아래 '무대'(플레이어 그리드)에 서고,
            지난 제안은 고스트 카드로 흐름 속에 남아 '다시 열기'로 무대 복원. */}
        {((storyPlan?.messages || []).length > 0 || proposalHistory.length > 0) && (
          <div className="w-full max-w-[800px] flex flex-col gap-6 py-8 animate-in fade-in duration-700">

            {/* [R8 유령 5호 2026-07-20] 스토리박스 독립 — 렌더 조건에서 `storyPlan &&` 제거.
                storyPlan(대화 원고)이 죽어도 proposalHistory>0이면 지난 원고 세대는 상주한다
                (프로젝트 전환·확정 왕복 중 소실 0). '지난 원고 0개'(이 블록 미출현)와 '복원 실패'
                (세대는 있는데 대화 기록만 못 불러옴)를 아래 안내로 구분한다. */}
            {!storyPlan && proposalHistory.length > 0 && (
              <div className="text-[11px] text-muted-foreground/76 px-1">
                이전 대화 기록은 불러오지 못했어요. 지난 원고 세대는 아래에 그대로 남아 있습니다.
              </div>
            )}

            {/* [TIMELINE-PAGE 2026-08-02] 잘린 옛 기록으로 가는 유일한 문.
                서버는 limit=300 을 넘으면 has_more=true 를 주는데(실측: Merope 614행 중
                314행 도달 불가) 그것을 듣는 코드가 0이었다 — 방어는 있고 호출처가 없었다.
                ★버튼으로 둔 이유: 이 환경에서 IntersectionObserver 가 0회 발화한다(§4-2).
                  스크롤 자동 로드는 만들어도 발동을 증명할 수 없다. 증명 가능한 것만 만든다.
                ★스트림 맨 위에 둔다 — 옛것은 위에 있다(entry_id 오름차순). */}
            {timelineHasMore && (
              <button
                type="button"
                data-timeline-load-older
                onClick={requestOlderTimeline}
                disabled={timelineLoadingMore}
                className="w-full max-w-[800px] self-center rounded-xl border border-border/15 bg-card/40 px-3 py-2.5 text-meta text-muted-foreground hover:bg-card/70 transition-colors disabled:opacity-60"
              >
                {timelineLoadingMore ? "불러오는 중…" : "이전 기록 불러오기"}
              </button>
            )}

            <div className="flex flex-col gap-8">
              {[
                // timestamp 없는 메시지는 ts=0으로 맨 위로 튀지 않게 — 직전 메시지
                // 시각을 승계해 입력 순서(아래로 쌓임)를 지킨다.
                // [STAGE-ONE 2026-08-02] "지금은 …입니다" 는 화면에 한 줄만 남는다.
                //   A-0 실측: Merope 를 열어도 새 행은 0이었다(ai_stage 32 -> 32).
                //   화면에 32줄이 보인 것은 그동안 쌓인 옛 행이 새로고침마다 다시
                //   렌더되던 것이다 — 쓰기는 이미 멎었고(55b72c4d) 남은 건 읽기였다.
                //   ★삭제가 아니라 렌더 제외다. 원장 32행은 그대로 둔다(A-4).
                //   ★"전부 흘러간다"와 충돌하지 않는다: 안내는 사건이 아니라
                //     '지금 어느 단계인가'라는 현재 상태의 표시다. 사건만 흐른다.
                //   ★제외를 복원 경로(Index.tsx:1620~)가 아니라 여기서 하는 이유:
                //     55b72c4d 의 가드가 storyPlan.messages 안의 마지막 ai_stage_* 를
                //     읽어 "같은 단계면 다시 말하지 않는다"를 판정한다. 복원에서 빼면
                //     그 가드가 lastKey=null 을 보고 다시 말하기 시작해 A-5(DELTA 0)가
                //     깨진다. 원장에는 남기고 화면에서만 접는다.
                //   ★문구가 아니라 id 접두로 가른다(생성부 Index.tsx `ai_stage_${key}_${ts}`).
                ...(() => {
                  const all = (storyPlan?.messages || []) as any[];
                  const isStage = (m: any) => String(m?.id ?? "").startsWith("ai_stage_");
                  let lastStageIdx = -1;
                  for (let i = all.length - 1; i >= 0; i--) { if (isStage(all[i])) { lastStageIdx = i; break; } }
                  let last = 0;
                  return all.map((msg: any, i: number) => {
                    last = typeof msg.timestamp === "number" && msg.timestamp > 0 ? msg.timestamp : last + 1;
                    // 가장 최근 안내 한 줄만 남기고 나머지 안내는 스트림에 담지 않는다.
                    if (isStage(msg) && i !== lastStageIdx) return null;
                    return { kind: "msg" as const, ts: last, msg };
                  }).filter(Boolean) as any[];
                })(),
                ...proposalHistory
                  .map((h) => ({ kind: "pair" as const, ts: h.ts, entry: h })),
                // [PERSON-PALETTE→FLOW] 인물 문답도 흐름 속 한 지점 — 이후 대화는 아래로
                ...(paletteTsRef.current && (pendingPersons.length > 0 || personSavedNote)
                  ? [{ kind: "palette" as const, ts: paletteTsRef.current }]
                  : []),
                // [CHAT-FLOW 2026-08-02 · CHAT-FLOW-3 분리] 전사와 편집안은 각각 다른 사건이다.
                //   국장 확정: 전부 흘러간다. 붙박이는 없다.
                //   ★ 없는 쪽은 아이템을 만들지 않는다 — 빈 말풍선을 띄우지 않는다.
                //   ts 는 지어내지 않는다:
                //     전사   = 원장의 transcript_ref 시각. 없으면 0(종전대로 맨 위).
                // [TIMELINE-REF 2026-08-02 정정] 위 줄은 원래 "전사 생성 시각을 들고 있는
                //   값이 프론트에 없다"였다. ★틀린 주석이었다 — 값은 두 개나 있었다.
                //   (1) roughCut.created_at 은 DB 에 있고 응답에도 실린다(main.py:6162).
                //       다만 그것은 '산출물이 만들어진 시각'이라 재생성하면 갱신된다
                //       (main.py:6325) — 대화 흐름의 자리로 쓸 수 없다.
                //   (2) 그래서 '대화에 등장한 시각'을 원장에 참조 사건으로 따로 남기고
                //       (transcript_ref · client_id=tref_<input_hash> 결정론) 그 값을 쓴다.
                //   실측이 시킨 일이다: ts=0 이면 8/1 에 만든 원고가 7/31 대화 위에 놓였다.
                //     편집안 = 가장 최근 편집안이 만들어진 시각(proposalHistory 승계).
                //              아직 없으면 0 이고, 그때는 배열 순서상 전사 다음에 온다
                //              (Array#sort 는 안정 정렬).
                // [LAYER-SPLIT 2026-08-04] 전사·편집안을 이 흐름에서 뺐다.
                //   둘은 대화가 아니라 작업물이다. 채팅 스크롤 밖 자기 층에서 산다.
                //   ★이 줄이 사라지면서 CHAT-FOLD 가 조각맵을 죽이던 경로도 함께 사라진다
                //     (8/3 사고: 접힘 -> 언마운트 -> onData(null) -> 조각맵 0).
              ]
                .sort((a, b) => a.ts - b.ts)
                // [CHAT-SKIN 2026-08-02] 날짜가 바뀌거나 한참 벌어졌을 때만 시간을 말한다.
                //   국장 지시: "날짜 바뀌면 간단한 표식... 시간 너무 지났으면 표식."
                //   참조 제품도 그렇다 — 줄마다 시각을 달지 않는다.
                //   ★배열 단계에서 끼워 넣는다. 아래 map 구조는 건드리지 않는다.
                .reduce((acc: any[], item: any, i: number, src: any[]) => {
                  const prev = i > 0 ? src[i - 1] : null;
                  // ★ 날짜가 바뀔 때만. 같은 날 안에서는 몇 시간이 벌어지든 긋지 않는다 —
                  //   국장: "같은 날짜면 이렇게 자주 안 해도 돼. 그냥 날짜인데."
                  //   (1시간 간격 표식을 넣었다가 같은 날에 여러 번 그어져 걷어냈다)
                  if (item.ts > 0 && (
                    !prev || prev.ts <= 0 ||
                    new Date(prev.ts).toDateString() !== new Date(item.ts).toDateString()
                  )) {
                    acc.push({ kind: "divider", ts: item.ts });
                  }
                  acc.push(item);
                  return acc;
                }, [])
                .map((item: any) => item.kind === "divider" ? (
                <div key={`divider_${item.ts}`} className="w-full flex items-center gap-3 py-2">
                  <span className="flex-1 h-px bg-border/15" />
                  <span className="text-micro text-muted-foreground">
                    {(() => {
                      // 날짜만 말한다. 시각은 말하지 않는다 — 구분선의 일은 날이 바뀌었음을
                      // 알리는 것뿐이다.
                      const d = new Date(item.ts);
                      return d.toDateString() === new Date().toDateString()
                        ? "오늘"
                        : d.toLocaleDateString([], { month: "long", day: "numeric" });
                    })()}
                  </span>
                  <span className="flex-1 h-px bg-border/15" />
                </div>
                ) : item.kind === "palette" ? (
                <div key="person_palette" className="flex flex-col gap-3">
                  {personSavedNote && (
                    <div className="flex justify-start animate-in fade-in duration-500">
                      {/* [CHAT-SKIN] 아이콘·말풍선 박스 제거 — AI 말은 글자만 흐른다 */}
                      <div className="w-full text-body text-foreground">
                        {personSavedNote}
                      </div>
                    </div>
                  )}
                  {pendingPersons.length > 0 && (
                    <div className="flex justify-start animate-in fade-in duration-500">
                      {/* [CHAT-SKIN] 아이콘·말풍선 박스 제거 */}
                      <div className="w-full">
                        <div className="w-full space-y-3">
                          <p className="text-body text-foreground">영상에 자주 나오는 분들이 보여요. 누구인지 알려주시면 편집할 때 이름으로 부를 수 있어요.</p>
                          <div className="flex flex-wrap gap-3">
                            {pendingPersons.map((p) => (
                              <div key={p.person_id} className="flex flex-col items-center gap-1.5 bg-black/20 rounded-lg p-2.5 w-[120px]">
                                <img
                                  src={p.face_url}
                                  alt="face"
                                  className="w-16 h-16 rounded-full object-cover border border-white/10"
                                />
                                <span className="text-[9px] text-muted-foreground/76">{p.appearances}개 장면 등장</span>
                                <input
                                  value={personNameDraft[p.person_id] ?? ""}
                                  onChange={(e) => setPersonNameDraft((prev) => ({ ...prev, [p.person_id]: e.target.value }))}
                                  onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) savePersonName(p.person_id); }}
                                  placeholder="이름"
                                  className="w-full bg-transparent border-b border-white/15 focus:border-primary/60 text-center text-[12px] text-foreground py-0.5 outline-none"
                                />
                                <div className="flex gap-1">
                                  <button
                                    onClick={() => savePersonName(p.person_id)}
                                    disabled={!(personNameDraft[p.person_id] ?? "").trim()}
                                    className="px-2 py-0.5 rounded text-[10px] font-bold bg-primary/15 text-primary hover:bg-primary hover:text-primary-foreground disabled:opacity-30 transition-all"
                                  >저장</button>
                                  <button
                                    onClick={() => rejectPerson(p.person_id)}
                                    className="px-2 py-0.5 rounded text-[10px] text-muted-foreground/60 hover:text-foreground transition-all"
                                  >건너뛰기</button>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                ) : item.kind === "msg" ? (
                // [CHAT-SKIN 2026-08-02 국장 지시 "일단은 같게"] 참조 제품(Claude·ChatGPT) 방식.
                //   지운 것: 줄마다 붙던 아이콘(BookOpen/List) · AI 답변의 말풍선 박스와 테두리.
                //   AI 답변은 배경 없이 글자만 흐른다 — 저쪽이 그렇고, 박스가 매 줄 반복되면
                //   국장 말대로 낭비다. 박스는 '내가 한 말'을 가르는 데만 쓴다.
                <div key={item.msg.id} className={`flex ${item.msg.sender === "user" ? "justify-end" : "justify-start"} animate-in fade-in duration-300`}>
                  <div className={`flex flex-col gap-1.5 ${item.msg.sender === "user" ? "items-end max-w-[80%]" : "items-start w-full"}`}>
                      <div className={`text-body whitespace-pre-wrap break-words ${
                        item.msg.sender === "user"
                          ? "px-4 py-2.5 rounded-2xl bg-secondary/40 text-foreground"
                          : "text-foreground"
                      }`}>
                        {/* [S-1] 스피너는 첫 토큰 전까지만 — say가 차오르기 시작하면 소거 */}
                        {item.msg.isInterpreting && !item.msg.text && (
                          <div className="flex items-center gap-2 text-primary/60">
                            <Loader2 size={14} className="animate-spin" />
                            <span className="text-[11px] font-medium animate-pulse">듣고 있어요…</span>
                          </div>
                        )}
                        {String(item.msg.text || "").replace(/\b\d{8}_\d{6}(?:_\d+)?\b/g, "")}
                      </div>
                      {/* [관문D 2026-07-21] 큐원 판단근거(대사·장면·맥락) 얇게 표시 — 없으면 "근거 없음" */}
                      {item.msg.sender === "ai" && (item.msg as any).candidate_evidence && Object.keys((item.msg as any).candidate_evidence).length > 0 && (
                        <div className="px-4 py-2 rounded-xl bg-secondary/5 border border-border/5 text-[11px] text-muted-foreground/70 space-y-1.5 max-w-full">
                          {Object.entries((item.msg as any).candidate_evidence).map(([fid, lines]: any) => {
                            const ev = (lines as string[]).filter((l) => !l.startsWith("meta:"));
                            return (
                              <div key={fid} className="space-y-0.5">
                                {ev.length === 0 ? (
                                  <div className="italic text-muted-foreground/70">근거 없음</div>
                                ) : ev.map((l: string, i: number) => {
                                  const label = l.startsWith("speech:") ? "대사" : l.startsWith("scene:") ? "장면" : l.startsWith("context:") ? "맥락" : "";
                                  const val = l.replace(/^(speech|scene|context):\s*/, "").slice(0, 80);
                                  return (
                                    <div key={i}><span className="text-primary/50 mr-1">✓ {label}</span>{val}</div>
                                  );
                                })}
                              </div>
                            );
                          })}
                        </div>
                      )}
                      {/* [SHOW] 조회 결과 카드 — 사람 말 명칭(제목·시간), 클릭=그 자리 재생 */}
                      {(item.msg as any).kind === "search_results" && Array.isArray((item.msg as any).results) && (item.msg as any).results.length > 0 && (
                        <SearchResultCards results={(item.msg as any).results} />
                      )}
                      {/* [CHAT-SKIN] 줄마다 붙던 시각 제거 — 국장 말대로 낭비다.
                          시간은 아래 구분선이 날짜가 바뀌거나 한참 벌어졌을 때만 말한다. */}
                  </div>
                </div>
                // [CHAT-ROOT 3-2 2026-08-02] 활성 제안 슬롯 제거.
                //   구판은 활성 pair 자리에 빈 div 를 두고 무대를 portal 로 그 안에 세웠다 —
                //   전사·플레이어가 **채팅 메시지들 사이에 끼는** 원인이었다.
                //   업계 규칙(Cloudscape): 아티팩트를 말풍선 안에 중첩하지 않는다.
                //   이제 활성이든 아니든 pair 는 카드 하나로만 남고(사건), 무대는 스트림
                //   밖 위에 선다(상태). 카드 클릭 -> activeProposalEntryId 갱신 -> 위 무대 전환.
                ) : (
                // [LAYER-FIX 2026-08-04 국장 확정 ③] '지난 원고' 접이식 블록을 없앤다.
                //   버전 줄(채팅 바로 위)이 그 일을 대신한다 — 지난 것을 보는 자리가 두 곳일
                //   이유가 없고, 이 블록은 (무음)(무음)… 만 늘어놓아 읽히지도 않았다.
                null
                ))}
            </div>

          </div>
        )}
        
        {/* [PERSON-PALETTE→FLOW] 팔레트는 이제 흐름 속 아이템으로 렌더 (위 타임라인 map) */}

        {/* [CHATSCROLL-FIX-01] 위에서 읽는 중에 새 내용이 오면 끌어내리지 않고 여기로 알린다.
            sticky라 기존 레이아웃을 건드리지 않는다 (높이 점유 없음). */}
        {chatHasNew && (
          <div className="sticky bottom-5 z-30 self-center pointer-events-none">
            {/* [C-2 2026-08-02] 동작은 옳았다 — 메시지는 정상 적재되는데 배지가 눈에 안 띄어
                국장이 '제안이 사라졌다'고 읽었다(실측 [CHATSCROLL][HOLD] user_scrolled_up).
                ★ 스크롤 로직은 손대지 않는다. 자동 추종으로 되돌리면 원래 결함으로 돌아간다.
                바꾼 것은 색·크기·위치뿐이다. */}
            <button
              type="button"
              onClick={scrollChatToBottom}
              className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-primary/50 bg-primary px-4 py-2 text-[13px] font-bold text-primary-foreground shadow-[0_4px_20px_-2px_hsl(var(--primary)/0.75)] ring-2 ring-primary/25 animate-pulse hover:animate-none hover:brightness-110"
            >
              새 내용 도착 ↓
            </button>
          </div>
        )}

        {/* [FLOW] 자동 스크롤 목적지 — 흐름의 최신 지점 */}
        <div ref={chatEndRef} />

      </div>
      </>
    );
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#0a0a0b] items-center overflow-hidden relative">
      {renderContent()}

      <ComposerSection
        storyPlan={storyPlan}
        appState={appState}
        onAddVideoFiles={onAddVideoFiles}
        onRequestAddVideos={onRequestAddVideos}
        handleUpload={handleUpload}
        consultationTextareaRef={consultationTextareaRef}
        consultationInput={consultationInput}
        setConsultationInput={setConsultationInput}
        resizeConsultationTextarea={resizeConsultationTextarea}
        handleSubmitConsultation={handleSubmitConsultation}
        chatValue={chatValue}
        setChatValue={setChatValue}
        handleSendFull={handleSendFull}
      />
    </div>
  );
};

export default CenterPanel;
