# Architecture

WakeMesh separates real-time audio work from Home Assistant configuration.

## Engine: data plane

The Engine add-on owns the processes that must run continuously:

- FFmpeg RTSP/go2rtc ingestion, filtering, resampling, and limiting
- PulseAudio virtual sources and sinks
- Wake-word, voice-activity, and Assist session processing
- Response capture, encoding, and media-player routing
- Worker registration, health reporting, and watchdog recovery

Each physical source may host multiple logical assistants. Each logical
assistant receives a distinct identity, wake-word configuration, Assist pipeline
assignment, and response target.

## Integration: control plane

The Home Assistant integration connects to the Engine's versioned HTTP API. In
the current milestone it discovers health and worker status. Planned milestones
move source and assistant configuration into config entries and add diagnostics,
repairs, and safe worker reconciliation.

## Home Assistant and Frigate boundaries

Home Assistant owns Assist pipelines, intent handling, devices, entities, and
response players. Frigate may provide camera restreams, events, and audio
classification, but WakeMesh does not modify Frigate configuration or use
Frigate as the conversational pipeline.

## Reliability model

The Engine exits when a critical audio worker stops so Home Assistant's add-on
watchdog can recover the full process graph. Runtime worker records back the
health/status API. Configuration changes are intentionally restart-based during
the alpha phase.

## Roadmap

1. Read-only health, status, and redacted-configuration API.
2. Authenticated test and restart commands.
3. Validated configuration updates with atomic worker reconciliation.
4. Native `AssistSatelliteEntity` instances and removal of compatibility shims.
5. Per-personality wake words, pipelines, prompts, voices, and response routes.

