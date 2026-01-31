from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import numpy as np

DATA_DIR = Path("/app/data")

@dataclass
class Params:
    tickers: list[str]
    start: str
    end: str
    lookbacks: list[int]
    train_days: int
    test_days: int
    rebalance_days: int
    top_k: int
    fee_bps: float

def load_prices(tickers: list[str]) -> pd.DataFrame:
    dfs = []
    for t in tickers:
        p = DATA_DIR / f"{t.upper()}.csv"
        if not p.exists():
            raise FileNotFoundError(f"Missing data file: {p}. Run scripts/fetch_stooq.")
        df = pd.read_csv(p)
        if "Date" not in df.columns or "Close" not in df.columns:
            raise ValueError(f"Bad CSV schema in {p}. Need Date and Close.")
        df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce")
        df = df.dropna(subset=["Date"]).sort_values("Date")
        df = df[["Date", "Close"]].rename(columns={"Close": t.upper()}).set_index("Date")
        dfs.append(df)
    px = pd.concat(dfs, axis=1).dropna(how="any")
    return px

def daily_returns(px: pd.DataFrame) -> pd.DataFrame:
    rets = px.pct_change().dropna(how="any")
    return rets

def momentum_scores(px: pd.DataFrame, lookback: int) -> pd.DataFrame:
    # simple total return over lookback
    return px.pct_change(lookback)

def sharpe(x: pd.Series) -> float:
    x = x.dropna()
    if len(x) < 10:
        return float("-inf")
    sd = x.std()
    if sd == 0 or np.isnan(sd):
        return float("-inf")
    return (x.mean() / sd) * np.sqrt(252)

def run_walkforward(params: Params) -> dict:
    px = load_prices(params.tickers)
    px = px.loc[pd.to_datetime(params.start, utc=True): pd.to_datetime(params.end, utc=True)]
    if len(px) < params.train_days + params.test_days + 5:
        raise ValueError("Not enough price history for given start/end/train/test.")

    rets = daily_returns(px)

    dates = rets.index
    eq = pd.Series(index=dates, dtype=float)
    eq.iloc[0] = 1.0

    rows = []
    t0 = 0
    fee = params.fee_bps / 10000.0

    while True:
        train_start = t0
        train_end = train_start + params.train_days
        test_end = train_end + params.test_days
        if test_end >= len(dates):
            break

        train_slice = slice(train_start, train_end)
        test_slice = slice(train_end, test_end)

        # choose best lookback on training Sharpe of top-k momentum portfolio
        best_lb = None
        best_sh = float("-inf")

        for lb in params.lookbacks:
            scores = momentum_scores(px, lb).loc[dates[train_slice]]
            # rebalance every N days: forward-fill chosen basket weights between rebals
            w = pd.DataFrame(0.0, index=scores.index, columns=scores.columns)
            for i, dt in enumerate(scores.index):
                if i % params.rebalance_days == 0:
                    top = scores.loc[dt].nlargest(params.top_k).index.tolist()
                    w.loc[dt, top] = 1.0 / params.top_k
            w = w.replace(0, np.nan).ffill().fillna(0.0)

            rp = (w * rets.loc[w.index]).sum(axis=1) - fee
            sh = sharpe(rp)
            if sh > best_sh:
                best_sh, best_lb = sh, lb

        # apply best lookback on test
        scores = momentum_scores(px, best_lb).loc[dates[test_slice]]
        w = pd.DataFrame(0.0, index=scores.index, columns=scores.columns)
        for i, dt in enumerate(scores.index):
            if i % params.rebalance_days == 0:
                top = scores.loc[dt].nlargest(params.top_k).index.tolist()
                w.loc[dt, top] = 1.0 / params.top_k
        w = w.replace(0, np.nan).ffill().fillna(0.0)

        rp = (w * rets.loc[w.index]).sum(axis=1) - fee

        # chain equity
        prev_eq = float(eq.loc[w.index[0] - pd.Timedelta(days=1)] if (w.index[0] - pd.Timedelta(days=1)) in eq.index else eq.iloc[train_end-1])
        # safer: use last known equity before test starts
        prev_eq = float(eq.ffill().iloc[train_end-1])

        test_eq = (1.0 + rp).cumprod() * prev_eq
        eq.loc[test_eq.index] = test_eq

        rows.append({
            "train_start": str(dates[train_start].date()),
            "train_end": str(dates[train_end-1].date()),
            "test_start": str(dates[train_end].date()),
            "test_end": str(dates[test_end-1].date()),
            "best_lookback": int(best_lb),
            "train_sharpe": float(best_sh),
        })

        t0 = test_end  # roll forward by test window

    eq = eq.dropna()
    r = eq.pct_change().dropna()

    # metrics
    eq2 = eq.ffill().dropna()
    if len(eq2) < 2:
        cagr = float("nan")
        ann_vol = float("nan")
        sh = float("nan")
        maxdd = float("nan")
    else:
        r = eq2.pct_change().dropna()
        years = len(r) / 252.0
        if years > 0 and float(eq2.iloc[0]) != 0.0:
            cagr = (float(eq2.iloc[-1]) / float(eq2.iloc[0])) ** (1.0 / years) - 1.0
        else:
            cagr = float("nan")
        ann_vol = float(r.std() * (252.0 ** 0.5))
        if float(r.std()) != 0.0:
            sh = float((r.mean() / r.std()) * (252.0 ** 0.5))
        else:
            sh = float("nan")
        peak = eq2.cummax()
        dd = (eq2 / peak) - 1.0
        maxdd = float(abs(dd.min()))
    return {
        "equity": eq,
        "returns": r,
        "maxdd": maxdd,
        "cagr": float(cagr),
        "ann_vol": float(ann_vol),
        "sharpe": float(sh),
        "windows": pd.DataFrame(rows),
    }
