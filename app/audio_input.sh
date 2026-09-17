#!/usr/bin/env bash
set -euo pipefail

while true; do
  echo "Connecting ${SOURCE_NAME} to ${STREAM_URL}"
  ffmpeg -hide_banner -loglevel warning -rtsp_transport tcp \
    -i "$STREAM_URL" -vn -ac 1 -ar 16000 \
    -af "highpass=f=120,lowpass=f=7000,volume=${GAIN_DB}dB,alimiter=limit=0.95" \
    -f pulse -device "$CAMERA_SINK" "$SOURCE_NAME" || true
  echo "${SOURCE_NAME} audio disconnected; reconnecting in 2 seconds"
  sleep 2
done
