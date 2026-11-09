"""SSH authorized keys endpoint."""

import logging
import os
import re
from pathlib import Path

from flask import Blueprint, Response, jsonify
from werkzeug.exceptions import BadRequest

from mapio_webserver_back.app.security import json_body

logger = logging.getLogger(__name__)
bp = Blueprint("ssh", __name__)

_KEY_PATTERN = re.compile(
    r"(ssh-(rsa|ed25519)|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com"
    r"|sk-ecdsa-sha2-nistp256@openssh\.com) [A-Za-z0-9+/]+={0,3}( [^\r\n]*)?"
)


@bp.post("/ssh-setkey")
def ssh_setkey() -> Response:
    """Append a public key to the authorized keys of the server user.

    Returns:
        Response: The status of the operation

    Raises:
        BadRequest: If the key is not a single-line OpenSSH public key
    """
    key = json_body().get("userkey")
    if not isinstance(key, str) or not _KEY_PATTERN.fullmatch(key.strip()):
        raise BadRequest("Invalid SSH public key")
    key = key.strip()

    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    authorized_keys = ssh_dir / "authorized_keys"
    existing = authorized_keys.read_text().splitlines() if authorized_keys.exists() else []
    if key not in existing:
        fd = os.open(authorized_keys, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as file:
            file.write(key + "\n")
    logger.info("SSH key added")
    return jsonify(status="ok")
