'use client';

import { useEffect, useState } from "react";

type Run = {
  run_id: string;
  status?: string;
  created_at?: string;
  started_at?: string;
  ended_at?: string;
  name?: string;
  params?: Record<string, any>;
  error?: string;
};

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function fetchText(url: string): Promise<string> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) return "";
  return await r.text();
}

async function fetchJSON<T>(url: string): Promise<T | null> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) return null;
  return (await r.json()) as T;
}

function parseCsvToObject(csvText: string): Record<string, string> | null {
  if (!csvText) return null;
  const lines = csvText.trim().split(/\r?\n/);
  if (lines.length < 2) return null;
  const headers = lines[0].split(",").map(s => s.trim());
  const values = lines[1].split(",").map(s => s.trim());
  const out: Record<string, string> = {};
  headers.forEach((h, i) => (out[h] = values[i] ?? ""));
  return out;
}

function fmtPct(x: string | undefined) {
  if (!x) return "-";
  const v = Number(x);
  if (!Number.isFinite(v)) return x;
  return `${(v * 100).toFixed(2)}%`;
}

function fmtNum(x: string | undefined) {
  if (!x) return "-";
  const v = Number(x);
  if (!Number.isFinite(v)) return x;
  return v.toFixed(3);
}

export default function RunDetail({ params }: { params: { id: string } }) {
  const [run, setRun] = useState<Run | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<Record<string, string> | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const baseStatic = `${API}/runs-static/${params.id}`;

  async function refresh() {
    setRefreshing(true);

    const runObj = await fetchJSON<Run>(`${API}/runs/${params.id}`);
    if (runObj) setRun(runObj);

    const arts = await fetchJSON<{ run_id: string; files: string[] }>(
      `${API}/runs/${params.id}/artifacts`
    );
    if (arts?.files) setFiles(arts.files);

    const metricsCsv = await fetchText(`${baseStatic}/metrics.csv`);
    setMetrics(parseCsvToObject(metricsCsv));

    setRefreshing(false);
  }

  async function startRun() {
    setRefreshing(true);
    await fetch(`${API}/runs/${params.id}/start`, { method: "POST" });
    await refresh();
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 980 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>Run {params.id}</h1>
        <button onClick={refresh} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
        <button onClick={startRun} disabled={refreshing}>
          Start / Re-run
        </button>
      </div>

      <div style={{ marginTop: 12 }}>
        <div style={{ padding: 12, background: "#f6f6f6", borderRadius: 8 }}>
          <div><b>Status:</b> {run?.status ?? "unknown"}</div>
          {run?.error ? <div><b>Error:</b> {run.error}</div> : null}
          <div><b>Created:</b> {run?.created_at ?? "-"}</div>
          <div><b>Started:</b> {run?.started_at ?? "-"}</div>
          <div><b>Ended:</b> {run?.ended_at ?? "-"}</div>
        </div>
      </div>

      <h2 style={{ marginTop: 20 }}>KPIs (from metrics.csv)</h2>
      <div style={{ padding: 12, background: "#f6f6f6", borderRadius: 8 }}>
        {metrics ? (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <tbody>
              <tr>
                <td style={{ padding: 6 }}><b>CAGR</b></td>
                <td style={{ padding: 6 }}>{fmtPct(metrics["CAGR"])}</td>
              </tr>
              <tr>
                <td style={{ padding: 6 }}><b>Annual Volatility</b></td>
                <td style={{ padding: 6 }}>{fmtPct(metrics["AnnVol"])}</td>
              </tr>
              <tr>
                <td style={{ padding: 6 }}><b>Sharpe</b></td>
                <td style={{ padding: 6 }}>{fmtNum(metrics["Sharpe"])}</td>
              </tr>
              <tr>
                <td style={{ padding: 6 }}><b>Sortino</b></td>
                <td style={{ padding: 6 }}>{fmtNum(metrics["Sortino"])}</td>
              </tr>
              <tr>
                <td style={{ padding: 6 }}><b>Max Drawdown</b></td>
                <td style={{ padding: 6 }}>{fmtPct(metrics["MaxDD"])}</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <div>metrics.csv not found yet (run may not have succeeded).</div>
        )}
      </div>

      <h2 style={{ marginTop: 20 }}>Charts</h2>
      <div style={{ display: "grid", gap: 12 }}>
        <img
          src={`${baseStatic}/charts/equity.png`}
          alt="equity"
          style={{ width: "100%", maxWidth: 900, border: "1px solid #ddd", borderRadius: 8 }}
        />
        <img
          src={`${baseStatic}/charts/drawdown.png`}
          alt="drawdown"
          style={{ width: "100%", maxWidth: 900, border: "1px solid #ddd", borderRadius: 8 }}
        />
        <img
          src={`${baseStatic}/charts/monthly_returns_heatmap.png`}
          alt="monthly heatmap"
          style={{ width: "100%", maxWidth: 900, border: "1px solid #ddd", borderRadius: 8 }}
        />
      </div>

      <h2 style={{ marginTop: 20 }}>Artifacts</h2>
      <div style={{ padding: 12, background: "#f6f6f6", borderRadius: 8 }}>
        {files.length ? (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {files.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        ) : (
          <div>No artifacts yet.</div>
        )}
      </div>

      <h2 style={{ marginTop: 20 }}>Raw run.json</h2>
      <pre style={{ background: "#f6f6f6", padding: 12, borderRadius: 8, overflowX: "auto" }}>
        {run ? JSON.stringify(run, null, 2) : "Loading..."}
      </pre>
    </main>
  );
}
