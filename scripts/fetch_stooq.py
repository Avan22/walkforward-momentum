import sys
import ssl
import urllib.request
from pathlib import Path

import certifi

BASE = "https://stooq.com/q/d/l/?s={sym}&i=d"

def norm_symbol(sym: str) -> str:
    s = sym.strip().lower()
    # If user provides already like spy.us, keep it.
    if "." in s:
        return s
    # Default to US listing for common tickers
    return f"{s}.us"

def fetch(sym: str, out_dir: Path) -> Path:
    s = norm_symbol(sym)
    url = BASE.format(sym=s)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{sym.upper()}.csv"

    ctx = ssl.create_default_context(cafile=certifi.where())
    req = urllib.request.Request(url, headers={"User-Agent": "walkforward-momentum/1.0"})
    with urllib.request.urlopen(req, context=ctx) as r:
        data = r.read()

    header = b"Date,Open,High,Low,Close,Volume"
    if header not in data[:200]:
        # save debug payload so you can inspect what stooq returned
        dbg = out_dir / f"{sym.upper()}_DEBUG.html"
        dbg.write_bytes(data)
        raise RuntimeError(f"Bad response for {sym} (requested {s}). Saved debug: {dbg}")

    out.write_bytes(data)
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/fetch_stooq.py SPY QQQ IWM EFA TLT GLD")
        raise SystemExit(2)

    out_dir = Path("data")
    for sym in sys.argv[1:]:
        p = fetch(sym, out_dir)
        print(f"saved {p}")
