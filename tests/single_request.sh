#!/bin/bash
URL="http://192.168.122.10:31321/predict"
HOST="image-classifier.default.192.168.122.10.sslip.io"
IMAGE="${1:-/home/core/test_1_ship.png}"

T_SEND=$(date +%s%N)

RESPONSE=$(curl --interface uesimtun0 -v \
  -H "Host: $HOST" \
  "$URL" \
  -F "file=@$IMAGE" 2>&1)

CURL_EXIT=$?
T_COMPLETE=$(date +%s%N)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

echo "t_send     : $(echo "scale=3; $T_SEND / 1000000" | bc) ms"
echo "t_complete : $(echo "scale=3; $T_COMPLETE / 1000000" | bc) ms"

if [ $CURL_EXIT -ne 0 ]; then
  echo "latency    : N/A"
  echo "status     : CURL ERROR (exit code $CURL_EXIT)"
elif [ -z "$BODY" ]; then
  echo "latency    : N/A"
  echo "status     : NO RESPONSE (http $HTTP_CODE)"
else
  LATENCY=$(echo "scale=3; ($T_COMPLETE - $T_SEND) / 1000000" | bc)
  echo "latency    : $LATENCY ms"
  echo "status     : $HTTP_CODE"
  echo "response   : $BODY"
fi
