#!/usr/bin/env python3
"""Capture the virtual speaker, serve each response, and forward it to HomePod."""

from __future__ import annotations

import json
import os
import subprocess
import struct
import threading
import time
import urllib.request
import wave
from pathlib import Path

RATE = 22050
CHANNELS = 1
WIDTH = 2
CHUNK_FRAMES = 1024
START_RMS = 250
END_SILENCE_SECONDS = 0.8
MIN_AUDIO_SECONDS = 0.35

ROUTER_ID = os.environ["ROUTER_ID"]
VOICE_SINK = os.environ["VOICE_SINK"]
REPLY_DIR = Path("/media/wakemesh") / ROUTER_ID
REPLY_DIR.mkdir(parents=True, exist_ok=True)
HA_URL = os.environ["HOME_ASSISTANT_URL"].rstrip("/")
ENTITY = os.environ["HOMEPOD_ENTITY"]
VOLUME = float(os.environ.get("HOMEPOD_VOLUME", "0.3"))
INITIAL_CHIME = os.environ.get("INITIAL_CHIME", "").strip()
STOP_MUSIC_ON_WAKE = os.environ.get("STOP_MUSIC_ON_WAKE", "false").lower() == "true"
WAKE_EVENT_FILE = Path(os.environ.get("WAKEMESH_WAKE_EVENT_FILE", ""))

_playback_lock = threading.Lock()
_preempted_playback = False
_preempted_volume: float | None = None
_preempted_at = 0.0


def pcm_rms(chunk: bytes) -> int:
    """Return RMS for little-endian signed 16-bit PCM without audioop."""
    sample_count = len(chunk) // WIDTH
    if not sample_count:
        return 0
    samples = struct.unpack(f"<{sample_count}h", chunk)
    return int((sum(sample * sample for sample in samples) / sample_count) ** 0.5)


def ha_request(path: str, *, data: dict | None = None) -> object | None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        print("SUPERVISOR_TOKEN is unavailable; Home Assistant request skipped", flush=True)
        return None
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(
        f"http://supervisor/core/api/{path.lstrip('/')}",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read()
        return json.loads(payload) if payload else None


def ha_service(domain: str, service: str, data: dict) -> object | None:
    return ha_request(f"services/{domain}/{service}", data=data)


def destination_state() -> dict:
    state = ha_request(f"states/{ENTITY}")
    return state if isinstance(state, dict) else {}


def is_destination_playing() -> bool:
    return destination_state().get("state") == "playing"


def handle_wake_event() -> None:
    """Pause active destination audio as soon as the wake word is accepted."""
    global _preempted_at, _preempted_playback, _preempted_volume
    if not STOP_MUSIC_ON_WAKE:
        return
    try:
        state = destination_state()
        was_playing = state.get("state") == "playing"
        volume = state.get("attributes", {}).get("volume_level")
        with _playback_lock:
            _preempted_playback = was_playing
            _preempted_volume = float(volume) if volume is not None else None
            _preempted_at = time.monotonic() if was_playing else 0.0
        if was_playing:
            ha_service("media_player", "media_pause", {"entity_id": ENTITY})
            print(f"Paused active audio on wake for {ENTITY}", flush=True)
    except Exception as err:
        print(f"Wake preemption failed: {err}", flush=True)


def watch_wake_events() -> None:
    """Watch the marker touched by the satellite's wake-word callback."""
    global _preempted_at, _preempted_playback, _preempted_volume
    last_mtime = WAKE_EVENT_FILE.stat().st_mtime_ns if WAKE_EVENT_FILE.exists() else 0
    while True:
        should_restore = False
        restore_volume = None
        try:
            if WAKE_EVENT_FILE.exists():
                mtime = WAKE_EVENT_FILE.stat().st_mtime_ns
                if mtime != last_mtime:
                    last_mtime = mtime
                    handle_wake_event()
            with _playback_lock:
                if _preempted_playback and time.monotonic() - _preempted_at > 60:
                    should_restore = True
                    restore_volume = _preempted_volume
                    _preempted_playback = False
                    _preempted_volume = None
                    _preempted_at = 0.0
            if should_restore:
                if restore_volume is not None:
                    ha_service("media_player", "volume_set", {
                        "entity_id": ENTITY, "volume_level": restore_volume,
                    })
                ha_service("media_player", "media_play", {"entity_id": ENTITY})
                print(f"Restored audio after wake timeout for {ENTITY}", flush=True)
        except OSError as err:
            print(f"Wake event watcher failed: {err}", flush=True)
        time.sleep(0.05)


def encode_response(wav_path: Path, media_path: Path) -> None:
    """Encode speech, optionally prepending one configured local/remote chime."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if INITIAL_CHIME:
        if not INITIAL_CHIME.startswith(("/media/", "http://", "https://")):
            raise ValueError("initial_chime must use /media/, http://, or https://")
        command.extend([
            "-i", INITIAL_CHIME, "-i", str(wav_path),
            "-filter_complex",
            (
                "[0:a]aresample=44100,aformat=sample_fmts=fltp:"
                "channel_layouts=stereo[chime];"
                "[1:a]aresample=44100,aformat=sample_fmts=fltp:"
                "channel_layouts=stereo[speech];"
                "[chime][speech]concat=n=2:v=0:a=1[out]"
            ),
            "-map", "[out]",
        ])
    else:
        command.extend(["-i", str(wav_path), "-ar", "44100", "-ac", "2"])
    command.extend(["-codec:a", "libmp3lame", "-b:a", "128k", str(media_path)])
    subprocess.run(command, check=True)


def route_response(pcm: bytes) -> None:
    global _preempted_at, _preempted_playback, _preempted_volume
    stamp = int(time.time() * 1000)
    wav_path = REPLY_DIR / f"wakemesh_{stamp}.wav"
    media_path = REPLY_DIR / f"wakemesh_{stamp}.mp3"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(WIDTH)
        wav.setframerate(RATE)
        wav.writeframes(pcm)

    encode_response(wav_path, media_path)
    wav_path.unlink(missing_ok=True)

    # Each response uses a unique URL to avoid aggressive AirPlay caching.
    old_replies = sorted(REPLY_DIR.glob("wakemesh_*.mp3"), key=lambda p: p.stat().st_mtime)
    for old_reply in old_replies[:-5]:
        old_reply.unlink(missing_ok=True)

    ha_service("media_player", "volume_set", {
        "entity_id": ENTITY,
        "volume_level": VOLUME,
    })
    with _playback_lock:
        was_preempted = _preempted_playback
        preempted_volume = _preempted_volume
        _preempted_playback = False
        _preempted_volume = None
        _preempted_at = 0.0
    ha_service("media_player", "play_media", {
        "entity_id": ENTITY,
        "media_content_id": (
            f"media-source://media_source/local/wakemesh/{ROUTER_ID}/{media_path.name}"
        ),
        "media_content_type": "audio/mpeg",
        "announce": True,
        "extra": {
            "wakemesh_preempted_playback": was_preempted,
            "wakemesh_original_volume": preempted_volume,
        },
    })
    # The WakeMesh RAOP player consumes the hint above and resumes playback.
    # This fallback also supports ordinary Home Assistant media players.
    if was_preempted and not is_destination_playing():
        if preempted_volume is not None:
            ha_service("media_player", "volume_set", {
                "entity_id": ENTITY, "volume_level": preempted_volume,
            })
        ha_service("media_player", "media_play", {"entity_id": ENTITY})
    print(f"Forwarded {len(pcm) / (RATE * WIDTH):.1f}s of audio to {ENTITY}", flush=True)


def capture() -> None:
    command = [
        "parec", f"--device={VOICE_SINK}.monitor", "--format=s16le",
        f"--rate={RATE}", f"--channels={CHANNELS}",
    ]
    while True:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE)
        assert proc.stdout is not None
        active = False
        silence_started = 0.0
        chunks: list[bytes] = []
        try:
            while True:
                chunk = proc.stdout.read(CHUNK_FRAMES * WIDTH)
                if not chunk:
                    break
                rms = pcm_rms(chunk)
                now = time.monotonic()
                if rms >= START_RMS:
                    if not active:
                        active = True
                        chunks = []
                    silence_started = 0.0
                elif active and silence_started == 0.0:
                    silence_started = now

                if active:
                    chunks.append(chunk)
                    if silence_started and now - silence_started >= END_SILENCE_SECONDS:
                        pcm = b"".join(chunks)
                        active = False
                        chunks = []
                        silence_started = 0.0
                        if len(pcm) >= RATE * WIDTH * MIN_AUDIO_SECONDS:
                            try:
                                route_response(pcm)
                            except Exception as err:
                                print(f"Response routing failed: {err}", flush=True)
        finally:
            proc.kill()
            proc.wait()
            time.sleep(1)


if STOP_MUSIC_ON_WAKE and str(WAKE_EVENT_FILE):
    threading.Thread(target=watch_wake_events, daemon=True).start()

capture()
