// [STRUCT-A③ 2026-08-08] 원고의 읽는 층 — 장면 띠.
//
// 개념서 §3: "카드 수백 개를 나열하지 않는다. 워드 문서를 읽듯이 전체 내용을 읽고,
//             문장을 클릭하면 해당 영상이 재생된다."
//
// 하루치를 찍으면 조각이 1,000개를 넘는다(실측 추정 5시간 → 1,441개).
// 그것을 통째로 그리면 화면이 죽고, 사람도 못 읽는다.
// 그래서 위에 읽는 층을 둔다 — 하루가 장면 열몇 개로 보이고, 하나를 고르면
// 그 장면의 조각만 아래층(원본맵)에 펼쳐진다.
//
// ★조각맵·원본맵을 없애지 않는다(국장 지침). 그것들은 PBE·소리·A/B가 매달린
//   검증된 화면이다. 여기서 하는 일은 '보이는 범위를 좁히는 것'뿐이다.
import { useEffect, useState } from "react";
import { videoService } from "@/services/videoService";

export interface Scene {
  group_no: number;
  label: string;
  source_id: string;
  start_ms: number;
  end_ms: number;
  item_count: number;
  place: string | null;
  top_tags: string[];
  fragment_ids: string[];
  dialogue_head: string | null;
}

const fmt = (ms: number) => {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

interface Props {
  programId: string | null;
  /** 고른 장면 (null = 전체 보기) */
  selected: number | null;
  onSelect: (scene: Scene | null) => void;
  /** 원고가 아직 없으면 띠 자체를 감춘다 */
  className?: string;
}

const SceneStrip: React.FC<Props> = ({ programId, selected, onSelect, className }) => {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!programId || !programId.startsWith("proj_")) {
      setScenes([]);
      return;
    }
    let alive = true;
    setLoading(true);
    setFailed(false);
    fetch(`${videoService.API_BASE_URL}/ledger/${encodeURIComponent(programId)}/scenes`)
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        if (d?.ok && Array.isArray(d.scenes)) {
          setScenes(d.scenes);
          console.info("[SCENE-STRIP] 장면", d.scene_count, "개");
        } else {
          setFailed(true);
        }
      })
      .catch((e) => {
        if (alive) setFailed(true);
        console.warn("[SCENE-STRIP] 장면 불러오기 실패 — 전체 보기로 둔다:", e?.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [programId]);

  // 실패하거나 장면이 없으면 아무것도 그리지 않는다 — 아래층은 종전대로 전체를 본다.
  if (failed || (!loading && scenes.length === 0)) return null;

  const total = scenes.reduce((n, s) => n + s.item_count, 0);

  return (
    <div className={className} data-scene-strip>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[11px] text-muted-foreground/70">
          {loading ? "장면을 훑는 중…" : `찍어 온 것 — 장면 ${scenes.length}개 · 조각 ${total}개`}
        </span>
        {selected !== null && (
          <button
            type="button"
            data-scene-all
            onClick={() => onSelect(null)}
            className="text-[11px] text-primary hover:text-primary/80 transition-colors"
          >
            전체 보기
          </button>
        )}
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {scenes.map((s) => {
          const on = selected === s.group_no;
          return (
            <button
              key={s.group_no}
              type="button"
              data-scene-chip={s.group_no}
              title={`${fmt(s.start_ms)}~${fmt(s.end_ms)} · 조각 ${s.item_count}개${
                s.dialogue_head ? `\n"${s.dialogue_head}"` : ""
              }`}
              onClick={() => onSelect(on ? null : s)}
              className={
                "shrink-0 px-2.5 py-1.5 rounded-lg border text-left transition-colors " +
                (on
                  ? "bg-primary/20 border-primary/40"
                  : "bg-secondary/10 border-border/20 hover:border-border/40")
              }
            >
              <div className="text-[11px] leading-tight">
                <span className="text-muted-foreground/60 mr-1">{s.group_no}</span>
                {s.label}
              </div>
              <div className="text-[10px] text-muted-foreground/55 leading-tight">
                {fmt(s.start_ms)} · {s.item_count}조각
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default SceneStrip;
