"""
apply_tune — maps a TuneLevel to concrete libtorrent handle settings.

Safety cap
----------
GLOBAL_MAX_PEERS = 250 — no single torrent is allowed to open more than
this many connections regardless of the requested level, preventing
resource exhaustion on constrained systems.
"""

from __future__ import annotations

from typing import Any

from engine.models import TuneLevel
from engine.logger import get_logger

logger = get_logger(__name__)

# Hard ceiling — no single torrent may exceed this connection count.
GLOBAL_MAX_PEERS = 250

# Level → (max_connections, request_queue_time_seconds)
_LEVEL_SETTINGS: dict[TuneLevel, dict[str, int]] = {
    TuneLevel.SAFE:       {"max_connections": 50,  "request_queue_time": 5},
    TuneLevel.BALANCED:   {"max_connections": 100, "request_queue_time": 3},
    TuneLevel.AGGRESSIVE: {"max_connections": 200, "request_queue_time": 2},
    TuneLevel.EXTREME:    {"max_connections": 300, "request_queue_time": 1},
}


def apply_tune(handle: Any, tune_level: TuneLevel) -> None:
    """
    Apply per-torrent connection limits for *tune_level* to a libtorrent
    torrent handle.  All values are capped at GLOBAL_MAX_PEERS.

    Silently absorbs libtorrent errors so a failed apply never crashes the
    controller tick.
    """
    settings = _LEVEL_SETTINGS[tune_level]
    max_conns = min(settings["max_connections"], GLOBAL_MAX_PEERS)

    try:
        handle.set_max_connections(max_conns)
        # Never cap uploads — the tuner controls download throughput only.
        handle.set_upload_limit(0)
        logger.debug(
            "apply_tune",
            extra={"level": tune_level.name, "max_connections": max_conns},
        )
    except Exception as exc:
        logger.warning(
            "apply_tune failed",
            extra={"level": tune_level.name, "error": str(exc)},
        )
