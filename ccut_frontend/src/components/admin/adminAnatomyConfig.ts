export type AnatomyStatus =
  | "normal"
  | "slow"
  | "broken"
  | "idle"
  | "processing"
  | "unmeasured";

export type AnatomyNodeId =
  | "upload"
  | "analysis"
  | "transcript"
  | "fragment"
  | "story"
  | "edit"
  | "render"
  | "export"
  // [MAP-R2] 채팅 계열 — 오늘 감사한 결함 넷이 여기서 났는데 지도에 없었다.
  | "chat"
  | "intent"
  | "consult"
  | "search"
  | "editcmd"
  | "proposal"
  | "hold";

export interface AnatomyNodeDefinition {
  id: AnatomyNodeId;
  label: string;
  description: string;
  related: AnatomyNodeId[];
  metricKey?: "source_count" | "semantic_fragment_count" | "export_success_count";
  metricLabel?: string;
}

export interface AnatomyEdgeDefinition {
  from: AnatomyNodeId;
  to: AnatomyNodeId;
  declared: boolean;
  evidence: string;
}

export const ANATOMY_MENU_ENABLED =
  import.meta.env.VITE_CCUT_ADMIN_ANATOMY === "ON";

export const ANATOMY_NODES: AnatomyNodeDefinition[] = [
  {
    id: "upload",
    label: "업로드",
    description: "영상이 CCUT에 들어와 원본으로 등록되는 자리입니다.",
    related: ["analysis"],
    metricKey: "source_count",
    metricLabel: "원본",
  },
  {
    id: "analysis",
    label: "분석",
    description: "등록된 영상에서 제작에 필요한 재료를 찾는 자리입니다.",
    related: ["upload", "transcript"],
  },
  {
    // [ANATOMY] 중복주의: 능력지도에도 등장하지만, 여기는 현재 데이터의 통과 여부만 본다.
    // 능력 여부와 수치는 새로 계산하지 않고 /lab/audit 값을 참조한다.
    id: "transcript",
    label: "전사",
    description: "영상의 말을 시간 순서가 있는 글로 만드는 자리입니다.",
    related: ["analysis", "fragment"],
  },
  {
    // [ANATOMY] 중복주의: 능력지도에도 등장하지만, 여기는 현재 데이터의 통과 여부만 본다.
    // fragment_vault_count와 합치지 않고 _service_counts.semantic_fragment_count만 표시한다.
    id: "fragment",
    label: "조각",
    description: "원본을 다시 찾고 배열할 수 있는 제작 조각으로 나누는 자리입니다.",
    related: ["transcript", "story"],
    metricKey: "semantic_fragment_count",
    metricLabel: "조각",
  },
  {
    // [ANATOMY] 중복주의: 능력지도에도 등장하지만, 여기는 현재 데이터의 통과 여부만 본다.
    // Qwen 상태는 ui_state.roughCut.generation에 남은 값만 사용한다.
    id: "story",
    label: "스토리",
    description: "전사에서 핵심을 골라 이야기의 첫 구성을 세우는 자리입니다.",
    related: ["fragment", "edit"],
  },
  {
    // [ANATOMY] 중복주의: 능력지도에도 등장하지만, 여기는 현재 데이터의 통과 여부만 본다.
    // 편집 상태는 /edit-state와 vault_events의 edit_command 영수증만 읽는다.
    id: "edit",
    label: "편집",
    description: "사용자의 선택을 실제 사용 구간과 순서로 확정하는 자리입니다.",
    related: ["story", "render"],
  },
  {
    // [ANATOMY] 중복주의: 능력지도에도 등장하지만, 여기는 현재 데이터의 통과 여부만 본다.
    // 렌더 능력과 현재 흐름 상태를 같은 값으로 간주하지 않는다.
    id: "render",
    label: "렌더",
    description: "확정된 편집을 재생 가능한 영상으로 계산하는 자리입니다.",
    related: ["edit", "export"],
  },
  {
    id: "export",
    label: "Export",
    description: "완성된 영상을 사용자가 꺼내 쓸 수 있게 내보내는 자리입니다.",
    related: ["render"],
    metricKey: "export_success_count",
    metricLabel: "내보내기",
  },
];

export const ANATOMY_CHAT_NODES: AnatomyNodeDefinition[] = [
  { id: "chat", label: "채팅", description: "사용자의 말이 들어오는 자리입니다.", related: ["intent"] },
  { id: "intent", label: "의도판정", description: "그 말이 상담인지 검색인지 편집지시인지 가르는 자리입니다.", related: ["chat", "consult", "search", "editcmd"] },
  { id: "consult", label: "상담", description: "판별에 실패해도 편집이 아니라 상담으로 돌아옵니다(LAB-50 ①).", related: ["intent", "chat"] },
  { id: "search", label: "조각검색", description: "말로 조각을 찾아 조각맵으로 흘려보내는 자리입니다.", related: ["intent", "fragment"] },
  { id: "editcmd", label: "편집지시", description: "말이 편집 지시로 해석된 자리입니다.", related: ["intent", "proposal"] },
  { id: "proposal", label: "제안생성", description: "승인된 스토리로 A/B를 만드는 자리입니다.", related: ["editcmd", "story"] },
  { id: "hold", label: "보류맵", description: "지금 쓰지 않는 조각을 내려놓는 자리입니다. 조각맵과 왕복합니다.", related: ["fragment"] },
];


export const ANATOMY_EDGES: AnatomyEdgeDefinition[] = [
  {
    from: "upload",
    to: "analysis",
    declared: true,
    evidence: "/upload -> /generate-fragments",
  },
  {
    from: "analysis",
    to: "transcript",
    declared: true,
    evidence: "main.py::_background_whisper_impl",
  },
  {
    from: "transcript",
    to: "fragment",
    declared: false,
    evidence: "UNDECLARED: 전사와 조각 생성은 단일 직렬 영수증이 없음",
  },
  {
    from: "fragment",
    to: "story",
    declared: true,
    evidence: "/rough-cut/project/{program_id}",
  },
  {
    from: "story",
    to: "edit",
    declared: false,
    evidence: "UNDECLARED: 사용자 승격과 대사 수정 사이 통합 영수증이 없음",
  },
  {
    from: "edit",
    to: "render",
    declared: true,
    evidence: "fragment_edit_state -> compile_spans",
  },
  {
    from: "render",
    to: "export",
    declared: false,
    evidence: "UNDECLARED: 렌더와 내보내기 성공 사이 단일 흐름 영수증이 없음",
  },
];

/* ── [MAP-R2] 판: 좌표는 우리가 정한다 ──────────────────────────────────────────
 *
 * 물리 자동배치를 쓰지 않는 이유: Vizceral 은 노드가 수백 개라 사람이 놓을 수 없어서
 * 물리에 맡긴다. CCUT 은 파이프라인 순서가 이미 정해져 있다 — 물리에 맡기면 매번 다른
 * 모양이 나오고, 위치가 아무 뜻도 나르지 못한다. 그게 진짜 성의 없는 것이다.
 *
 * 판의 문법 (모양 자체가 정보):
 *   위쪽 호(arc)  = 사용자의 말. 채팅에서 시작해 의도판정에서 셋으로 갈라진다.
 *   가운데 띠     = 재료가 흐르는 본선. 왼쪽에서 오른쪽으로.
 *   아래          = 본선에 매달린 것(보류맵) — 본선과 왕복한다.
 *   본선 아래 호  = 되돌아가는 길(재승인). 순방향과 절대 겹치지 않게 아래로 부푼다.
 * 세 갈래의 말이 각기 다른 자리로 내려꽂히는 모양이 곧 '의도판정이 셋으로 갈린다'는 사실이다.
 */
export type AnatomyRelationKind = "forward" | "back" | "bidir" | "branch" | "merge";

export interface AnatomyNodePlacement {
  id: AnatomyNodeId;
  x: number;
  y: number;
  /** 계열 — 색과 형태를 가른다. 장식이 아니라 '어느 세계의 것인가'다. */
  band: "chat" | "main" | "aside";
}

export interface AnatomyRelation {
  from: AnatomyNodeId;
  to: AnatomyNodeId;
  kind: AnatomyRelationKind;
  /** 근거 없는 선은 그리지 않는다 — 코드에서 확인된 자리만 적는다. */
  evidence: string;
  /** 곡률(양수=아래로 부풀음). 되돌아가는 길을 순방향과 눈으로 가르는 유일한 수단. */
  bow?: number;
}

export const ANATOMY_CANVAS = { width: 1000, height: 560 };

export const ANATOMY_PLACEMENT: AnatomyNodePlacement[] = [
  // 위쪽 호 — 사용자의 말
  { id: "chat", x: 430, y: 58, band: "chat" },
  { id: "intent", x: 430, y: 142, band: "chat" },
  { id: "consult", x: 215, y: 232, band: "chat" },
  { id: "search", x: 430, y: 232, band: "chat" },
  { id: "editcmd", x: 650, y: 232, band: "chat" },
  { id: "proposal", x: 790, y: 232, band: "chat" },
  // 가운데 띠 — 재료의 본선
  { id: "upload", x: 70, y: 372, band: "main" },
  { id: "analysis", x: 178, y: 372, band: "main" },
  { id: "transcript", x: 296, y: 372, band: "main" },
  { id: "fragment", x: 430, y: 372, band: "main" },
  { id: "story", x: 566, y: 372, band: "main" },
  { id: "edit", x: 700, y: 372, band: "main" },
  { id: "render", x: 828, y: 372, band: "main" },
  { id: "export", x: 936, y: 372, band: "main" },
  // 아래 — 본선에 매달린 것
  { id: "hold", x: 430, y: 496, band: "aside" },
];

export const ANATOMY_RELATIONS: AnatomyRelation[] = [
  // 말의 갈래
  { from: "chat", to: "intent", kind: "forward",
    evidence: "CenterPanel.tsx:732 fragment search -> parseDirectionFromText -> 상담" },
  { from: "intent", to: "consult", kind: "branch",
    evidence: "CenterPanel.tsx:745 판별 실패 기본값 = 상담 (LAB-50 ①)" },
  { from: "intent", to: "search", kind: "branch",
    evidence: "CenterPanel.tsx:732 sr.is_search -> setFragSearch" },
  { from: "intent", to: "editcmd", kind: "branch",
    evidence: "CenterPanel.tsx:743 parsedDirection -> onReproposal" },
  { from: "consult", to: "chat", kind: "back", bow: -46,
    evidence: "상담은 채팅으로 돌아온다 (onConsultation)" },
  { from: "editcmd", to: "proposal", kind: "forward",
    evidence: "useProposalState.ts:660 /intent/route-edit -> handleReproposal" },
  // 말이 본선으로 내려꽂히는 자리
  { from: "search", to: "fragment", kind: "merge",
    evidence: "조각 검색 결과가 조각맵으로 (setFragSearch)" },
  { from: "proposal", to: "story", kind: "merge",
    evidence: "useProposalState.ts:420 sequence -> key_fragments -> 스토리" },
  // 본선
  { from: "upload", to: "analysis", kind: "forward", evidence: "/upload -> /generate-fragments" },
  { from: "analysis", to: "transcript", kind: "forward", evidence: "main.py::_background_whisper_impl" },
  { from: "transcript", to: "fragment", kind: "forward", evidence: "semantic_engine 조각화" },
  { from: "fragment", to: "story", kind: "forward", evidence: "ui_state.story.fids (사용자 결정)" },
  { from: "story", to: "edit", kind: "forward", evidence: "story_gate.approve -> fragment_edit_state" },
  { from: "edit", to: "render", kind: "forward", evidence: "fragment_edit_state -> compile_spans (ledger_r0)" },
  { from: "render", to: "export", kind: "forward", evidence: "EDL clips -> render_engine" },
  // 되돌아가는 길 — 이 선이 보이는 순간 시간표가 지도가 된다
  { from: "edit", to: "story", kind: "back", bow: 74,
    evidence: "useStoryGate.ts:54 reopenStory -> story_review 복귀 (Index.tsx:252)" },
  // 왕복
  { from: "fragment", to: "hold", kind: "bidir",
    evidence: "Index.tsx:268 holdPositions — 조각맵 <-> 보류맵 (제안별 아님, 프로젝트 스코프)" },
];

export const ANATOMY_STATUS: Record<
  AnatomyStatus,
  { label: string; meaning: string }
> = {
  normal: { label: "정상", meaning: "일하고 있음" },
  slow: { label: "느림", meaning: "작동하나 기준선 초과" },
  broken: { label: "끊김", meaning: "여기서 흐름이 멈춤" },
  idle: { label: "유휴", meaning: "연결됐으나 지금 안 쓰임" },
  processing: { label: "처리중", meaning: "진행 중" },
  unmeasured: { label: "미계측", meaning: "계측 없음" },
};
