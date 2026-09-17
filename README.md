# WakeMesh

**Turn network audio sources into local Home Assistant voice satellites—and deliver reliable announcements to HomePods.**

[![Tests](https://github.com/ccabman/wakemesh/actions/workflows/tests.yml/badge.svg)](https://github.com/ccabman/wakemesh/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/ccabman/wakemesh?include_prereleases&label=release)](https://github.com/ccabman/wakemesh/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-local%20voice-41BDF5.svg)](https://www.home-assistant.io/voice_control/)

WakeMesh is an experimental audio processor and router for Home Assistant. It
connects RTSP or go2rtc audio sources—such as cameras and doorbells—to Home
Assistant Assist, then routes spoken responses to a selected media player.

> [!WARNING]
> WakeMesh is alpha software. It is intended for technically experienced Home
> Assistant users and should not be relied on for alarms, emergencies, or other
> safety-critical functions.

## Why WakeMesh?

Many homes already contain useful microphones in cameras, doorbells, and other
network devices. WakeMesh experiments with treating those sources as a mesh of
logical voice satellites without requiring a speaker beside every microphone.

- Consume audio from RTSP and go2rtc streams
- Run multiple logical Assist satellites from one engine
- Configure independent wake words and Assist personalities
- Send responses to Home Assistant media players
- Keep speech processing and routing on the local network
- Expose health and worker diagnostics through a versioned local API
- Discover HomePods without manually entering MAC addresses
- Present true HomePod stereo pairs as one synchronized destination
- Raise announcement volume by configurable percentage points
- Restore volume and resume interrupted playback after announcements

## How it works

```text
Camera / doorbell audio
          |
          v
   RTSP or go2rtc
          |
          v
  WakeMesh Engine  ---> Home Assistant Assist pipeline
          |                         |
          +<---- synthesized reply--+
          |
          v
 HomePod / media player
```

The repository contains two components:

- `app/` — the Home Assistant add-on and long-running audio data plane.
- `custom_components/wakemesh/` — the Home Assistant integration and control
  plane. It provides engine status plus native media-player destinations for
  reliable HomePod announcements.

See [Architecture](docs/architecture.md) for the design and roadmap.

## Current status

WakeMesh is at **0.2.x alpha**. The engine can run multiple configured sources
and satellites, process wake words through Linux Voice Assistant, and route
responses to Home Assistant media players. The integration can also discover
HomePods, distinguish stereo pairs from temporary multi-room groups, stream
announcements through the active pair leader, and restore prior playback.

## Installation

See the [installation guide](docs/installation.md). A concise outline:

1. Add this repository to the Home Assistant add-on store.
2. Install **WakeMesh Engine**.
3. Configure one source and one disabled test assistant.
4. Set a strong API token and start the add-on.
5. Add the WakeMesh integration through HACS or copy
   `custom_components/wakemesh` into your Home Assistant configuration.
6. Validate audio, wake-word behavior, and response routing before enabling
   additional satellites.

### AirPlay announcement destinations

1. Open **Settings → Devices & services → WakeMesh → Add entry**.
2. Choose **AirPlay announcement destination**.
3. Select a discovered HomePod or stereo pair. Already configured destinations
   are omitted automatically.
4. Assign the resulting WakeMesh device to an area.
5. Use its media player anywhere Home Assistant accepts a playback destination.

Each destination also provides **Idle Announcement Volume** and **Playing
Announcement Boost** controls. The boost is expressed in percentage points: if
music is playing at 20% and boost is 10, the announcement plays at 30%.

WakeMesh collapses only genuine Apple stereo pairs. Temporary multi-room
playback groups remain separate so individual HomePods are not accidentally
treated as permanent pairs.

## Configuration example

```yaml
api_port: 8100
api_token: replace-with-a-long-random-token
home_assistant_url: http://homeassistant.local:8123
debug_logging: false
sources:
  - id: back_door
    stream_url: rtsp://go2rtc.local:8554/back_door
    audio_gain_db: 12
    assistants:
      - id: household
        enabled: false
        name: WakeMesh Back Door
        port: 6064
        wake_word: hey_jarvis
        stop_word: stop
        response_player: media_player.living_room
        response_volume: 0.3
```

Start with `enabled: false`, confirm the stream and response target, and only
then enable the assistant. Full field descriptions are in
[Configuration](docs/configuration.md).

## Privacy and security

WakeMesh handles live microphone audio. Keep its control API and source streams
on a trusted network, use a unique API token, and do not expose its ports to the
public internet. See [Security](SECURITY.md) for reporting guidance and the
current threat model.

## Development

The control API tests use Python's standard library:

```bash
python3 -m unittest discover -s tests -v
```

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## License

WakeMesh is available under the [MIT License](LICENSE).
