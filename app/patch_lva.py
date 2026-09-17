#!/usr/bin/env python3
"""Give each WakeMesh satellite a distinct ESPHome/mDNS device identity."""

from pathlib import Path
import sysconfig


path = Path(sysconfig.get_paths()["purelib"]) / "linux_voice_assistant" / "__main__.py"
if not path.is_file():
    raise RuntimeError(f"Linux Voice Assistant source was not found: {path}")
source = path.read_text(encoding="utf-8")

if "import os\n" not in source:
    source = source.replace("import logging\n", "import logging\nimport os\n", 1)
if "import hashlib\n" not in source:
    source = source.replace("import logging\n", "import hashlib\nimport logging\n", 1)

old = '    mac_address_clean = mac_address.replace(":", "").lower()\n'
new = (
    '    # WakeMesh virtual MAC: keep each routed satellite distinct in Home Assistant.\n'
    '    device_suffix = os.environ.get("LVA_DEVICE_SUFFIX", "").strip("-")\n'
    '    if device_suffix:\n'
    '        virtual_mac = hashlib.sha256(device_suffix.encode()).hexdigest()[:10]\n'
    '        mac_address = "02:" + ":".join(virtual_mac[i:i + 2] for i in range(0, 10, 2))\n'
    '    mac_address_clean = mac_address.replace(":", "").lower()\n'
)
if "WakeMesh virtual MAC" in source:
    pass
elif old in source:
    source = source.replace(old, new, 1)
else:
    raise RuntimeError("Unable to locate LVA device-name assignment")

path.write_text(source, encoding="utf-8")

verified = path.read_text(encoding="utf-8")
if "WakeMesh virtual MAC" not in verified:
    raise RuntimeError(f"LVA identity patch verification failed: {path}")
print(f"WakeMesh identity patch verified: {path}", flush=True)
