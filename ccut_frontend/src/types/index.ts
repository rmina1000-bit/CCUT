// CCUT 1.0.4 — 공유 도메인 타입 단일 출처 (REFACTOR: AppState/SourceEntry 중복 통합)
import type { Fragment } from "@/data/fragmentData";

export type AppState = "empty" | "analyzing" | "complete";

export type SourceEntry = {
  source_id: string;
  label: string;
  // [DISPLAY-NAME] 원본 제목(파일명) — 라벨(A,B..)만으론 어느 영상인지 알 수 없다
  title?: string;
  display_name?: string | null;
  video_url: string;
  fragments: Fragment[];
  file_size_bytes?: number;
  duration_sec?: number;
};
