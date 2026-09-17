FROM python:3.13-slim-bookworm

ARG LVA_VERSION=1.1.15

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      alsa-utils avahi-utils bash build-essential ca-certificates ffmpeg git \
      jq libasound2-plugins libmpv-dev pulseaudio pulseaudio-utils procps curl && \
    pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
      "linux-voice-assistant @ https://github.com/OHF-Voice/linux-voice-assistant/archive/refs/tags/v${LVA_VERSION}.tar.gz" && \
    git clone --depth 1 --branch "v${LVA_VERSION}" \
      https://github.com/OHF-Voice/linux-voice-assistant.git /tmp/lva && \
    mkdir -p /opt/lva && \
    cp -R /tmp/lva/sounds /tmp/lva/wakewords /opt/lva/ && \
    apt-get purge -y --auto-remove git build-essential && \
    rm -rf /tmp/lva /var/lib/apt/lists/*

COPY patch_lva.py /usr/local/bin/patch_lva.py
RUN chmod 755 /usr/local/bin/patch_lva.py && python3 /usr/local/bin/patch_lva.py

COPY run.sh audio_input.sh response_router.py control_api.py pulse.pa /usr/local/bin/
RUN chmod 755 /usr/local/bin/run.sh /usr/local/bin/audio_input.sh \
    /usr/local/bin/response_router.py /usr/local/bin/control_api.py

ENTRYPOINT ["/usr/local/bin/run.sh"]
