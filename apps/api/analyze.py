from __future__ import annotations

from pathlib import Path
import json
import pandas as pd
import math

def _safe_div(a: float, b: float) -> float:
    if b is None:
        return float("nan")
    try:
        if abs(b) < 1e-12:
            return float("nan")
    except TypeError:
        return float("nan")
    return a / b

from research_core import Params, run_walkforward

def analyze_run(rdir: Path) -> None:
    run_json = rdir / "run.json"
    params_used = rdir / "params_used.json"
    metrics_csv = rdir / "metrics.csv"
    equity_csv = rdir / "equity.csv"
    windows_csv = rdir / "walkforward_windows.csv"

    run = json.loads(run_json.read_text())
    p = run.get("params", {}) or {}

    params = Params(
        tickers=p.get("tickers", ["SPY","QQQ","IWM","EFA","TLT","GLD"]),
        start=p.get("start", "2015-01-01"),
        end=p.get("end", "2024-12-31"),
        lookbacks=p.get("lookbacks", [20,40,60,90,120,180,252]),
        train_days=int(p.get("train_days", 504)),
        test_days=int(p.get("test_days", 63)),
        rebalance_days=int(p.get("rebalance_days", 5)),
        top_k=int(p.get("top_k", 1)),
        fee_bps=float(p.get("fee_bps", 5)),
    )

    params_used.write_text(json.dumps(params.__dict__, indent=2))

    out = run_walkforward(params)

    # equity artifacts
    eq = out["equity"].rename("Equity").to_frame()
    eq.index.name = "Date"
    eq.to_csv(equity_csv)

    out["windows"].to_csv(windows_csv, index=False)

    # metrics
    m = pd.DataFrame([{
        "CAGR": out["cagr"],
        "AnnVol": out["ann_vol"],
        "Sharpe": out["sharpe"],
        "MaxDD": out["maxdd"],
    }])
    m.to_csv(metrics_csv, index=False)
