# Contributing to WakeMesh

Thank you for helping improve WakeMesh.

## Before opening a change

- Search existing issues and discussions.
- Keep credentials, private hostnames, IP addresses, and audio samples out of
  commits and logs.
- For behavioral changes, explain the audio path and failure mode being changed.
- Keep safety-critical claims out of documentation and UI text.

## Development workflow

1. Fork the repository and create a focused branch.
2. Make the smallest coherent change.
3. Run `python3 -m unittest discover -s tests -v`.
4. Update documentation and the changelog when behavior changes.
5. Open a pull request describing validation hardware and Home Assistant version.

## Bug reports

Include WakeMesh version, Home Assistant version, architecture, a redacted
configuration, and relevant logs. Never post RTSP credentials, API tokens, or
unredacted private network details.

