'use client';

import { useEffect, useState } from "react";

type Run = {
  run_id: string;
  status?: string;
  created_at?: string;
  name?: string;
};

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function fetchText(url: string): Promise<string> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) return "";
  return await r.text();
}

function parseCsvRow(csvText: string): Record<string, string> | null {
  const lines = (csvText || "").trim().split(/\r?\n/);
  if (lines.length < 2) return null;
  const h = lines[0].split(",").map(s => s.trim());
  const v = lines[1].split(",").map(s => s.trim());
  const out: Record<string, string> = {};
  h.forEach((k, i) => out[k] = v[i] ?? "");
  return out;
}

function pct(x?: string) {
  if (!x) return "-";
  const n = Number(x);
  if (!Number.isFinite(n)) return x;
  return (n * 100).toFixed(2) + "%";
}

function num(x?: string) {
  if (!x) return "-";
  const n = Number(x);
  if (!Number.isFinite(n)) return x;
  return n.toFixed(2);
}

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(false);
  const [metricsMap, setMetricsMap] = useState<Record<string, Record<string, string> | null>>({});

  async function refresh() {
    const r = await fetch(`${API}/runs`, { cache: "no-store" });
    const j = await r.json();
    setRuns(j);

    const next: Record<string, Record<string, string> | null> = {};
    for (const run of j) {
      const m = await fetchText(`${API}/runs-static/${run.run_id}/metrics.csv`);
      next[run.run_id] = m ? (parseCsvRow(m) ?? null) : null;
    }
    setMetricsMap(next);
  }

  async function createAndStart() {
    setLoading(true);
    const r = await fetch(`${API}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "walkforward-momentum",
        params: {
          tickers: ["SPY", "QQQ", "IWM", "EFA", "TLT", "GLD"],
          start: "2015-01-01",
          end: "2024-12-31",
          train_days: 504,
          test_days: 63,
          rebalance_days: 5,
          lookbacks: [20, 40, 60, 90, 120, 180, 252],
          top_k: 1,
          fee_bps: 5
        }
      })
    });
    const j = await r.json();
    await fetch(`${API}/runs/${j.run_id}/start`, { method: "POST" });
    await refresh();
    setLoading(false);
  }

  useEffect(() => { refresh(); }, []);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 1100, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>WalkForward Momentum – Runs</h1>
      <div style={{ display: "flex", gap: 10 }}>
        <button onClick={createAndStart} disabled={loading}>
          {loading ? "Running..." : "New run"}
        </button>
        <button onClick={refresh}>Refresh</button>
      </div>

      <div style={{ marginTop: 16, display: "grid", gap: 10 }}>
        {runs.map((x) => {
          const m = metricsMap[x.run_id] || null;
          return (
            <div key={x.run_id} style={{ border: "1px solid #333", borderRadius: 10, padding: 14 }}>
              <div style={{ fontFamily: "monospace", fontSize: 14 }}>{x.run_id}</div>
              <div>Status: <b>{x.status || "unknown"}</b></div>
              {m ? (
                <div style={{ marginTop: 6, display: "flex", gap: 18, flexWrap: "wrap" }}>
                  <div>CAGR: <b>{pct(m["CAGR"])}</b></div>
                  <div>Vol: <b>{pct(m["AnnVol"])}</b></div>
                  <div>Sharpe: <b>{num(m["Sharpe"])}</b></div>
                  <div>MaxDD: <b>{pct(m["MaxDD"])}</b></div>
                </div>
              ) : (
                <div style={{ marginTop: 6, opacity: 0.8 }}>KPIs unavailable (run not succeeded yet)</div>
              )}
              <div style={{ marginTop: 10 }}>
                <a href={`/runs/${x.run_id}`}>Open</a>
              </div>
            </div>
          );
        })}
      </div>
    </main>
  );
}
