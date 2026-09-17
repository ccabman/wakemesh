# Security policy

## Supported versions

WakeMesh is pre-release software. Security fixes are applied to the latest
published version only.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature when it is enabled
for this repository. Do not open a public issue containing credentials,
recordings, private network details, or an exploitable proof of concept.

## Deployment guidance

- Keep the Engine API and all media streams on a trusted local network.
- Do not forward WakeMesh, RTSP, go2rtc, ESPHome, or Home Assistant ports to the
  public internet.
- Replace the default API token before starting the add-on.
- Use dedicated least-privilege camera credentials when available.
- Treat logs and captured audio as sensitive household data.

