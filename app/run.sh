#!/usr/bin/env bash
set -euo pipefail

OPTIONS=/data/options.json
DEBUG="$(jq -r '.debug_logging' "$OPTIONS")"
API_PORT="$(jq -r '.api_port' "$OPTIONS")"
API_TOKEN="$(jq -r '.api_token' "$OPTIONS")"

export HOME_ASSISTANT_URL="$(jq -r '.home_assistant_url' "$OPTIONS")"

# Re-verify the per-satellite identity patch at every start. This makes the
# protection independent of Docker layer caching and fails fast if an upstream
# Linux Voice Assistant release changes the device-name implementation.
python3 /usr/local/bin/patch_lva.py

mkdir -p /run/pulse /media/wakemesh /data/runtime
rm -f /data/runtime/*.json
chown pulse:pulse /run/pulse

runuser -u pulse -- env HOME=/var/run/pulse XDG_RUNTIME_DIR=/run/pulse \
  pulseaudio --daemonize=yes --exit-idle-time=-1 --disallow-exit \
  --disable-shm=yes --log-target=stderr --file=/usr/local/bin/pulse.pa
export PULSE_SERVER=unix:/var/run/pulse/native

for _ in $(seq 1 30); do
  pactl info >/dev/null 2>&1 && break
  sleep 0.2
done

PIDS=()

register_worker() {
  local worker_id="$1" worker_type="$2" worker_pid="$3" source_id="$4"
  jq -n --arg id "$worker_id" --arg type "$worker_type" \
    --arg source_id "$source_id" --argjson pid "$worker_pid" \
    '{id:$id,type:$type,source_id:$source_id,pid:$pid}' \
    >"/data/runtime/${worker_id}.json"
}

/usr/local/bin/control_api.py --port "$API_PORT" --token "$API_TOKEN" \
  --version "0.1.8" --runtime-dir /data/runtime &
PIDS+=("$!")
register_worker control_api control_api "$!" system

cleanup() {
  if ((${#PIDS[@]})); then
    kill "${PIDS[@]}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

normalize_id() {
  printf '%s' "$1" | tr '[:upper:]-' '[:lower:]_' | tr -cd 'a-z0-9_'
}

while IFS= read -r source; do
  SOURCE_ID="$(normalize_id "$(jq -r '.id' <<<"$source")")"
  STREAM_URL="$(jq -r '.stream_url' <<<"$source")"
  GAIN_DB="$(jq -r '.audio_gain_db' <<<"$source")"
  CAMERA_SINK="camera_${SOURCE_ID}"
  SOURCE_NAME="Camera Voice ${SOURCE_ID}"

  pactl load-module module-null-sink \
    sink_name="$CAMERA_SINK" format=s16le rate=16000 channels=1 >/dev/null
  env STREAM_URL="$STREAM_URL" GAIN_DB="$GAIN_DB" \
    CAMERA_SINK="$CAMERA_SINK" SOURCE_NAME="$SOURCE_NAME" \
  /usr/local/bin/audio_input.sh &
  PIDS+=("$!")
  register_worker "source_${SOURCE_ID}" audio_input "$!" "$SOURCE_ID"

  while IFS= read -r assistant; do
    if [[ "$(jq -r '.enabled' <<<"$assistant")" != "true" ]]; then
      continue
    fi
    ASSISTANT_ID="$(normalize_id "$(jq -r '.id' <<<"$assistant")")"
    NAME="$(jq -r '.name' <<<"$assistant")"
    PORT="$(jq -r '.port' <<<"$assistant")"
    WAKE_WORD="$(jq -r '.wake_word' <<<"$assistant")"
    STOP_WORD="$(jq -r '.stop_word' <<<"$assistant")"
    HOMEPOD_ENTITY="$(jq -r '.response_player' <<<"$assistant")"
    HOMEPOD_VOLUME="$(jq -r '.response_volume' <<<"$assistant")"
    INITIAL_CHIME="$(jq -r '.initial_chime // ""' <<<"$assistant")"
    STOP_MUSIC_ON_WAKE="$(jq -r '.stop_music_on_wake // false' <<<"$assistant")"
    ROUTER_ID="${SOURCE_ID}_${ASSISTANT_ID}"
    DEVICE_SUFFIX="$(printf '%s' "$ROUTER_ID" | sha256sum | cut -c1-6)"
    VOICE_SINK="voice_${ROUTER_ID}"
    WAKE_EVENT_FILE="/data/runtime/wake_${ROUTER_ID}"
    rm -f "$WAKE_EVENT_FILE"

    pactl load-module module-null-sink \
      sink_name="$VOICE_SINK" format=s16le rate=22050 channels=1 >/dev/null

    env ROUTER_ID="$ROUTER_ID" VOICE_SINK="$VOICE_SINK" \
      HOMEPOD_ENTITY="$HOMEPOD_ENTITY" HOMEPOD_VOLUME="$HOMEPOD_VOLUME" \
      INITIAL_CHIME="$INITIAL_CHIME" STOP_MUSIC_ON_WAKE="$STOP_MUSIC_ON_WAKE" \
      WAKEMESH_WAKE_EVENT_FILE="$WAKE_EVENT_FILE" \
    /usr/local/bin/response_router.py &
    PIDS+=("$!")
    register_worker "router_${ROUTER_ID}" response_router "$!" "$SOURCE_ID"

    ARGS=(
      --name "$NAME"
      --host 0.0.0.0
      --port "$PORT"
      --audio-input-channels 1
      --wake-model "$WAKE_WORD"
      --stop-model "$STOP_WORD"
      --wake-word-dir /opt/lva/wakewords
      --preferences-file "/data/preferences_${ROUTER_ID}.json"
      --download-dir "/data/local_${ROUTER_ID}"
      --disable-peripheral-api
      --listen-during-wake-sound
      --refractory-seconds 5
      --timer-finished-sound /opt/lva/sounds/timer_finished.flac
    )
    if [[ "$DEBUG" == "true" ]]; then
      ARGS+=(--debug)
    fi

    echo "Starting ${NAME}; source=${SOURCE_ID}; ESPHome port=${PORT}; wake=${WAKE_WORD}"
    env PULSE_SOURCE="${CAMERA_SINK}.monitor" PULSE_SINK="$VOICE_SINK" \
      LVA_DEVICE_SUFFIX="$DEVICE_SUFFIX" \
      WAKEMESH_WAKE_EVENT_FILE="$WAKE_EVENT_FILE" \
      python3 -m linux_voice_assistant "${ARGS[@]}" &
    PIDS+=("$!")
    register_worker "satellite_${ROUTER_ID}" assist_satellite "$!" "$SOURCE_ID"
  done < <(jq -c '.assistants[]' <<<"$source")
done < <(jq -c '.sources[]' "$OPTIONS")

if ((${#PIDS[@]} == 0)); then
  echo "No camera voice sources configured" >&2
  exit 1
fi

wait -n "${PIDS[@]}"
echo "A camera voice worker stopped; exiting for watchdog recovery" >&2
exit 1
