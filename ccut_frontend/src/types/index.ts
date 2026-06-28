// CCUT 1.0.4 — 공유 도메인 타입 단일 출처 (REFACTOR: AppState/SourceEntry 중복 통합)
import type { Fragment } from "@/data/fragmentData";

export type AppState = "empty" | "analyzing" | "complete";

export type SourceEntry = {
  source_id: string;
  label: string;
  video_url: string;
  fragments: Fragment[];
  file_size_bytes?: number;
  duration_sec?: number;
};
