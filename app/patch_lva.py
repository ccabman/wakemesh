#!/usr/bin/env python3
"""Apply the small WakeMesh hooks needed by Linux Voice Assistant."""

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

satellite_path = path.with_name("satellite.py")
satellite_source = satellite_path.read_text(encoding="utf-8")
if "import os\n" not in satellite_source:
    satellite_source = satellite_source.replace("import logging\n", "import logging\nimport os\n", 1)
if "from pathlib import Path\n" not in satellite_source:
    satellite_source = satellite_source.replace(
        "from functools import partial\n", "from functools import partial\nfrom pathlib import Path\n", 1
    )

wake_anchor = "        self._emit(LVAEvent.WAKE_WORD_DETECTED)\n        self.duck()\n"
wake_hook = (
    "        self._emit(LVAEvent.WAKE_WORD_DETECTED)\n"
    "        # WakeMesh hook: notify the response router before listening begins.\n"
    "        wake_event_file = os.environ.get(\"WAKEMESH_WAKE_EVENT_FILE\")\n"
    "        if wake_event_file:\n"
    "            try:\n"
    "                Path(wake_event_file).touch()\n"
    "            except OSError:\n"
    "                _LOGGER.exception(\"Unable to emit WakeMesh wake event\")\n"
    "        self.duck()\n"
)
if "WakeMesh hook: notify the response router" in satellite_source:
    pass
elif wake_anchor in satellite_source:
    satellite_source = satellite_source.replace(wake_anchor, wake_hook, 1)
else:
    raise RuntimeError("Unable to locate LVA wake-word event")

satellite_path.write_text(satellite_source, encoding="utf-8")

verified = path.read_text(encoding="utf-8")
if "WakeMesh virtual MAC" not in verified:
    raise RuntimeError(f"LVA identity patch verification failed: {path}")
if "WakeMesh hook: notify the response router" not in satellite_path.read_text(encoding="utf-8"):
    raise RuntimeError(f"LVA wake-event patch verification failed: {satellite_path}")
print(f"WakeMesh patches verified: {path}, {satellite_path}", flush=True)
