#!/usr/bin/env python3
"""Capture the virtual speaker, serve each response, and forward it to HomePod."""

from __future__ import annotations

import json
import os
import subprocess
import struct
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


def pcm_rms(chunk: bytes) -> int:
    """Return RMS for little-endian signed 16-bit PCM without audioop."""
    sample_count = len(chunk) // WIDTH
    if not sample_count:
        return 0
    samples = struct.unpack(f"<{sample_count}h", chunk)
    return int((sum(sample * sample for sample in samples) / sample_count) ** 0.5)


def ha_service(domain: str, service: str, data: dict) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        print("SUPERVISOR_TOKEN is unavailable; response playback skipped", flush=True)
        return
    body = json.dumps(data).encode()
    request = urllib.request.Request(
        f"http://supervisor/core/api/services/{domain}/{service}",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


def route_response(pcm: bytes) -> None:
    stamp = int(time.time() * 1000)
    wav_path = REPLY_DIR / f"wakemesh_{stamp}.wav"
    media_path = REPLY_DIR / f"wakemesh_{stamp}.mp3"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(WIDTH)
        wav.setframerate(RATE)
        wav.writeframes(pcm)

    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(wav_path), "-ar", "44100", "-ac", "2",
            "-codec:a", "libmp3lame", "-b:a", "128k", str(media_path),
        ],
        check=True,
    )
    wav_path.unlink(missing_ok=True)

    # Each response uses a unique URL to avoid aggressive AirPlay caching.
    old_replies = sorted(REPLY_DIR.glob("wakemesh_*.mp3"), key=lambda p: p.stat().st_mtime)
    for old_reply in old_replies[:-5]:
        old_reply.unlink(missing_ok=True)

    ha_service("media_player", "volume_set", {
        "entity_id": ENTITY,
        "volume_level": VOLUME,
    })
    ha_service("media_player", "play_media", {
        "entity_id": ENTITY,
        "media_content_id": (
            f"media-source://media_source/local/wakemesh/{ROUTER_ID}/{media_path.name}"
        ),
        "media_content_type": "audio/mpeg",
        "announce": True,
    })
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


capture()
