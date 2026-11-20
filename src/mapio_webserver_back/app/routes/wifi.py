"""WiFi scan and configuration endpoints."""

import hashlib
import logging
import os
import time

from flask import Blueprint, Response, jsonify
from werkzeug.exceptions import BadRequest

from mapio_webserver_back.app import commands, config
from mapio_webserver_back.app.security import json_body

logger = logging.getLogger(__name__)
bp = Blueprint("wifi", __name__)

_WPA_TEMPLATE = """ctrl_interface=/var/run/wpa_supplicant
ctrl_interface_group=0
update_config=1

network={{
  ssid={ssid}
  psk={psk}
  key_mgmt=WPA-PSK
  proto=WPA2
  pairwise=CCMP TKIP
  group=CCMP TKIP
  scan_ssid=1
}}
"""


def _write_wpa_conf(ssid: str, password: str) -> None:
    # Hex-encoded SSID and derived PSK keep user input out of the config syntax
    psk = hashlib.pbkdf2_hmac("sha1", password.encode(), ssid.encode(), 4096, 32).hex()
    content = _WPA_TEMPLATE.format(ssid=ssid.encode().hex(), psk=psk)
    fd = os.open(config.WPA_CONF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        os.fchmod(fd, 0o600)
        file.write(content)


def _apply_wifi() -> None:
    commands.run(["systemctl", "daemon-reload"], check=False)
    commands.run(["systemctl", "stop", "wpa_supplicant-ap.service"], check=False)
    commands.run(["systemctl", "enable", "--now", "wpa_supplicant.service"], check=False)
    time.sleep(5)  # Wait before enabling the wlan0 service
    commands.run(["systemctl", "enable", "wpa_supplicant@wlan0.service"], check=False)
    commands.run(["systemctl", "restart", "wpa_supplicant@wlan0.service"], check=False)


@bp.post("/wifi")
def set_wifi() -> tuple[Response, int]:
    """Store the WiFi credentials and switch from access point to station mode.

    Returns:
        tuple[Response, int]: 202, the network change happens after the response

    Raises:
        BadRequest: If the SSID or password is invalid
    """
    data = json_body()
    ssid = data.get("selectedWifi")
    password = data.get("password")
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32:
        raise BadRequest("Invalid SSID")
    if (
        not isinstance(password, str)
        or not 8 <= len(password) <= 63
        or not all(" " <= char <= "~" for char in password)
    ):
        raise BadRequest("The password must be 8 to 63 printable ASCII characters")

    logger.info("Setup WIFI network")
    _write_wpa_conf(ssid, password)
    commands.run_in_background(_apply_wifi)
    return jsonify(status="accepted"), 202


@bp.get("/getScan")
def get_scan() -> Response:
    """Scan the surrounding WiFi networks.

    Returns:
        Response: A list of {"name": ssid}
    """
    commands.run(["ifconfig", config.WIFI_INTERFACE, "up"], check=False)
    output = commands.run(["iw", config.WIFI_INTERFACE, "scan"], check=False)
    names = {
        line.strip().removeprefix("SSID:").strip()
        for line in output.splitlines()
        if line.strip().startswith("SSID:")
    }
    return jsonify([{"name": name} for name in sorted(names) if name])
