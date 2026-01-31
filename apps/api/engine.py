import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd

@dataclass(frozen=True)
class WFParams:
    tickers: List[str]
    start: str
    end: str
    train_days: int
    test_days: int
    rebalance_days: int
    lookbacks: List[int]
    top_k: int
    fee_bps: float

def _load_prices(data_dir: Path, tickers: List[str]) -> pd.DataFrame:
    frames = []
    for t in tickers:
        p = data_dir / f"{t.upper()}.csv"
        if not p.exists():
            raise FileNotFoundError(f"Missing data file: {p}. Run scripts/fetch_stooq.py {t.upper()}")
        df = pd.read_csv(p)
        if "Date" not in df.columns or "Close" not in df.columns:
            raise RuntimeError(f"Bad CSV format for {t}: {p}")
        df["Date"] = pd.to_datetime(df["Date"])
        df = df[["Date", "Close"]].rename(columns={"Close": t.upper()})
        frames.append(df.set_index("Date"))
    px = pd.concat(frames, axis=1).sort_index()
    px = px.ffill().dropna()
    return px

def _momentum_scores(px: pd.DataFrame, lookback: int) -> pd.DataFrame:
    return px.pct_change(lookback)

def _rebalance_dates(idx: pd.DatetimeIndex, every: int) -> pd.DatetimeIndex:
    if len(idx) == 0:
        return idx
    # take every Nth day in the index, starting at first available day
    return idx[::every]

def _simulate_period(px: pd.DataFrame, start_i: int, end_i: int, lookback: int, top_k: int,
                     rebalance_days: int, fee_bps: float) -> Tuple[pd.Series, pd.DataFrame]:
    """
    Simulate from idx[start_i] .. idx[end_i] inclusive.
    Strategy: at each rebalance date, compute momentum over lookback, pick top_k, equal-weight.
    Returns: equity series (daily), and trades log.
    """
    idx = px.index
    window_px = px.iloc[start_i:end_i+1].copy()
    dates = window_px.index

    # daily returns of each asset
    rets = window_px.pct_change().fillna(0.0)

    rebal_dates = _rebalance_dates(dates, rebalance_days)
    weights = pd.Series(0.0, index=px.columns)
    equity = []
    trades = []

    eq = 1.0
    last_sel = []

    for d in dates:
        if d in rebal_dates:
            # compute momentum using data up to d (inclusive)
            # require lookback history
            loc = window_px.index.get_loc(d)
            if loc >= lookback:
                m = (window_px.iloc[loc] / window_px.iloc[loc - lookback]) - 1.0
                sel = list(m.sort_values(ascending=False).head(top_k).index)
            else:
                sel = []  # not enough history yet

            new_w = pd.Series(0.0, index=px.columns)
            if sel:
                new_w.loc[sel] = 1.0 / len(sel)

            # transaction cost on turnover
            turnover = float((new_w - weights).abs().sum())
            cost = turnover * (fee_bps / 10000.0)

            if sel != last_sel:
                trades.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "lookback": lookback,
                    "selected": ",".join(sel),
                    "turnover": turnover,
                    "cost": cost
                })
                last_sel = sel

            weights = new_w
            eq *= (1.0 - cost)

        # apply daily portfolio return
        r = float((weights * rets.loc[d]).sum())
        eq *= (1.0 + r)
        equity.append(eq)

    eqs = pd.Series(equity, index=dates, name="equity")
    trades_df = pd.DataFrame(trades)
    return eqs, trades_df

def _sharpe(daily_rets: pd.Series) -> float:
    if daily_rets.std() == 0:
        return -1e9
    return float((daily_rets.mean() / daily_rets.std()) * np.sqrt(252))

def walkforward_backtest(data_dir: Path, params: WFParams) -> Dict[str, Any]:
    px = _load_prices(data_dir, params.tickers)
    px = px.loc[(px.index >= pd.to_datetime(params.start)) & (px.index <= pd.to_datetime(params.end))]
    if len(px) < (params.train_days + params.test_days + max(params.lookbacks) + 5):
        raise RuntimeError("Not enough data for the chosen start/end/train/test/lookbacks")

    idx = px.index
    windows = []
    all_equity = pd.Series(dtype=float)
    all_trades = []

    start_i = 0
    run_no = 0

    # roll by test_days
    while True:
        train_start = start_i
        train_end = train_start + params.train_days - 1
        test_start = train_end + 1
        test_end = test_start + params.test_days - 1

        if test_end >= len(idx):
            break

        # choose best lookback on TRAIN by sharpe
        best_lb = None
        best_score = -1e18

        for lb in params.lookbacks:
            # simulate train with lb
            eq_train, _ = _simulate_period(px, train_start, train_end, lb, params.top_k, params.rebalance_days, params.fee_bps)
            train_rets = eq_train.pct_change().dropna()
            score = _sharpe(train_rets)
            if score > best_score:
                best_score = score
                best_lb = lb

        # run OOS test with chosen lookback
        eq_test, trades_df = _simulate_period(px, test_start, test_end, int(best_lb), params.top_k, params.rebalance_days, params.fee_bps)

        # chain equity continuously
        if all_equity.empty:
            all_equity = eq_test.copy()
        else:
            scale = all_equity.iloc[-1]
            all_equity = pd.concat([all_equity, eq_test * scale])

        if not trades_df.empty:
            trades_df["window"] = run_no
            all_trades.append(trades_df)

        windows.append({
            "window": run_no,
            "train_start": idx[train_start].strftime("%Y-%m-%d"),
            "train_end": idx[train_end].strftime("%Y-%m-%d"),
            "test_start": idx[test_start].strftime("%Y-%m-%d"),
            "test_end": idx[test_end].strftime("%Y-%m-%d"),
            "best_lookback": int(best_lb),
            "train_sharpe": float(best_score),
        })

        run_no += 1
        start_i = test_start  # roll forward by test period

    if all_equity.empty:
        raise RuntimeError("No walk-forward windows produced. Check date range.")

    # Build a Lean-like results payload used by your analyzer
    # Analyzer expects: Charts -> Strategy Equity -> Series -> Equity -> Values[{x,y}]
    values = [{"x": int(pd.Timestamp(d).timestamp()), "y": float(v)} for d, v in all_equity.items()]
    payload = {
        "Charts": {
            "Strategy Equity": {
                "Series": {
                    "Equity": {"Values": values}
                }
            }
        },
        "WalkForward": {
            "windows": windows
        }
    }

    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame(columns=["date","lookback","selected","turnover","cost","window"])
    return {
        "payload": payload,
        "equity": all_equity,
        "windows": pd.DataFrame(windows),
        "trades": trades,
    }
