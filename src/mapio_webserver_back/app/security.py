"""Token authentication and request body validation."""

# pyright: reportUnusedFunction=false

import hmac
import logging
from typing import Any, Optional, cast

from flask import Flask, Response, jsonify, make_response, request
from werkzeug.exceptions import BadRequest

from mapio_webserver_back.app import config

logger = logging.getLogger(__name__)


def install_auth(app: Flask) -> None:
    """Require a bearer token on every request when MAPIO_API_TOKEN is set.

    Args:
        app: The Flask application
    """
    token = cast("Optional[str]", app.config["API_TOKEN"])
    if not token:
        logger.warning("MAPIO_API_TOKEN is not set: the API is NOT protected")
        return
    expected = token.encode()

    @app.before_request
    def check_token() -> Optional[Response]:
        # CORS preflight requests never carry credentials
        if request.method == "OPTIONS":
            return None
        scheme, _, supplied = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() == "bearer" and hmac.compare_digest(supplied.encode(), expected):
            return None
        return make_response(jsonify(error="unauthorized"), 401)


def json_body() -> dict[str, Any]:
    """Return the JSON object sent by the client.

    Returns:
        dict[str, Any]: The decoded body

    Raises:
        BadRequest: If the body is not a JSON object
    """
    request.max_content_length = config.MAX_JSON_BYTES
    data: Any = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadRequest("A JSON object is expected")
    return data  # pyright: ignore[reportUnknownVariableType]
