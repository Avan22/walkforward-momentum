import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analyze import analyze_run
from engine import WFParams, walkforward_backtest

RUNS_DIR = Path("./runs").resolve()
DATA_DIR = Path("./data").resolve()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/runs-static", StaticFiles(directory=str(RUNS_DIR)), name="runs-static")


class RunCreate(BaseModel):
    name: str = Field(default="walkforward-momentum")
    params: Dict[str, Any] = Field(default_factory=dict)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/runs")
def create_run(body: RunCreate):
    run_id = uuid.uuid4().hex
    rdir = _run_dir(run_id)
    rdir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "run_id": run_id,
        "name": body.name,
        "created_at": _now_iso(),
        "status": "queued",
        "params": body.params,
    }
    _write_json(rdir / "run.json", manifest)
    return {"run_id": run_id}


@app.get("/runs")
def list_runs():
    out = []
    for p in sorted(RUNS_DIR.iterdir(), key=lambda x: x.name, reverse=True):
        if p.is_dir() and (p / "run.json").exists():
            out.append(_read_json(p / "run.json"))
    return out


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    rdir = _run_dir(run_id)
    rj = rdir / "run.json"
    if not rj.exists():
        raise HTTPException(404, "run not found")
    return _read_json(rj)


@app.get("/runs/{run_id}/artifacts")
def artifacts(run_id: str):
    rdir = _run_dir(run_id)
    if not rdir.exists():
        raise HTTPException(404, "run not found")
    files = []
    for p in rdir.rglob("*"):
        if p.is_file():
            files.append(str(p.relative_to(rdir)))
    return {"run_id": run_id, "files": sorted(files)}


@app.post("/runs/{run_id}/start")
def start(run_id: str):
    rdir = _run_dir(run_id)
    rj = rdir / "run.json"
    if not rj.exists():
        raise HTTPException(404, "run not found")

    run = _read_json(rj)
    run["status"] = "running"
    run["started_at"] = _now_iso()
    _write_json(rj, run)

    log_path = rdir / "run.log.txt"

    # Defaults (resume-presentable + sensible)
    p = run.get("params") or {}
    tickers = p.get("tickers", ["SPY", "QQQ", "IWM", "EFA", "TLT", "GLD"])
    start_date = p.get("start", "2015-01-01")
    end_date = p.get("end", "2024-12-31")
    train_days = int(p.get("train_days", 504))      # ~2y
    test_days = int(p.get("test_days", 63))         # ~1q
    rebalance_days = int(p.get("rebalance_days", 5))# weekly
    lookbacks = p.get("lookbacks", [20, 40, 60, 90, 120, 180, 252])
    top_k = int(p.get("top_k", 1))
    fee_bps = float(p.get("fee_bps", 5.0))          # 5 bps per turnover

    params_used = WFParams(
        tickers=[str(x).upper() for x in tickers],
        start=str(start_date),
        end=str(end_date),
        train_days=train_days,
        test_days=test_days,
        rebalance_days=rebalance_days,
        lookbacks=[int(x) for x in lookbacks],
        top_k=top_k,
        fee_bps=fee_bps,
    )

    try:
        with log_path.open("w") as f:
            f.write("Walk-forward momentum runner (real data via Stooq CSV files in ./data)\n")
            f.write(f"params_used={params_used}\n")

        result = walkforward_backtest(DATA_DIR, params_used)

        # artifacts
        _write_json(rdir / "params_used.json", params_used.__dict__)
        (rdir / "lean_results.json").write_text(json.dumps(result["payload"]))
        result["windows"].to_csv(rdir / "walkforward_windows.csv", index=False)
        result["trades"].to_csv(rdir / "trades.csv", index=False)

        # analyzer generates: equity.csv, metrics.csv, charts/*
        analyze_run(rdir)

    except Exception as e:
        run["status"] = "failed"
        run["ended_at"] = _now_iso()
        run["error"] = str(e)
        _write_json(rj, run)
        raise HTTPException(500, f"post-run failed: {e}")

    run["status"] = "succeeded"
    run["ended_at"] = _now_iso()
    _write_json(rj, run)
    return {"run_id": run_id, "status": "succeeded"}
