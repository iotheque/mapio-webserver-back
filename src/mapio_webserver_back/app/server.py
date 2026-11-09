"""Create the flask application serving the endpoints called by the frontend."""

# pyright: reportUnusedFunction=false

import logging
import os
from typing import Any, Optional, cast

from flask import Flask, Response, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from mapio_webserver_back.app import commands, config
from mapio_webserver_back.app.routes import docker, logs, ssh, system, wifi
from mapio_webserver_back.app.security import install_auth


def create_app(test_config: Optional[dict[str, Any]] = None) -> Flask:
    """Create the app.

    Environment variables:
        MAPIO_API_TOKEN: Bearer token required by every endpoint
        MAPIO_CORS_ORIGINS: Comma-separated allowed origins, "*" by default

    Args:
        test_config: Values overriding the configuration read from the environment

    Returns:
        Flask: The server
    """
    logger = logging.getLogger(__name__)
    logger.info("Create the app")

    app = Flask(__name__)
    app.config.from_mapping(
        API_TOKEN=os.environ.get("MAPIO_API_TOKEN"),
        CORS_ORIGINS=os.environ.get("MAPIO_CORS_ORIGINS", "*"),
        MAX_CONTENT_LENGTH=config.MAX_UPLOAD_BYTES,
    )
    app.config.from_mapping(test_config or {})

    cors_origins = cast(str, app.config["CORS_ORIGINS"])
    CORS(app, origins=[origin.strip() for origin in cors_origins.split(",")])
    install_auth(app)

    for blueprint in (system.bp, wifi.bp, docker.bp, ssh.bp, logs.bp):
        app.register_blueprint(blueprint)

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException) -> tuple[Response, int]:
        return jsonify(error=error.description), error.code or 500

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception) -> tuple[Response, int]:
        if isinstance(error, commands.CommandError):
            logger.error("%s", error)
        else:
            logger.exception("Unhandled error")
        return jsonify(error="internal error"), 500

    return app
