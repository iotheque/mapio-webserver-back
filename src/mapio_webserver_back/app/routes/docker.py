"""Docker compose and container management endpoints."""

import logging
import threading
from collections import defaultdict
from typing import Any, cast

import yaml
from flask import Blueprint, Response, jsonify
from werkzeug.exceptions import BadRequest

from mapio_webserver_back.app import commands, config
from mapio_webserver_back.app.security import json_body

logger = logging.getLogger(__name__)
bp = Blueprint("docker", __name__)

COMPOSE_ACTIONS = ("pull", "create")
CONTAINER_ACTIONS = ("start", "stop", "restart")

# Docker operations must not overlap
_docker_lock = threading.Lock()


def _as_dict(value: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _compose_services() -> dict[str, Any]:
    try:
        with config.COMPOSE_FILE.open() as file:
            data: Any = yaml.safe_load(file)
    except (OSError, yaml.YAMLError) as exc:
        raise commands.CommandError(f"Cannot read {config.COMPOSE_FILE}: {exc}") from exc
    return _as_dict(_as_dict(data).get("services"))


def _split_image(image: str) -> tuple[str, str]:
    # A colon before the last slash belongs to a registry port, not to a tag
    if ":" in image.rsplit("/", 1)[-1]:
        name, _, tag = image.rpartition(":")
        return name, tag
    return image, "latest"


def _selected(data: dict[str, Any], key: str, allowed: set[str]) -> list[str]:
    selected: Any = data.get(key)
    if not isinstance(selected, list):
        raise BadRequest(f"Invalid {key}")
    items = cast("list[Any]", selected)
    if not items or not all(isinstance(item, str) and item in allowed for item in items):
        raise BadRequest(f"Invalid {key}")
    return cast("list[str]", items)


def _action(data: dict[str, Any], allowed: tuple[str, ...]) -> str:
    action = str(data.get("select_action"))
    if action not in allowed:
        raise BadRequest(f"Unknown action, expected one of {', '.join(allowed)}")
    return action


def _script_output(name: str) -> str:
    try:
        return commands.run([str(config.TOOLS_DIR / name)], check=False)
    except commands.CommandError as exc:
        logger.warning("%s", exc)
        return ""


def _container_names() -> list[str]:
    output = commands.run(["docker", "ps", "-a", "--format", "{{.Names}}"])
    return output.split()


@bp.get("/compose")
def compose_list() -> Response:
    """List the services declared in the docker-compose file.

    Returns:
        Response: A list of {"name", "image", "version"}
    """
    containers: list[dict[str, str]] = []
    for name, service in _compose_services().items():
        image, version = _split_image(str(_as_dict(service).get("image", "None")))
        containers.append({"name": str(name), "image": image, "version": version})
    return jsonify(containers)


@bp.post("/compose")
def compose_action() -> tuple[Response, int]:
    """Pull or recreate compose services in the background.

    Returns:
        tuple[Response, int]: 202 once the action is scheduled
    """
    data = json_body()
    services = _selected(data, "selectedServices", set(_compose_services()))
    action = _action(data, COMPOSE_ACTIONS)
    base = ["docker", "compose", "-f", str(config.COMPOSE_FILE)]

    def task() -> None:
        with _docker_lock:
            for service in services:
                logger.info("docker compose %s %s", action, service)
                if action == "pull":
                    commands.run([*base, "pull", service], timeout=None)
                commands.run([*base, "up", "-d", "--force-recreate", service], timeout=None)
            if action == "pull":
                commands.run(["docker", "system", "prune", "-f"], timeout=None)

    commands.run_in_background(task)
    return jsonify(status="accepted"), 202


@bp.get("/docker")
def container_list() -> Response:
    """List the containers with their status and published ports.

    Returns:
        Response: A list of {"name", "status", "port"}
    """
    output = commands.run(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"])

    ports: defaultdict[str, list[str]] = defaultdict(list)
    for line in _script_output("docker_scan_port.sh").splitlines():
        parts = line.split()
        if len(parts) == 2:
            ports[parts[0]].append(parts[1])

    containers: list[dict[str, str]] = []
    for line in output.splitlines():
        name, _, status = line.partition("\t")
        containers.append(
            {
                "name": name,
                "status": status.split(" ")[0],
                "port": ", ".join(ports[name]),
            }
        )
    return jsonify(containers)


@bp.post("/docker")
def container_action() -> tuple[Response, int]:
    """Start, stop or restart containers in the background.

    Returns:
        tuple[Response, int]: 202 once the action is scheduled
    """
    data = json_body()
    containers = _selected(data, "selectedServices", set(_container_names()))
    action = _action(data, CONTAINER_ACTIONS)

    def task() -> None:
        with _docker_lock:
            for container in containers:
                logger.info("docker %s %s", action, container)
                commands.run(["docker", action, container])

    commands.run_in_background(task)
    return jsonify(status="accepted"), 202


@bp.get("/docker-update")
def docker_update() -> Response:
    """Tell which containers have a newer image available.

    Returns:
        Response: A list of {"name", "update"}
    """
    updates: list[dict[str, str]] = []
    for line in _script_output("docker_check_versions.sh").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            updates.append({"name": parts[0], "update": parts[1]})
    return jsonify(updates)


@bp.get("/load-yaml")
def load_yaml() -> Response:
    """Return the raw docker-compose file.

    Returns:
        Response: {"content": text}
    """
    try:
        return jsonify(content=config.COMPOSE_FILE.read_text())
    except OSError as exc:
        raise commands.CommandError(f"Cannot read {config.COMPOSE_FILE}: {exc}") from exc


@bp.post("/save-yaml")
def save_yaml() -> Response:
    """Validate and atomically replace the docker-compose file.

    Returns:
        Response: {"status": "ok"}

    Raises:
        BadRequest: If the content is not a valid compose YAML mapping
    """
    content = json_body().get("content")
    if not isinstance(content, str):
        raise BadRequest("'content' must be a string")
    try:
        parsed: Any = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise BadRequest(f"Invalid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BadRequest("The compose file must be a YAML mapping")

    temp = config.COMPOSE_FILE.with_name(config.COMPOSE_FILE.name + ".tmp")
    temp.write_text(content)
    temp.replace(config.COMPOSE_FILE)
    return jsonify(status="ok")
