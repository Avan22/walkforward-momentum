# WalkForward Momentum (MVP)

A production-style research MVP for walk-forward momentum strategy evaluation.

## What it does
- Downloads daily ETF data from Stooq (CSV) into `./data/`
- Runs a walk-forward optimization:
  - On each window, selects the best momentum lookback on the training period (Sharpe)
  - Applies the selected lookback out-of-sample on the test period
  - Rolls forward and chains equity across windows
- Persists immutable run artifacts per execution (run folder), including:
  - `params_used.json`
  - `lean_results.json` (Lean-like chart schema for a generic analyzer)
  - `walkforward_windows.csv`
  - `trades.csv`
  - `equity.csv`, `metrics.csv`
  - charts (`charts/equity.png`, `charts/drawdown.png`, `charts/monthly_returns_heatmap.png`)

## Stack
- FastAPI (API + run storage + artifact serving)
- Next.js (UI)
- Pandas/Numpy (research engine + analytics)
- Matplotlib (charts)
- Docker Compose (local reproducibility)

## Quickstart
### 1) Fetch data
```bash
python3 scripts/fetch_stooq.py SPY QQQ IWM EFA TLT GLD

