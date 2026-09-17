# Installation

WakeMesh consists of the Engine add-on and an optional Home Assistant custom
integration. It currently targets Home Assistant OS or Supervised installations
that can run local add-ons.

## Prerequisites

- Home Assistant with access to the add-on store
- An RTSP or go2rtc stream containing audio
- A configured Home Assistant Assist pipeline
- A media player capable of playing Home Assistant media-source URLs
- A trusted local network between these components

## Install the Engine

1. In Home Assistant, open **Settings → Add-ons → Add-on store**.
2. Open the store menu and choose **Repositories**.
3. Add this repository's GitHub URL.
4. Install **WakeMesh Engine**.
5. Open the add-on configuration and replace every sample value.
6. Generate a long, unique `api_token`.
7. Leave the first assistant disabled while validating its source.
8. Start the add-on and inspect its log for the control API and source worker.

## Install the integration

Until a HACS release is published, copy
`custom_components/wakemesh` to `/config/custom_components/wakemesh` and restart
Home Assistant. Then:

1. Open **Settings → Devices & services**.
2. Select **Add integration** and search for **WakeMesh**.
3. Enter the Engine URL, normally `http://homeassistant.local:8100`.
4. Enter the same API token configured in the add-on.

The integration creates a WakeMesh Engine device with total-worker and
running-worker sensors.

## First satellite

Use a unique ID and port for every logical assistant. Start with a conservative
gain and response volume. After enabling the assistant, Home Assistant should
discover it as an ESPHome-compatible voice device. Assign an Assist pipeline,
then perform a quiet-room wake-word test before adjusting gain.

## Updating

Back up the add-on configuration before updating. Alpha releases may include
configuration changes; read the changelog for every version.

