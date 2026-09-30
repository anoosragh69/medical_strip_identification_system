"""Formatted, stage-by-stage console logging for the upload pipeline.

Owner: Person B (see tasks/split.md). Every stage of a request emits one
line: what happened, how long it took, and the fields needed to debug a demo
failure from the terminal alone.
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from typing import Iterator

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

_configured = False


def configure(level: int = logging.INFO) -> None:
    """Install the shared formatter exactly once per process."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    _configured = True


def new_logger(name: str) -> logging.Logger:
    configure()
    return logging.getLogger(name)


def log_stage(logger: logging.Logger, stage: str, status: str, elapsed_ms: float | None = None, **fields) -> None:
    """Emit one aligned stage line, e.g. `ocr               ok       confidence=0.91 ms=412`."""
    parts = [f"{key}={value}" for key, value in fields.items()]
    if elapsed_ms is not None:
        parts.append(f"ms={elapsed_ms:.0f}")
    suffix = " ".join(parts)
    logger.info("%-20s %-7s %s", stage, status, suffix)


@contextmanager
def stage_timer(logger: logging.Logger, stage: str) -> Iterator[callable]:
    """Time a stage and log it on exit.

        with stage_timer(log, "preprocess") as timer:
            image = preprocess(raw)
        timer.elapsed_ms  # available after the block
    """

    class Timer:
        elapsed_ms: float = 0.0

    timer = Timer()
    started = time.perf_counter()
    try:
        yield timer
    except Exception:
        timer.elapsed_ms = (time.perf_counter() - started) * 1000
        log_stage(logger, stage, "error", timer.elapsed_ms)
        raise
    else:
        timer.elapsed_ms = (time.perf_counter() - started) * 1000
        log_stage(logger, stage, "ok", timer.elapsed_ms)
