"""Paths and limits used by the endpoints, overridable from the environment."""

import os
from pathlib import Path

COMPOSE_FILE = Path(os.environ.get("MAPIO_COMPOSE_FILE", "/home/root/mapio/docker-compose.yml"))
TOOLS_DIR = Path(os.environ.get("MAPIO_TOOLS_DIR", "/home/root/tools"))
WPA_CONF = Path("/etc/wpa_supplicant/wpa_supplicant-wlan0.conf")
OS_RELEASE = Path("/etc/os-release")
BUNDLE_PATH = Path("/usr/local/bundle.raucb")
WIFI_INTERFACE = "wlan0"

MAX_UPLOAD_BYTES = 2 * 1024**3
MAX_JSON_BYTES = 1024**2
MAX_LOG_STREAMS = 3
