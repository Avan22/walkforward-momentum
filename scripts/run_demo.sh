#!/usr/bin/env bash
set -euo pipefail

API="${API:-http://localhost:8000}"

RUN_JSON="$(curl -fsS -X POST "$API/runs" \
  -H 'Content-Type: application/json' \
  -d '{"name":"walkforward-momentum","params":{"tickers":["SPY","QQQ","IWM","EFA","TLT","GLD"],"start":"2015-01-01","end":"2024-12-31","train_days":504,"test_days":63,"rebalance_days":5,"lookbacks":[20,40,60,90,120,180,252],"top_k":1,"fee_bps":5}}')"

RUN_ID="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["run_id"])' "$RUN_JSON")"
echo "RUN_ID=$RUN_ID"

curl -fsS -X POST "$API/runs/$RUN_ID/start" >/dev/null
echo "✅ finished"

echo "--- metrics.csv ---"
cat "runs/$RUN_ID/metrics.csv"
