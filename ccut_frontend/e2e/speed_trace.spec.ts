import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND_URL = process.env.CCUT_FRONTEND_URL || "http://127.0.0.1:5173/";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TRACE_PATH = path.resolve(__dirname, "../../logs/trace/speed_trace.jsonl");
const API_BASE_URL = process.env.CCUT_API_BASE_URL || "http://127.0.0.1:8011";
const MEROPE_PROJECT_ID = "proj_f6be58f81e4f";

function readTraceLines(): string[] {
  if (!fs.existsSync(TRACE_PATH)) return [];
  return fs.readFileSync(TRACE_PATH, "utf8").split(/\r?\n/).filter(Boolean);
}

function parseTraceLines(lines: string[]): any[] {
  return lines.map((line) => {
    try { return JSON.parse(line); } catch { return null; }
  }).filter(Boolean);
}

async function latestAssistantText(page: any): Promise<string> {
  return await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('.justify-start [class*="whitespace-pre-wrap"]'));
    return String((rows[rows.length - 1] as HTMLElement | undefined)?.innerText || "");
  });
}

async function latestTimelineAssistant(): Promise<{ text: string; source: string }> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(MEROPE_PROJECT_ID)}/timeline?limit=30`);
    if (!res.ok) return { text: "", source: `timeline_http_${res.status}` };
    const data = await res.json() as any;
    const entries = Array.isArray(data?.entries) ? data.entries : [];
    for (let i = entries.length - 1; i >= 0; i--) {
      const payload = entries[i]?.payload || {};
      if (payload.sender === "ai" && typeof payload.text === "string") {
        return { text: payload.text, source: "project_timeline" };
      }
    }
    return { text: "", source: "project_timeline_empty" };
  } catch (e: any) {
    return { text: "", source: `timeline_error:${e?.message || e}` };
  }
}

async function installTraceAugment(page: any) {
  await page.route("**/trace/speed", async (route: any) => {
    const request = route.request();
    let payload: any = {};
    try { payload = JSON.parse(request.postData() || "{}"); } catch {}
    await page.waitForTimeout(80);
    const screenText = await latestAssistantText(page);
    const db = await latestTimelineAssistant();
    payload.screen_text = screenText;
    payload.db_assistant_text = db.text;
    payload.db_assistant_source = db.source;
    payload.client_abort = false;
    await route.continue({
      headers: { ...request.headers(), "content-type": "application/json" },
      postData: JSON.stringify(payload),
    });
  });
}

async function openMerope(page: any) {
  await page.addInitScript(() => {
    window.localStorage.setItem("CCUT_TRACE", "1");
  });
  await installTraceAugment(page);
  await page.goto(FRONTEND_URL, { waitUntil: "domcontentloaded" });
  await page.getByText("Merope", { exact: true }).click();
  await page.waitForFunction(
    () => Array.from(document.images).filter((img) => img.complete && img.naturalWidth > 0).length >= 13,
    null,
    { timeout: 30000 },
  );
}

async function sendTraceTurn(page: any, text: string): Promise<{ traceId: string | null; report: any }> {
  let traceId: string | null = null;
  const onRequest = (request: any) => {
    if (request.url().includes("/intent/route-edit/stream")) {
      traceId = request.headers()["x-ccut-trace-id"] || traceId;
    }
  };
  page.on("request", onRequest);
  const report = page.waitForResponse(
    (response: any) => response.url().includes("/trace/speed") && response.status() === 200,
    { timeout: 120000 },
  );
  await page.locator("textarea").first().fill(text);
  await page.locator("textarea").first().press("Enter");
  const response = await report;
  page.off("request", onRequest);
  return { traceId, report: await response.json().catch(() => null) };
}

function summarizeTrace(row: any) {
  const calls = row?.ollama_calls || [];
  const last = calls[calls.length - 1] || {};
  return {
    trace_id: row?.trace_id,
    route: row?.route_action || row?.response?.action || null,
    edit_executed: ["run_proposal", "revise_current", "retrigger", "intent_clear"].includes(row?.route_action),
    done_reason: last.done_reason ?? null,
    eval_count: last.eval_count ?? null,
    prompt_eval_count: last.prompt_eval_count ?? null,
    last_chunk: last.last_normal_chunk ?? "",
    ollama_len: typeof last.completion_chars === "number" ? last.completion_chars : null,
    db_len: String(row?.db_assistant_text || "").length,
    screen_len: String(row?.screen_text || "").length,
    aborted_by: row?.client_abort ? "frontend" : (last.connection_closed_by || row?.connection_closed_by || null),
    first_visible_ms: row?.t7 && row?.t0 ? row.t7 - row.t0 : null,
    total_ms: row?.t8 && row?.t0 ? row.t8 - row.t0 : null,
    screen_text: row?.screen_text || "",
    db_assistant_text: row?.db_assistant_text || "",
    backend_assistant_text: row?.response?.backend_assistant_text || "",
    calls,
  };
}

const CHAT_12 = [
  "안녕.",
  "오늘은 조금 차분한 기분이야.",
  "나는 커피보다 물을 더 자주 마셔.",
  "방 안은 조용하고 편안해.",
  "요즘 잠을 조금 덜 자서 피곤해.",
  "내가 아까 뭘 더 자주 마신다고 했지?",
  "좋아하는 색은 파란색에 가까워.",
  "한국어 대화가 제일 편하게 느껴져.",
  "내일은 쉬는 시간이 있으면 좋겠어.",
  "오늘 하루는 꽤 길게 느껴졌어.",
  "이야기는 여기까지야.",
  "고마워.",
];

const REGRESSION_6 = [
  ["E1", "생일잔치 장면만 남겨줘"],
  ["E2", "케이크 자르는 부분 잘라줘"],
  ["E3", "cake cutting 장면 편집해보자"],
  ["C1", "오늘 날씨 어때"],
  ["C2", "편집이란 말만 들으면 긴장돼"],
  ["C3", "그건 나중에 하고 다른 얘기하자"],
] as const;

const HOLDOUT_6 = [
  ["H1", "잔치 끝나고 정리하는 데만 골라줘"],
  ["H2", "요즘 영상 편집하는 사람들 많더라"],
  ["H3", "아이가 웃는 순간 위주로 가자"],
  ["H4", "이건 좀 이따가 생각해볼게"],
  ["H5", "촛불 켜는 장면 있어?"],
  ["H6", "편집 얘기는 그만하고 커피 얘기나 하자"],
] as const;

function hasNonKoreanSentence(text: string): boolean {
  return /[A-Za-z一-鿿]/.test(text || "");
}

function thirdPersonSelf(text: string): boolean {
  return /CCUT[는가은이]/.test(text || "");
}

function incomplete(text: string): boolean {
  const t = (text || "").trim();
  return !!t && /[,，、]$|[은는이가을를와과로]$/.test(t);
}

test("SPEED-TRACE-1R records three real Merope chat turns", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("CCUT_TRACE", "1");
  });

  const beforeLines = readTraceLines().length;
  const traceIds: string[] = [];
  page.on("request", (request) => {
    const header = request.headers()["x-ccut-trace-id"];
    if (request.url().includes("/intent/route-edit/stream") && header) {
      traceIds.push(header);
    }
  });

  await page.goto(FRONTEND_URL, { waitUntil: "domcontentloaded" });
  await page.getByText("Merope", { exact: true }).click();
  await page.waitForFunction(
    () => Array.from(document.images).filter((img) => img.complete && img.naturalWidth > 0).length >= 13,
    null,
    { timeout: 30000 },
  );

  const messages = [
    "\uc548\ub155, \uc9c0\uae08\uc740 \ud3b8\uc9d1 \uc694\uccad \uc544\ub2c8\uace0 \uc9e7\uac8c \ub300\ud654\ub9cc \ud558\uc790.",
    "\uc624\ub298 \uc751\ub2f5 \uc18d\ub3c4\ub97c \ud655\uc778\ud558\ub294 \uc9e7\uc740 \ub300\ud654\uc57c.",
    "\uc9c0\uae08 \uae30\ubd84\uc740 \uc5b4\ub54c? \uc9e7\uac8c \ub300\ud654\ud558\uc790.",
  ];

  for (const message of messages) {
    const report = page.waitForResponse(
      (response) => response.url().includes("/trace/speed") && response.status() === 200,
      { timeout: 90000 },
    );
    await page.locator("textarea").first().fill(message);
    await page.locator("textarea").first().press("Enter");
    await report;
  }

  const afterLines = readTraceLines();
  const newLines = afterLines.slice(beforeLines);
  console.log("SPEED_TRACE_JSONL_PATH", TRACE_PATH);
  for (const line of newLines.slice(-3)) console.log("SPEED_TRACE_JSONL_RAW", line);
  console.log("SPEED_TRACE_OUTPUT_DIR", testInfo.outputDir);

  expect(traceIds).toHaveLength(3);
  expect(newLines.length).toBeGreaterThanOrEqual(3);
});

test("CHAT-ROLE-PROBE-1 scenario runner", async ({ page }, testInfo) => {
  test.skip(process.env.CCUT_CHAT_ROLE_PROBE !== "1", "set CCUT_CHAT_ROLE_PROBE=1");
  const scenario = process.env.CCUT_CHAT_PROBE_SCENARIO || "step2";
  const mode = process.env.CCUT_CHAT_PROBE_MODE || "generate";
  const beforeLines = readTraceLines().length;
  await openMerope(page);
  const sent: Array<{ label: string; text: string; traceId: string | null }> = [];
  const cases = scenario === "regression"
    ? REGRESSION_6
    : scenario === "holdout"
      ? HOLDOUT_6
      : CHAT_12.map((text, i) => [`T${i + 1}`, text] as const);
  for (const [label, text] of cases) {
    const result = await sendTraceTurn(page, text);
    sent.push({ label, text, traceId: result.traceId });
  }
  const newRows = parseTraceLines(readTraceLines().slice(beforeLines));
  const byId = new Map(newRows.map((row) => [row.trace_id, row]));
  const summaries = sent.map((item) => ({
    mode,
    scenario,
    case: item.label,
    text: item.text,
    ...summarizeTrace(byId.get(item.traceId)),
  }));
  for (const s of summaries) {
    const rawLine = {
      mode: s.mode,
      scenario: s.scenario,
      case: s.case,
      text: s.text,
      trace_id: s.trace_id,
      route: s.route,
      edit_executed: s.edit_executed,
      done_reason: s.done_reason,
      eval_count: s.eval_count,
      prompt_eval_count: s.prompt_eval_count,
      last_chunk: s.last_chunk,
      db_len: s.db_len,
      screen_len: s.screen_len,
      aborted_by: s.aborted_by,
      first_visible_ms: s.first_visible_ms,
      total_ms: s.total_ms,
    };
    console.log("CHAT_ROLE_PROBE_LINE", JSON.stringify(rawLine));
    console.log("CHAT_ROLE_PROBE_RESPONSE", JSON.stringify({
      mode: s.mode,
      case: s.case,
      screen_text: s.screen_text,
      db_assistant_text: s.db_assistant_text,
      backend_assistant_text: s.backend_assistant_text,
    }));
  }
  if (scenario === "step2") {
    const firstVisible = summaries.map((s) => s.first_visible_ms).filter((v) => typeof v === "number");
    const total = summaries.map((s) => s.total_ms).filter((v) => typeof v === "number");
    const recall = summaries.find((s) => s.case === "T6")?.screen_text || "";
    console.log("CHAT_ROLE_PROBE_AB", JSON.stringify({
      mode,
      turns: summaries.length,
      ko_break: summaries.filter((s) => hasNonKoreanSentence(s.screen_text)).length,
      third_person: summaries.filter((s) => thirdPersonSelf(s.screen_text)).length,
      prefix: summaries.filter((s) => String(s.screen_text || "").includes("CCUT:")).length,
      incomplete: summaries.filter((s) => incomplete(s.screen_text)).length,
      recall,
      recall_pass: /물/.test(recall),
      first_visible_ms: firstVisible,
      total_ms: total,
    }));
  }
  console.log("CHAT_ROLE_PROBE_OUTPUT_DIR", testInfo.outputDir);
  expect(summaries.length).toBe(cases.length);
});
