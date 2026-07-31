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
  | "export";

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
