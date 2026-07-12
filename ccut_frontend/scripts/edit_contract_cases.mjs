/**
 * 공유 케이스 벡터 러너 (TS측) — 출력 형식은 Python 러너와 문자 단위 동일 (동등성 diff 대상).
 * 사용: node edit_contract_cases.mjs <esbuild로 빌드된 editContract.js 경로> <fixtures JSON 경로>
 */
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const [, , builtPath, fixturesPath] = process.argv;
const mod = await import(pathToFileURL(builtPath).href);
const fx = JSON.parse(readFileSync(fixturesPath, "utf-8"));

// Python json.dumps(sort_keys=True, separators=(",", ":")) 동일 규격
function j(obj) {
  if (obj === null) return "null";
  if (Array.isArray(obj)) return `[${obj.map(j).join(",")}]`;
  if (typeof obj === "object") {
    const keys = Object.keys(obj).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${j(obj[k])}`).join(",")}}`;
  }
  if (typeof obj === "boolean") return obj ? "true" : "false";
  return JSON.stringify(obj);
}

// Python repr(float)와 동일한 최단 왕복 표기 (both shortest round-trip)
function pyNum(n) {
  return Number.isInteger(n) ? String(n) : String(n);
}

let fails = 0;

for (const c of fx.to_ms_cases) {
  const got = mod.toMs(c.seconds);
  const ok = got === c.expect_ms;
  if (!ok) fails += 1;
  console.log(`[C12] to_ms(${pyNum(c.seconds)}) = ${got} EXPECT ${c.expect_ms} ${ok ? "PASS" : "FAIL"}`);
}

for (const c of fx.normalize_cases) {
  const cid = c.id;
  const [canonical, receipt] = mod.normalize(c.input);
  const spans = mod.compileSpans(canonical);
  const ids = mod.edIds(c.edit_state_id, spans);
  const out = { canonical, receipt, spans, ed_ids: ids };
  const exp = {
    canonical: c.expect.canonical,
    receipt: c.expect.receipt,
    spans: c.expect.spans,
    ed_ids: c.expect.ed_ids,
  };
  const ok = j(out) === j(exp);
  if (!ok) fails += 1;
  console.log(`[${cid}] INPUT{${j(c.input)}}`);
  console.log(`[${cid}] OUTPUT{${j(out)}}`);
  if (!ok) console.log(`[${cid}] EXPECT{${j(exp)}}`);
  console.log(`[${cid}] ${ok ? "PASS" : "FAIL"}`);
}

for (const c of fx.rematch_cases) {
  const cid = c.id;
  const anchor = [...c.anchor];
  const idx = mod.rematchAnchor(anchor, c.candidates, c.tol_ms);
  const out = { anchor_after: anchor, matched_index: idx };
  const ok = idx === c.expect_index && anchor[0] === c.anchor[0] && anchor[1] === c.anchor[1];
  if (!ok) fails += 1;
  console.log(`[${cid}] INPUT{${j({ anchor: c.anchor, candidates: c.candidates, tol_ms: c.tol_ms })}}`);
  console.log(`[${cid}] OUTPUT{${j(out)}}`);
  console.log(`[${cid}] ${ok ? "PASS" : "FAIL"}`);
}

console.log(`[SUMMARY] fails=${fails}`);
process.exit(fails ? 1 : 0);
