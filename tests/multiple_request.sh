#!/bin/bash
URL="http://192.168.122.10:31321/predict"
HOST="image-classifier.default.192.168.122.10.sslip.io"
IMAGE="${1:-/home/core/test_1_ship.png}"
N="${2:-5}"   # số request đồng thời

send_request() {
  local ID=$1
  local T0=$(date +%s%N)

  RESPONSE=$(curl -s -w "\n%{http_code}" --interface uesimtun0 \
    -H "Host: $HOST" "$URL" \
    -F "file=@$IMAGE" 2>&1)

  local EXIT=$?
  local T1=$(date +%s%N)
  local HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  local BODY=$(echo "$RESPONSE" | head -n -1)

  if [ $EXIT -ne 0 ]; then
    echo "[req $ID] CURL ERROR (exit $EXIT)"
  else
    local LAT=$(echo "scale=3; ($T1 - $T0) / 1000000" | bc)
    echo "[req $ID] latency=$LAT ms  status=$HTTP_CODE  body=$BODY"
  fi
}

T_BATCH=$(date +%s%N)
echo "Sending $N concurrent requests..."

for i in $(seq 1 $N); do
  send_request $i &
done

wait

TOTAL=$(echo "scale=3; ($(date +%s%N) - $T_BATCH) / 1000000" | bc)
echo "────────────────────────────"
echo "wall-clock: $TOTAL ms  ($N requests)"
