"""Helpers to run system commands without ever going through a shell."""

import logging
import subprocess
import threading
from collections.abc import Sequence
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class CommandError(RuntimeError):
    """A system command could not be run or exited with an error."""


def run(args: Sequence[str], *, check: bool = True, timeout: Optional[float] = 60) -> str:
    """Run a command and return its stdout.

    Args:
        args: The command and its arguments
        check: Raise CommandError on a non-zero exit code
        timeout: Maximum duration in seconds, None for no limit

    Returns:
        str: The standard output of the command

    Raises:
        CommandError: If the command cannot be run, times out or fails (when check is set)
    """
    try:
        result = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CommandError(f"{args[0]}: {exc}") from exc
    if check and result.returncode != 0:
        raise CommandError(f"{args[0]} exited with {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def spawn(args: Sequence[str]) -> "subprocess.Popen[str]":
    """Start a long-running command whose stdout and stderr can be read line by line.

    Args:
        args: The command and its arguments

    Returns:
        subprocess.Popen[str]: The running process

    Raises:
        CommandError: If the command cannot be started
    """
    try:
        return subprocess.Popen(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        raise CommandError(f"{args[0]}: {exc}") from exc


def run_in_background(task: Callable[[], None]) -> None:
    """Run a task in a daemon thread, logging any failure.

    Args:
        task: The function to run
    """

    def runner() -> None:
        try:
            task()
        except Exception:
            logger.exception("Background task failed")

    threading.Thread(target=runner, daemon=True).start()
