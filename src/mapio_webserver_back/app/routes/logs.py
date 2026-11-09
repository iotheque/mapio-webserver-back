"""Live container logs streamed with Server-Sent Events."""

import json
import logging
import queue
import subprocess
import threading
from collections.abc import Iterator
from typing import Optional

from flask import Blueprint, Response, request
from werkzeug.exceptions import TooManyRequests

from mapio_webserver_back.app import commands, config

logger = logging.getLogger(__name__)
bp = Blueprint("logs", __name__)

# Idle connections are dropped by the server, a comment line keeps them open
KEEPALIVE_SECONDS = 15

_slots = threading.BoundedSemaphore(config.MAX_LOG_STREAMS)


@bp.get("/logs/stream")
def stream_logs() -> Response:
    """Stream `docker compose logs -f` as Server-Sent Events.

    Each event carries one JSON-encoded log line, the stream ends with an "end" event.

    Returns:
        Response: A text/event-stream response

    Raises:
        TooManyRequests: If too many streams are already open
    """
    tail = max(0, min(request.args.get("tail", default=50, type=int) or 0, 1000))
    if not _slots.acquire(blocking=False):
        raise TooManyRequests("Too many log streams are open")

    try:
        process = commands.spawn(
            [
                "docker",
                "compose",
                "-f",
                str(config.COMPOSE_FILE),
                "logs",
                "--tail",
                str(tail),
                "-f",
            ]
        )
    except commands.CommandError:
        _slots.release()
        raise

    lines: queue.Queue[Optional[str]] = queue.Queue(maxsize=1000)
    stop = threading.Event()

    def put(item: Optional[str]) -> bool:
        while not stop.is_set():
            try:
                lines.put(item, timeout=1)
            except queue.Full:
                continue
            return True
        return False

    def read() -> None:
        assert process.stdout is not None  # noqa: S101
        for line in process.stdout:
            if not put(line.rstrip("\r\n")):
                return
        put(None)

    threading.Thread(target=read, daemon=True).start()

    def events() -> Iterator[str]:
        while True:
            try:
                line = lines.get(timeout=KEEPALIVE_SECONDS)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if line is None:
                yield "event: end\ndata: {}\n\n"
                return
            yield f"data: {json.dumps(line)}\n\n"

    released = threading.Lock()

    def cleanup() -> None:
        stop.set()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        if released.acquire(blocking=False):
            _slots.release()

    response = Response(
        events(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    response.call_on_close(cleanup)
    return response
