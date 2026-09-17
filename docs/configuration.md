# Configuration

## AirPlay announcement destinations

Add a destination from **Settings → Devices & services → WakeMesh → Add
entry → AirPlay announcement destination**. Discovery automatically matches
HomePods to their native Apple TV integration entities and removes destinations
that are already configured.

True stereo pairs are displayed as one destination and routed through the
leader advertised by AirPlay. Temporary multi-room groups remain separate.

Each destination creates:

- A WakeMesh media player usable by TTS, Assist, scripts, and automations.
- **Idle Announcement Volume**, the fixed level used when no media is playing.
- **Playing Announcement Boost**, percentage points added to the current volume.

During an announcement WakeMesh records playback state and volume, streams the
audio directly over RAOP, restores the original volume, and resumes playback
when it was previously active.

## Engine options

| Option | Purpose | Guidance |
| --- | --- | --- |
| `api_port` | Local control API port | Default: `8100` |
| `api_token` | Bearer token for API access | Use a long, unique value |
| `home_assistant_url` | Home Assistant base URL | Prefer a stable local hostname |
| `debug_logging` | Verbose assistant logging | Enable temporarily for diagnosis |
| `sources` | Audio input definitions | One entry per RTSP/go2rtc source |

## Source options

| Option | Purpose | Guidance |
| --- | --- | --- |
| `id` | Stable source identifier | Lowercase letters, numbers, underscores |
| `stream_url` | Audio-capable RTSP/go2rtc URL | Keep credentials out of screenshots/logs |
| `audio_gain_db` | Input gain before limiting | Start low; range `0`–`30` dB |
| `assistants` | Logical satellites using this source | May contain multiple personalities |

## Assistant options

| Option | Purpose | Guidance |
| --- | --- | --- |
| `id` | Stable assistant identifier | Must be unique within its source |
| `enabled` | Starts the logical satellite | Keep false until validation is complete |
| `name` | Name shown in Home Assistant | Use a location/personality label |
| `port` | ESPHome-compatible API port | Must be unique per enabled assistant |
| `wake_word` | Wake-word model name | Must exist in the Engine image |
| `stop_word` | Stop-word model name | Usually `stop` |
| `response_player` | Home Assistant media-player entity | Example: `media_player.living_room` |
| `response_volume` | Playback volume | Range `0.0`–`1.0` |

## Tuning

Increase input gain only when normal speech is consistently too quiet. Excessive
gain raises background noise and false-trigger risk. Validate changes over
several days and change one parameter at a time.

Use a separate assistant entry when a source needs another wake word,
personality, pipeline, output player, or volume. Each enabled assistant requires
a unique port.

## Control API

The alpha API is read-only:

- `GET /v1/health` — engine version, uptime, and aggregate worker health
- `GET /v1/status` — registered workers and running state
- `GET /v1/config` — effective configuration with common secrets redacted

Send `Authorization: Bearer <api_token>` with every request.
