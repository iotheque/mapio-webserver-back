"""OS version and OTA update endpoints."""

import logging
import threading
from typing import Any, Optional

from flask import Blueprint, Response, jsonify, request
from werkzeug.exceptions import BadRequest, Conflict

from mapio_webserver_back.app import commands, config

logger = logging.getLogger(__name__)
bp = Blueprint("system", __name__)

_lock = threading.Lock()
_state: dict[str, Optional[str]] = {"status": "idle", "updateStatus": None, "error": None}


def _set_state(
    status: str, update_status: Optional[str] = None, error: Optional[str] = None
) -> None:
    with _lock:
        _state.update(status=status, updateStatus=update_status, error=error)


def _install_bundle() -> None:
    try:
        commands.run(["rauc", "install", str(config.BUNDLE_PATH)], timeout=3600)
    except commands.CommandError:
        logger.exception("Update failed")
        _set_state("error", error="Update failed, see the device logs")
        return
    finally:
        config.BUNDLE_PATH.unlink(missing_ok=True)
    _set_state("updating", "done")
    commands.run(["reboot"], check=False)


@bp.get("/status")
def status() -> Response:
    """Return the update status.

    Returns:
        Response: status (idle, updating, error), updateStatus and error
    """
    with _lock:
        return jsonify(_state)


@bp.get("/version")
def version() -> Response:
    """Return the OS version.

    Returns:
        Response: The MAPIO_OS_VERSION_PRETTY value of /etc/os-release
    """
    os_version = ""
    try:
        for line in config.OS_RELEASE.read_text().splitlines():
            key, _, value = line.partition("=")
            if key == "MAPIO_OS_VERSION_PRETTY":
                os_version = value.strip().strip('"')
    except OSError:
        logger.warning("Cannot read %s", config.OS_RELEASE)
    return jsonify(os_version=os_version)


@bp.post("/update")
def update() -> tuple[Response, int]:
    """Receive a RAUC bundle and install it in the background, then reboot.

    Returns:
        tuple[Response, int]: 202 once the bundle is uploaded

    Raises:
        BadRequest: If no bundle is sent
        Conflict: If an update is already running
    """
    bundle: Any = request.files.get("bundle")
    if bundle is None or not bundle.filename:
        raise BadRequest("A 'bundle' file is expected")
    with _lock:
        if _state["status"] == "updating":
            raise Conflict("An update is already in progress")
        _state.update(status="updating", updateStatus=None, error=None)
    try:
        bundle.save(config.BUNDLE_PATH)
    except OSError:
        _set_state("error", error="Cannot store the bundle")
        raise
    commands.run_in_background(_install_bundle)
    return jsonify(status="updating"), 202
