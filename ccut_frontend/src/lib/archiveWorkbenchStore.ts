import { useSyncExternalStore } from "react";

// [작업대 상태 유지 국장지시 2026-07-06 B] ArchiveWorkbench의 작업 상태를 컴포넌트 밖
// module store에 둔다 — 메뉴/탭/프로젝트 이동으로 컴포넌트가 unmount돼도 유지되고,
// 페이지 새로고침(모듈 재로드) 시에만 초기화된다. DB 미저장(세션 한정).

export interface FragmentCard {
  fragment_id: string;
  source_id: string;
  display_name: string | null;
  thumbnail_url: string | null;
  video_url: string | null;
  start: number | null;
  end: number | null;
  people: string | null;
  places: string | null;
  evidence: Record<string, any> | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text?: string;
  resultType?: string;
  results?: FragmentCard[];
}

export interface SourceFragment {
  fragment_id: string;
  display_name: string | null;
  thumbnail_url: string | null;
  start: number | null;
  end: number | null;
  eff_start: number | null;
  eff_end: number | null;
}

export interface SourceDetail {
  source_id: string;
  title: string;
  shot_date: string | null;
  play_url: string | null;
  fragments: SourceFragment[];
}

export interface SourceSlot {
  label: string;
  detail: SourceDetail;
}

export interface BasketItem {
  fragment_id: string;
  source_id: string;
  source_title: string;
  thumbnail_url: string | null;
  video_url: string | null;
  start: number | null;
  end: number | null;
  display_name: string | null;
}

export interface ExportResult {
  ok_count: number;
  duration_sec: number;
  export_dir: string;
  failed: { fragment_id: string; reason: string }[];
}

interface WBState {
  messages: ChatMessage[];
  slots: SourceSlot[];
  activeSourceId: string | null;
  matchedIds: string[];              // Set 대신 배열 — 새창 BroadcastChannel 직렬화 대비(C단계)
  basket: Record<string, BasketItem>;
  exportResult: ExportResult | null;
}

let state: WBState = {
  messages: [], slots: [], activeSourceId: null,
  matchedIds: [], basket: {}, exportResult: null,
};

const listeners = new Set<() => void>();
const emit = () => listeners.forEach(l => l());

export const workbenchStore = {
  getState: () => state,
  setState: (partial: Partial<WBState>) => { state = { ...state, ...partial }; emit(); },
  // functional 갱신 헬퍼 (basket 등 prev 기반 수정)
  update: (fn: (s: WBState) => Partial<WBState>) => { state = { ...state, ...fn(state) }; emit(); },
  subscribe: (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; },
};

export function useWorkbenchStore(): WBState {
  return useSyncExternalStore(workbenchStore.subscribe, workbenchStore.getState, workbenchStore.getState);
}
