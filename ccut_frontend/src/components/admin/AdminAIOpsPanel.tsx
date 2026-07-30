import React, { useEffect, useState } from "react";
import { ExternalLink, KeyRound, PlugZap, Send, Sparkles, Unplug } from "lucide-react";
import { fetcher } from "@/services/api";

// [War Room v1] AI 운영실 — 관리자 API 상태 + 역할별 질의 + 실행 로그.
// API 키는 write-only로 입력하며 서버 응답에는 마스킹 값만 표시한다.

interface AIStatus {
  provider: string | null;
  model: string | null;
  configured: boolean;
  status: string;
  runs_total: number;
  runs_failed: number;
  roles: string[];
}

interface ApiProvider {
  id: string;
  display_name: string;
  configured: boolean;
  masked_key: string;
  model: string | null;
  issue_url: string | null;
  docs_url: string | null;
  // [LAB-52 ③] unverified = 키는 저장됐지만 연결 테스트를 통과한 기록이 없음.
  connection: "unset" | "connected" | "unverified" | "error";
  verified?: boolean;
  last_checked_at: string | null;
  error: string | null;
}

interface AIRun {
  id: number;
  role: string;
  model_key: string;
  status: string;
  input_summary: string | null;
  output_summary: string | null;
  error: string | null;
  duration_ms: number | null;
  created_at: string;
}

interface QueryResult {
  role?: string;
  query?: string;
  result?: string;
  duration_ms?: number;
  error?: string;
  detail?: string;
}

const encryptSecret = async (value: string): Promise<string> => {
  const publicKey = await fetcher("/admin/api-keys/public-key") as {
    public_key_pem: string;
  };
  const encoded = publicKey.public_key_pem
    .replace("-----BEGIN PUBLIC KEY-----", "")
    .replace("-----END PUBLIC KEY-----", "")
    .replace(/\s/g, "");
  const binary = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    "spki",
    binary,
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  );
  const ciphertext = await crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    key,
    new TextEncoder().encode(value),
  );
  return btoa(String.fromCharCode(...new Uint8Array(ciphertext)));
};

export const AdminAIOpsPanel: React.FC = () => {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [runs, setRuns] = useState<AIRun[]>([]);
  const [role, setRole] = useState("ops_brief");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<QueryResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ApiProvider[]>([]);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [keyBusy, setKeyBusy] = useState<string | null>(null);
  const [keyMessage, setKeyMessage] = useState<Record<string, string>>({});
  const [keyEditing, setKeyEditing] = useState<Record<string, boolean>>({});

  const load = () => {
    fetcher("/admin/ai/status").then(setStatus).catch(e => setError(String(e)));
    fetcher("/admin/ai/runs?limit=30").then(r => setRuns(r.runs ?? [])).catch(e => setError(String(e)));
    fetcher("/admin/api-keys").then(r => setProviders(r.providers ?? [])).catch(e => setError(String(e)));
  };
  useEffect(load, []);

  const ask = async () => {
    const q = query.trim();
    if (!q || loading) return;
    setLoading(true);
    try {
      const r = await fetcher("/admin/ai/query", {
        method: "POST", body: JSON.stringify({ role, query: q }),
      }) as QueryResult;
      setResults(prev => [r, ...prev].slice(0, 10));
      setQuery("");
      load();
    } catch (e) {
      setResults(prev => [{ query: q, error: String(e) }, ...prev].slice(0, 10));
    } finally {
      setLoading(false);
    }
  };

  const connectKey = async (provider: ApiProvider) => {
    const value = (keyInputs[provider.id] ?? "").trim();
    if (!value) {
      setKeyMessage(prev => ({ ...prev, [provider.id]: "붙여넣은 키가 없습니다." }));
      return;
    }
    setKeyBusy(`${provider.id}:connect`);
    try {
      const ciphertext = await encryptSecret(value);
      const result = await fetcher(`/admin/api-keys/${provider.id}/connect`, {
        method: "POST",
        body: JSON.stringify({ ciphertext }),
      }) as { error?: string; model?: string };
      if (result.error) throw new Error(result.error);
      setKeyInputs(prev => ({ ...prev, [provider.id]: "" }));
      setKeyEditing(prev => ({ ...prev, [provider.id]: false }));
      setKeyMessage(prev => ({
        ...prev,
        [provider.id]: `연결 및 저장 완료 · ${result.model ?? provider.model ?? ""}`,
      }));
      load();
    } catch (e) {
      setKeyMessage(prev => ({ ...prev, [provider.id]: String(e) }));
    } finally {
      setKeyBusy(null);
    }
  };

  const disconnectKey = async (provider: ApiProvider) => {
    setKeyBusy(`${provider.id}:disconnect`);
    try {
      await fetcher(`/admin/api-keys/${provider.id}`, { method: "DELETE" });
      setKeyInputs(prev => ({ ...prev, [provider.id]: "" }));
      setKeyMessage(prev => ({ ...prev, [provider.id]: "연결 해제됨" }));
      load();
    } catch (e) {
      setKeyMessage(prev => ({ ...prev, [provider.id]: String(e) }));
    } finally {
      setKeyBusy(null);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold text-foreground/90">AI 운영실</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">
          한 번에 모델 1개 · 역할 1개 — 전 실행 admin_ai_runs 기록
        </p>
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <KeyRound size={14} className="text-primary" />
          <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/60">API 키</h2>
        </div>
        <div className="border-y border-border/15 divide-y divide-border/10">
          {providers.map(provider => {
            const isEditing = !provider.configured || keyEditing[provider.id];
            // [LAB-52 ③] 키가 있다 ≠ 연결됐다. 확인 안 된 상태를 연결됨으로 찍지 않는다.
            const badge = provider.connection === "error"
              ? { text: "오류", classes: "text-red-300 bg-red-500/10" }
              : provider.connection === "unverified"
                ? { text: "미확인", classes: "text-amber-300 bg-amber-500/10" }
                : provider.configured
                  ? { text: "연결됨", classes: "text-emerald-300 bg-emerald-500/10" }
                  : { text: "미설정", classes: "text-muted-foreground bg-secondary/30" };
            return (
              <div key={provider.id} className="py-4 space-y-2">
                <div className="flex items-center gap-3">
                  <div className="w-32 flex-shrink-0">
                    <p className="text-sm font-bold text-foreground/90">{provider.display_name}</p>
                    <span className={`inline-flex mt-1 px-1.5 py-0.5 text-[9px] font-bold ${badge.classes}`}>
                      {badge.text}
                    </span>
                  </div>
                  {isEditing && (
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={keyInputs[provider.id] ?? ""}
                      onChange={event => setKeyInputs(prev => ({
                        ...prev,
                        [provider.id]: event.target.value,
                      }))}
                      placeholder="발급받은 API 키 붙여넣기"
                      aria-label={`${provider.display_name} API 키`}
                      className="min-w-0 flex-1 h-9 bg-secondary/25 border border-border/15 px-3 text-xs font-mono outline-none focus:border-primary/40"
                    />
                  )}
                  {provider.issue_url ? (
                    <a
                      href={provider.issue_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="h-9 px-3 inline-flex items-center gap-1.5 border border-border/15 text-[11px] text-foreground/70 hover:bg-secondary/30"
                    >
                      <ExternalLink size={12} />
                      발급 페이지 열기
                    </a>
                  ) : (
                    <span className="text-[10px] text-muted-foreground/50">발급 페이지 미확인</span>
                  )}
                  {isEditing && (
                    <button
                      onClick={() => connectKey(provider)}
                      disabled={keyBusy != null}
                      className="h-9 px-4 inline-flex items-center gap-1.5 bg-primary/15 text-[11px] font-semibold text-primary hover:bg-primary/25 disabled:opacity-50"
                    >
                      <PlugZap size={12} />
                      연결하고 저장
                    </button>
                  )}
                  {provider.configured && !isEditing && (
                    <button
                      onClick={() => setKeyEditing(prev => ({ ...prev, [provider.id]: true }))}
                      disabled={keyBusy != null}
                      className="h-9 px-3 inline-flex items-center border border-border/15 text-[11px] text-foreground/70 hover:bg-secondary/30 disabled:opacity-50"
                    >
                      키 변경
                    </button>
                  )}
                  <button
                    onClick={() => disconnectKey(provider)}
                    disabled={keyBusy != null || !provider.configured}
                    title="연결 해제"
                    className="h-9 w-9 inline-flex items-center justify-center border border-border/15 text-muted-foreground/60 hover:text-red-300 disabled:opacity-30"
                  >
                    <Unplug size={13} />
                  </button>
                </div>
                <div className="pl-32 flex items-center gap-3 text-[10px] text-muted-foreground/50">
                  <span>
                    {provider.connection === "error"
                      ? "키는 저장됐지만 관리자 AI를 사용할 수 없습니다."
                      : provider.connection === "unverified"
                      ? "키는 저장돼 있습니다. 연결을 확인한 기록이 없어 사용 가능 여부는 미확인입니다."
                      : provider.configured
                      ? "연결되어 있습니다. 다시 설정할 필요가 없습니다."
                      : "발급 페이지에서 키를 복사해 붙여넣고 한 번만 누르십시오."}
                  </span>
                  {provider.configured && <span className="font-mono">{provider.masked_key}</span>}
                  {provider.model && <span>{provider.model}</span>}
                  {provider.last_checked_at && (
                    <span>마지막 확인 {new Date(provider.last_checked_at).toLocaleString()}</span>
                  )}
                  {(provider.error || keyMessage[provider.id]) && (
                    <span className={provider.error ? "text-red-400" : "text-foreground/60"}>
                      {provider.error || keyMessage[provider.id]}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="border border-border/15 p-4">
          <p className="text-[10px] font-semibold text-muted-foreground/50 uppercase">관리자 AI</p>
          {status ? (
            <>
              <p className={`text-sm font-bold mt-1 ${status.configured ? "text-emerald-400" : "text-muted-foreground/60"}`}>
                {status.status}
              </p>
              <p className="text-[10px] text-muted-foreground/50 mt-0.5 font-mono">
                {status.provider ?? "—"} · {status.model ?? "—"}
              </p>
              <p className="text-[10px] text-muted-foreground/40 mt-1">
                실행 {status.runs_total}회 · 실패 {status.runs_failed}회
              </p>
            </>
          ) : <p className="text-[11px] text-muted-foreground/50 animate-pulse mt-1">확인 중...</p>}
      </div>

      {/* 역할별 질의 */}
      <div className="flex gap-2">
        <select value={role} onChange={e => setRole(e.target.value)}
          className="h-9 rounded-md bg-secondary/30 border border-border/15 px-2 text-xs text-foreground/90 outline-none">
          {(status?.roles ?? ["ops_brief"]).map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") ask(); }}
          placeholder="운영 질의 입력..."
          className="flex-1 h-9 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40"
        />
        <button onClick={ask} disabled={loading}
          className="flex items-center gap-1.5 px-4 h-9 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors disabled:opacity-50">
          {loading ? <Sparkles size={13} className="animate-pulse" /> : <Send size={13} />}
          {loading ? "질의 중..." : "질의"}
        </button>
      </div>

      {results.map((r, i) => (
        <div key={i} className="rounded-lg border border-border/15 bg-card/20 p-4">
          <p className="text-[11px] font-semibold text-foreground/60">
            [{r.role}] Q. {r.query}
          </p>
          {r.error ? (
            <p className="text-xs text-red-400 mt-1">{r.error}{r.detail ? ` — ${r.detail}` : ""}</p>
          ) : (
            <p className="text-sm text-foreground/90 leading-relaxed mt-1">
              {r.result} <span className="text-[10px] text-muted-foreground/40">({r.duration_ms}ms)</span>
            </p>
          )}
        </div>
      ))}

      {/* 실행 로그 */}
      <div>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">실행 로그</h2>
        {runs.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">아직 기록된 AI 실행이 없습니다.</p>
        ) : (
          <div className="rounded-lg border border-border/15 divide-y divide-border/10">
            {runs.map(r => (
              <div key={r.id} className="px-3 py-2 flex items-center gap-3 text-[11px]">
                <span className={`font-black ${r.status === "ok" ? "text-emerald-400" : "text-red-400"}`}>{r.status}</span>
                <span className="font-mono text-primary/70">{r.role}</span>
                <span className="text-foreground/70 truncate flex-1">{r.input_summary}</span>
                {r.duration_ms != null && <span className="text-muted-foreground/40">{r.duration_ms}ms</span>}
                <span className="text-muted-foreground/40 flex-shrink-0">{new Date(r.created_at).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
