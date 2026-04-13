from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from engine.bandwidth import BandwidthOptimizer, BandwidthSnapshot
    from engine.peers import PeerManager, ScoredPeer
    from engine.scheduler import PieceScore, Scheduler
    from engine.torrent import TorrentEngine, TorrentStatus


def _load_runtime_dependencies() -> tuple[type[Any], type[Any], type[Any]]:
    try:
        bandwidth_module = import_module("engine.bandwidth")
        peers_module = import_module("engine.peers")
        scheduler_module = import_module("engine.scheduler")
    except ModuleNotFoundError:  # pragma: no cover - convenience for direct script execution
        bandwidth_module = import_module("bandwidth")
        peers_module = import_module("peers")
        scheduler_module = import_module("scheduler")

    bandwidth_optimizer_class = getattr(bandwidth_module, "BandwidthOptimizer")
    peer_manager_class = getattr(peers_module, "PeerManager")
    scheduler_class = getattr(scheduler_module, "Scheduler")
    return bandwidth_optimizer_class, peer_manager_class, scheduler_class


Clock = Callable[[], float]
SleepFunc = Callable[[float], Awaitable[None]]
StatsPrinter = Callable[["ControllerSnapshot"], None]


@dataclass(slots=True)
class ControllerSnapshot:
    iteration: int
    status: TorrentStatus
    peers: list[ScoredPeer]
    piece_scores: list[PieceScore]
    priorities: list[int]
    bandwidth: BandwidthSnapshot | None
    peers_updated: bool
    scheduler_updated: bool
    bandwidth_updated: bool


class Controller:
    """Coordinates engine polling, peer ranking, and piece scheduling."""

    def __init__(
        self,
        engine: TorrentEngine,
        peer_manager: PeerManager | None = None,
        scheduler: Scheduler | None = None,
        bandwidth_optimizer: BandwidthOptimizer | None = None,
        *,
        peer_interval: float = 1.0,
        scheduler_interval: float = 2.0,
        bandwidth_interval: float = 1.0,
        clock: Clock | None = None,
        sleep_func: SleepFunc | None = None,
        stats_printer: StatsPrinter | None = None,
    ) -> None:
        if peer_interval <= 0:
            raise ValueError("peer_interval must be positive.")
        if scheduler_interval <= 0:
            raise ValueError("scheduler_interval must be positive.")
        if bandwidth_interval <= 0:
            raise ValueError("bandwidth_interval must be positive.")

        bandwidth_optimizer_class, peer_manager_class, scheduler_class = (
            _load_runtime_dependencies()
        )
        self._engine = engine
        self._peer_manager = peer_manager or peer_manager_class()
        self._scheduler = scheduler or scheduler_class()
        self._bandwidth_optimizer = bandwidth_optimizer or bandwidth_optimizer_class()
        self._peer_interval = peer_interval
        self._scheduler_interval = scheduler_interval
        self._bandwidth_interval = bandwidth_interval
        self._clock = clock or time.monotonic
        self._sleep = sleep_func or asyncio.sleep
        self._stats_printer = stats_printer or self._default_stats_printer

        self._running = False
        self._started = False
        self._iteration = 0
        self._last_peer_update_at: float | None = None
        self._last_scheduler_update_at: float | None = None
        self._last_bandwidth_update_at: float | None = None
        self._cached_peer_info: list[Any] = []
        self._latest_peers: list[ScoredPeer] = []
        self._latest_piece_scores: list[PieceScore] = []
        self._latest_priorities: list[int] = []
        self._latest_bandwidth: BandwidthSnapshot | None = None
        self._last_snapshot: ControllerSnapshot | None = None

    @property
    def last_snapshot(self) -> ControllerSnapshot | None:
        return self._last_snapshot

    def start(self, torrent_file: str | Path) -> None:
        self._engine.start_session()
        self._engine.add_torrent(torrent_file)
        self._running = True
        self._started = True
        self._iteration = 0
        self._last_peer_update_at = None
        self._last_scheduler_update_at = None
        self._last_bandwidth_update_at = None
        self._cached_peer_info = []
        self._latest_peers = []
        self._latest_piece_scores = []
        self._latest_priorities = []
        self._latest_bandwidth = None
        self._last_snapshot = None

    def stop(self) -> None:
        self._running = False

    async def run(
        self,
        torrent_file: str | Path,
        *,
        poll_interval: float = 0.25,
        max_iterations: int | None = None,
    ) -> ControllerSnapshot | None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive.")
        if max_iterations is not None and max_iterations <= 0:
            raise ValueError("max_iterations must be positive when provided.")

        self.start(torrent_file)

        try:
            while self._running:
                snapshot = self.tick()

                if max_iterations is not None and snapshot.iteration >= max_iterations:
                    self.stop()
                elif snapshot.status.progress >= 100.0:
                    self.stop()

                if self._running:
                    await self._sleep(poll_interval)

            return self._last_snapshot
        finally:
            self.stop()

    def tick(self, now: float | None = None) -> ControllerSnapshot:
        if not self._started:
            raise RuntimeError("Controller has not been started.")

        observed_at = self._clock() if now is None else now
        peers_updated = False
        scheduler_updated = False
        bandwidth_updated = False
        raw_peer_info: list[Any] | None = None

        if self._is_due(self._last_peer_update_at, self._peer_interval, observed_at):
            raw_peer_info = self._engine.get_peer_info()
            self._cached_peer_info = list(raw_peer_info)
            self._latest_peers = self._peer_manager.collect(raw_peer_info, now=observed_at)
            self._last_peer_update_at = observed_at
            peers_updated = True

        if self._is_due(self._last_scheduler_update_at, self._scheduler_interval, observed_at):
            if raw_peer_info is None:
                raw_peer_info = list(self._cached_peer_info) if self._cached_peer_info else self._engine.get_peer_info()
                self._cached_peer_info = list(raw_peer_info)

            handle = self._engine.get_handle()
            self._latest_piece_scores = self._scheduler.score_pieces(handle, peer_infos=raw_peer_info)
            self._latest_priorities = self._scheduler.apply_scored_pieces(handle, self._latest_piece_scores)
            self._last_scheduler_update_at = observed_at
            scheduler_updated = True

        status = self._engine.get_status()
        if self._is_due(self._last_bandwidth_update_at, self._bandwidth_interval, observed_at):
            self._latest_bandwidth = self._bandwidth_optimizer.observe(status, self._engine.get_session())
            self._last_bandwidth_update_at = observed_at
            bandwidth_updated = True

        self._iteration += 1
        snapshot = ControllerSnapshot(
            iteration=self._iteration,
            status=status,
            peers=list(self._latest_peers),
            piece_scores=list(self._latest_piece_scores),
            priorities=list(self._latest_priorities),
            bandwidth=self._latest_bandwidth,
            peers_updated=peers_updated,
            scheduler_updated=scheduler_updated,
            bandwidth_updated=bandwidth_updated,
        )
        self._last_snapshot = snapshot
        self._stats_printer(snapshot)
        return snapshot

    @staticmethod
    def _is_due(last_updated_at: float | None, interval: float, now: float) -> bool:
        return last_updated_at is None or (now - last_updated_at) >= interval

    @staticmethod
    def _format_speed(bytes_per_second: int) -> str:
        units = ["B/s", "KiB/s", "MiB/s", "GiB/s"]
        value = float(bytes_per_second)

        for unit in units[:-1]:
            if value < 1024:
                return f"{value:.1f} {unit}"
            value /= 1024

        return f"{value:.1f} {units[-1]}"

    def _default_stats_printer(self, snapshot: ControllerSnapshot) -> None:
        line = (
            f"\rProgress: {snapshot.status.progress:6.2f}% | "
            f"Download: {self._format_speed(snapshot.status.download_rate):>12} | "
            f"Peers: {snapshot.status.peers:3d} | "
            f"Ranked: {len(snapshot.peers):3d} | "
            f"Scheduled: {len(snapshot.priorities):3d} | "
            f"Mode: {'aggressive' if snapshot.bandwidth and snapshot.bandwidth.aggressive_mode else 'normal'}"
        )
        print(line, end="", flush=True)
