import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const FRONTEND_URL = process.env.CCUT_FRONTEND_URL || "http://127.0.0.1:5173/";
const TRACE_PATH = path.resolve(__dirname, "../../logs/trace/speed_trace.jsonl");

function readTraceLines(): string[] {
  if (!fs.existsSync(TRACE_PATH)) return [];
  return fs.readFileSync(TRACE_PATH, "utf8").split(/\r?\n/).filter(Boolean);
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
