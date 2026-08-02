import React, { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, Send, PanelRightClose, PanelRightOpen } from "lucide-react";
import { fetcher } from "@/services/api";
import ResizeHandle from "@/components/ResizeHandle";

// [ADMIN-AI-LIVE 2026-08-02 C-1] 패널 폭 — 화면을 옮겨도 이 세션 동안은 유지된다.
//   저장소를 새로 만들지 않는다(지시서 금지). 모듈 메모리라 앱을 새로 열면 기본값이다.
const PANEL_WIDTH_DEFAULT = 288;   // 구판 w-72 와 같은 값
const PANEL_WIDTH_MIN = 240;
const PANEL_WIDTH_MAX = 640;
let sessionPanelWidth = PANEL_WIDTH_DEFAULT;

// [War Room v1] 공통 AI 보조 패널 — 전 관리자 화면 우측에 부착.
// read/query only: 이 패널에서 write 액션 실행 금지 (지시서 §STEP1).
// 일반 탭 권장 행동은 /admin/situation, EDIT LAB은 동일 감사 응답에서 도출한다.

interface QueryResult {
  query?: string;
  result?: string;
  error?: string;
  detail?: string;
  turns_carried?: number;   // [B-2] 이 답이 몇 턴을 기억하고 나왔는지 (백엔드 실측)
  // [UNMUZZLE 3] 이 답을 내려고 AI 가 직접 조회한 횟수. 0이면 지표만 보고 답한 것이다.
  tool_calls?: number;
  tool_round_limit?: boolean;
}

interface SituationLite {
  alerts?: { severity: string; title: string; recommended_action: string }[];
  action_queue?: { kind: string; title: string; priority: string }[];
}

interface LabAudit {
  materials?: { id: string; label: string; non_null: number; total: number }[];
  rules?: { declared: number; registered: number; unregistered: number };
  techniques?: { declared: number; wired: number; wireable_unwired: number };
  edges?: { status: string }[];
}

export const AdminAIPanel: React.FC<{
  screen: string;
  contextSource?: "lab";
}> = ({ screen, contextSource }) => {
  const [open, setOpen] = useState(true);
  const [situation, setSituation] = useState<SituationLite | null>(null);
  const [situationError, setSituationError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<QueryResult[]>([]);
  // [B-4] 답을 기다리는 동안 화면에 남는 내 질문 (오래된 것 위 → 최신 아래 순서).
  const [pending, setPending] = useState<string | null>(null);
  const [labAudit, setLabAudit] = useState<LabAudit | null>(null);
  // [LAB-52 ②] 감사 조회 실패를 '이상 없음'과 구분한다 (상황실 쪽 situationError와 같은 방식).
  const [labError, setLabError] = useState<string | null>(null);
  // [ADMIN-AI-LIVE B-4] 대화가 위로 쌓이고 입력은 아래 고정 — 답이 오면 하단을 따라간다.
  //   CenterPanel 의 하단 근접 판정(CHATSCROLL-FIX-01, slack 120px)과 같은 규칙을 쓴다.
  //   손짓 감지까지 복제하지 않는 이유: 이 패널의 새 내용은 전부 사용자가 방금 던진
  //   질문의 답이다 — 백그라운드로 도착하는 카드가 없어 오판할 대상 자체가 없다.
  const logRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const CHAT_BOTTOM_SLACK = 120;
  const isNearBottom = useCallback(() => {
    const el = logRef.current;
    if (!el) return true;
    if (el.scrollHeight <= el.clientHeight + 4) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight <= CHAT_BOTTOM_SLACK;
  }, []);
  // [C-1] 폭 — 세션 값에서 시작해 드래그로 바꾼다.
  const [width, setWidth] = useState(sessionPanelWidth);
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);

  useEffect(() => {
    fetcher("/admin/situation")
      .then(setSituation)
      .catch(e => setSituationError(String(e)));
  }, []);

  useEffect(() => {
    if (contextSource !== "lab") {
      setLabAudit(null);
      setLabError(null);
      return;
    }
    setLabError(null);
    fetcher("/lab/audit")
      .then(audit => { setLabAudit(audit); setLabError(null); })
      .catch(e => { setLabAudit(null); setLabError(String(e)); });
  }, [contextSource]);

  // [C-1] 좌측 경계 드래그. 문서 레벨에서 듣다가 버튼을 떼면 끝낸다.
  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startW: width };
    const onMove = (ev: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      // 왼쪽 경계라 왼쪽으로 끌수록 넓어진다.
      const next = Math.min(PANEL_WIDTH_MAX,
        Math.max(PANEL_WIDTH_MIN, d.startW + (d.startX - ev.clientX)));
      sessionPanelWidth = next;
      setWidth(next);
    };
    const onUp = () => {
      dragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [width]);

  // [B-4] 새 내용·대기 표시가 붙으면 하단으로 따라간다 (하단 근처에 있을 때만).
  useEffect(() => {
    if (isNearBottom()) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [history, loading, isNearBottom]);

  const ask = async () => {
    const q = query.trim();
    if (!q || loading) return;
    setLoading(true);
    setQuery("");
    // [B-4] 질문을 먼저 화면에 올린다 — 답을 기다리는 동안 무엇을 물었는지 보인다.
    setPending(q);
    // [B-2] 이전 대화를 함께 보낸다. 실패한 턴(result 없음)은 빼고 오래된 것부터.
    //   화면이 보관하는 것 이상은 보내지 않고, 몇 턴을 쓸지는 백엔드가 자른다.
    const carried = history
      .filter(h => h.query && h.result)
      .map(h => ({ query: h.query, result: h.result }));
    try {
      const r = await fetcher("/admin/ai/query", {
        method: "POST",
        body: JSON.stringify({
          role: "ops_brief",
          query: `[화면: ${screen}] ${q}`,
          history: carried,
          ...(labAudit ? { context: { screen: "편집연구실", audit: labAudit } } : {}),
        }),
      }) as QueryResult;
      setHistory(prev => [...prev, r].slice(-20));
    } catch (e) {
      setHistory(prev => [...prev, { query: q, error: String(e) }].slice(-20));
    } finally {
      setPending(null);
      setLoading(false);
    }
  };

  const lockedMaterials = labAudit?.materials?.filter(item => item.non_null === 0) ?? [];
  const labRecommended = labAudit ? [
    lockedMaterials.length > 0
      ? `[LOCKED ${lockedMaterials.length}] ${lockedMaterials.map(item => item.label).join(", ")} 생산 경로 확인`
      : null,
    (labAudit.rules?.unregistered ?? 0) > 0
      ? `[BROKEN ${labAudit.rules?.unregistered}] 하드룰 선언·registry ID 연결 확인`
      : null,
    // [NERVE-1] 미배선 정의 통일(국장 결정 2026-07-30) — declared-wired(모수 어긋난 24) 폐기,
    //   편집연구실 화면과 같은 wireable_unwired(즉시 배선 가능) 하나만 쓴다.
    (labAudit.techniques?.wireable_unwired ?? 0) > 0
      ? `[즉시 배선 가능 ${labAudit.techniques?.wireable_unwired}] 기법 배선 후보 검토`
      : null,
  ].filter((item): item is string => Boolean(item)) : [];
  const recommended = contextSource === "lab"
    ? labRecommended
    : [
      ...(situation?.alerts ?? []).map(a => `[${a.severity}] ${a.recommended_action}`),
      ...(situation?.action_queue ?? []).map(w => `[${w.priority}] ${w.title}`),
    ].slice(0, 3);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="AI 보조 패널 열기"
        className="w-9 flex-shrink-0 border-l border-border/15 bg-[hsl(228_12%_9%)] flex items-start justify-center pt-4 text-muted-foreground/76 hover:text-primary transition-colors"
      >
        <PanelRightOpen size={15} />
      </button>
    );
  }

  return (
    <aside
      style={{ width }}
      className="relative flex-shrink-0 border-l border-border/15 bg-[hsl(228_12%_9%)] flex flex-col"
    >
      {/* [DRAG-ONE 2026-08-02] 공용 손잡이로 교체.
          구판은 여기만 음수 마진(-6px)으로 옆으로 삐져나와 있어, 관제실에서 옆 칸의
          손잡이와 서로 물려 잡히지 않았다(국장 실사용 보고). overlay 는 음수 마진을 쓰지 않는다. */}
      <ResizeHandle variant="overlay" side="left" onStart={onDragStart} />
      <div className="px-4 py-3 border-b border-border/15 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkles size={13} className="text-primary" />
          <p className="text-xs font-bold text-foreground/90">AI 보조</p>
        </div>
        <button onClick={() => setOpen(false)} title="접기"
          className="text-muted-foreground/70 hover:text-foreground/80 transition-colors">
          <PanelRightClose size={14} />
        </button>
      </div>

      <div className="px-4 py-3 border-b border-border/10">
        <p className="text-[10px] font-semibold text-muted-foreground/76 uppercase">현재 화면</p>
        <p className="text-xs font-bold text-foreground/80 mt-0.5">{screen}</p>
      </div>

      <div className="px-4 py-3 border-b border-border/10">
        {/* [ADMIN-AI-LIVE 2026-08-02 B-6] 라벨 정직화.
            이 목록은 AI 응답이 아니다 — 일반 탭은 /admin/situation 의 경보·대기작업을,
            EDIT LAB 은 /lab/audit 수치를 그대로 옮긴 것이다(:96-101 실측 확인).
            그래서 화면이 바뀌어도 같은 세 줄이 나왔다. 출처대로 이름을 붙인다. */}
        <p className="text-[10px] font-semibold text-muted-foreground/76 uppercase mb-1.5">
          {contextSource === "lab" ? "감사 결과 요약" : "상황실 경보 · 대기 작업"}
        </p>
        {/* [LAB-52 ②] 조회 실패·측정 전은 '이상 없음'이 아니다. 셋을 각각 다르게 표기한다. */}
        {contextSource === "lab" && labError ? (
          <p className="text-[11px] text-red-400/80">편집연구실 감사 조회 실패 — {labError}</p>
        ) : contextSource !== "lab" && situationError ? (
          <p className="text-[11px] text-red-400/80">상황실 데이터 연결 실패 — {situationError}</p>
        ) : contextSource === "lab" && !labAudit ? (
          <p className="text-[11px] text-muted-foreground/70">감사 결과 확인 중...</p>
        ) : recommended.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/70">현재 경보·대기 작업 없음</p>
        ) : (
          <ul className="space-y-1">
            {recommended.map((r, i) => (
              <li key={i} className="text-[11px] text-foreground/70 leading-snug">· {r}</li>
            ))}
          </ul>
        )}
      </div>

      {/* [ADMIN-AI-LIVE 2026-08-02 B-4] 대화가 위로 쌓이고 입력은 아래 고정.
          구판은 입력이 위, 답이 아래로 내려가 최신이 화면 밖으로 밀렸다(국장 지적). */}
      <div ref={logRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {history.length === 0 && !pending && (
          <p className="text-[11px] text-muted-foreground/60 leading-snug">
            운영 지표를 근거로 묻고 답합니다. 앞선 대화를 기억합니다.
          </p>
        )}
        {history.map((h, i) => (
          <div key={i} className="space-y-1">
            <p className="text-[11px] text-foreground/70 text-right leading-snug">
              <span className="inline-block rounded-md bg-secondary/40 px-2 py-1">{h.query}</span>
            </p>
            <div className="rounded-md border border-border/10 bg-card/20 p-2.5">
              {h.error ? (
                <p className="text-[11px] text-red-400">{h.error}{h.detail ? ` — ${h.detail}` : ""}</p>
              ) : (
                <p className="text-[11px] text-foreground/80 leading-snug whitespace-pre-wrap">{h.result}</p>
              )}
              {/* [B-2] 기억이 실제로 실려 갔는지 화면에서 확인할 수 있게. 0턴이면 표시하지 않는다.
                  [UNMUZZLE 3] 직접 조회 횟수 — 스스로 봤는지 지표만 읽었는지가 여기서 갈린다. */}
              {!h.error && ((h.turns_carried ?? 0) > 0 || (h.tool_calls ?? 0) > 0) && (
                <p className="text-[10px] text-muted-foreground/50 mt-1.5">
                  {[(h.turns_carried ?? 0) > 0 ? `앞선 대화 ${h.turns_carried}턴 기억` : null,
                    (h.tool_calls ?? 0) > 0 ? `직접 조회 ${h.tool_calls}회` : null,
                    h.tool_round_limit ? "왕복 상한 도달(못 본 것 있음)" : null,
                  ].filter(Boolean).join(" · ")}
                </p>
              )}
            </div>
          </div>
        ))}
        {pending && (
          <div className="space-y-1">
            <p className="text-[11px] text-foreground/70 text-right leading-snug">
              <span className="inline-block rounded-md bg-secondary/40 px-2 py-1">{pending}</span>
            </p>
            <p className="text-[11px] text-muted-foreground/60 flex items-center gap-1.5">
              <Sparkles size={11} className="animate-pulse text-primary" /> 생각하는 중...
            </p>
          </div>
        )}
        <div ref={logEndRef} />
      </div>

      <div className="px-4 py-3 border-t border-border/15 flex gap-1.5">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") ask(); }}
          placeholder="운영 질의..."
          className="flex-1 h-8 rounded-md bg-secondary/30 border border-border/15 px-2.5 text-[11px] text-foreground/90 outline-none focus:border-primary/40"
        />
        <button onClick={ask} disabled={loading}
          className="px-2.5 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-primary transition-colors disabled:opacity-50">
          {loading ? <Sparkles size={12} className="animate-pulse" /> : <Send size={12} />}
        </button>
      </div>
    </aside>
  );
};
