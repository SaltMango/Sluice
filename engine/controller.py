from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from engine.config import EngineConfig
from engine.models import TorrentState, PieceState, PriorityBucket, PeerInfo
from engine.exceptions import EngineError
from engine.logger import get_logger
from engine.events import EventBus
from engine.metrics import MetricsCollector, TorrentMetrics

from engine.bandwidth import BandwidthOptimizer
from engine.peers import PeerManager
from engine.scheduler import Scheduler
from engine.torrent import TorrentEngine

logger = get_logger(__name__)


class Controller:
    """Coordinates engine polling, domain models, events, and fault-tolerant state loops."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()

        self.engine = TorrentEngine()
        self.peer_manager = PeerManager(self.config.peers)
        self.scheduler = Scheduler(self.config.scheduler)
        self.bandwidth_optimizer = BandwidthOptimizer(self.config.bandwidth)

        self.event_bus = EventBus()
        self.metrics = MetricsCollector()

        self._running = False
        self._started = False
        self._last_states: dict[str, TorrentState] = {}

        # ── Cached sub-system data (populated per-tick; read by API handlers) ──
        # Keyed by t_id
        self._last_peers: dict[str, list[PeerInfo]] = {}
        self._last_piece_counts: dict[str, dict[str, Any]] = {}
        self._last_completed_pieces: dict[str, int] = {}
        self._last_bw_utilization: dict[str, float] = {}
        self._piece_count_start: dict[str, float] = {}  # when we first saw this torrent

        # Interval timestamps
        self._last_peer_update_at: float | None = None
        self._last_scheduler_update_at: float | None = None
        self._last_bandwidth_update_at: float | None = None
        self._last_save_resume_at: float | None = None

        self._lock = asyncio.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self.engine.start_session()
        self._running = True
        self._started = True

        configured_bw = getattr(self.config.bandwidth, "configured_max_bandwidth", None) or 0
        self.metrics.set_configured_max_bandwidth(int(configured_bw))
        self._last_save_resume_at = time.monotonic()

        logger.info("Controller loop started")
        asyncio.create_task(self.event_bus.publish("controller_started", {}))

    def stop(self) -> None:
        self._running = False

    async def run(self, poll_interval: float = 0.5) -> None:
        self.start()
        try:
            while self._running:
                await self.tick()
                for t_id, state in list(self._last_states.items()):
                    if state.progress >= 100.0 and getattr(state, "_did_complete", False) is False:
                        setattr(state, "_did_complete", True)
                        logger.info("Download completed", extra={"torrent": t_id})
                        await self.event_bus.publish("download_complete", {"state": state})
                if self._running:
                    await asyncio.sleep(poll_interval)
        except EngineError as e:
            logger.exception("Domain error in main loop", extra={"error": str(e)})
            await self.event_bus.publish("error", {"error": str(e)})
        except asyncio.CancelledError:
            logger.info("Controller loop cancelled")
        finally:
            await self.shutdown()

    # ── State accessors (safe for API handlers) ───────────────────────────────

    def get_all_states(self) -> dict[str, TorrentState]:
        return self._last_states.copy()

    def get_state(self, t_id: str) -> TorrentState | None:
        return self._last_states.get(t_id)

    def get_cached_peers(self, t_id: str) -> list[PeerInfo]:
        return list(self._last_peers.get(t_id, []))

    def build_torrent_metrics(self, t_id: str) -> TorrentMetrics | None:
        """Assemble TorrentMetrics from cached data — zero libtorrent calls."""
        state = self._last_states.get(t_id)
        if state is None:
            return None

        piece_counts = dict(self._last_piece_counts.get(t_id, {}))
        # Inject the start timestamp so piece_rate is correct
        if "_start_time" not in piece_counts:
            piece_counts["_start_time"] = self._piece_count_start.get(t_id, time.monotonic())

        return self.metrics.build_torrent_metrics(
            peers=self.get_cached_peers(t_id),
            piece_counts=piece_counts,
            scheduler_last=dict(self.scheduler.last_metrics),
            scheduler_config=self.config.scheduler,
            completed_pieces=self._last_completed_pieces.get(t_id, 0),
            bw_utilization=self._last_bw_utilization.get(t_id, 0.0),
            seeds_connected=state.seeds_connected,
        )

    # ── Main tick ─────────────────────────────────────────────────────────────

    async def tick(self) -> None:
        async with self._lock:
            now = time.monotonic()

            for t_id in self.engine.get_all_active_ids():
                try:
                    # Register start timestamp on first sight
                    if t_id not in self._piece_count_start:
                        self._piece_count_start[t_id] = now

                    # State snapshot
                    state = self.engine.get_state(t_id)
                    self._last_states[t_id] = state

                    # Speed + milestones
                    self.metrics.record_speed(state.download_speed)
                    if state.progress >= 50.0:
                        self.metrics.notify_50pct(t_id)

                    # Bandwidth utilization (cheap to compute every tick)
                    configured_bw = getattr(self.config.bandwidth, "configured_max_bandwidth", None) or 0
                    current_speed = state.download_speed
                    if configured_bw > 0:
                        bw_util = min(1.0, current_speed / configured_bw)
                    else:
                        # Fall back to fraction of peak observed
                        peak = self.metrics.speed._peak
                        bw_util = min(1.0, current_speed / peak) if peak > 0 else 0.0
                    self._last_bw_utilization[t_id] = bw_util

                    # ── Peer sub-system ───────────────────────────────────────
                    if self._is_due(self._last_peer_update_at, self.config.peer_interval, now):
                        peers = self.engine.get_peers(t_id, active_time=now)
                        self._last_peers[t_id] = peers
                        self.peer_manager.evaluate(peers)
                        await self.event_bus.publish("peers_updated", {
                            "torrent": t_id,
                            "total": len(peers),
                            "choked": sum(1 for p in peers if p.is_choked),
                        })

                    # ── Scheduler sub-system ──────────────────────────────────
                    if self._is_due(self._last_scheduler_update_at, self.config.scheduler_interval, now):
                        pieces = self.engine.get_pieces(t_id)
                        peers = self.engine.get_peers(t_id, active_time=now)
                        self._last_peers[t_id] = peers  # freshen cache

                        scored_pieces = self.scheduler.score_pieces(pieces, peers)

                        priorities = [0] * len(pieces)
                        completed_count = 0
                        for sp in scored_pieces:
                            priorities[sp.info.index] = sp.priority.value
                            if sp.info.is_complete:
                                completed_count += 1
                                self.metrics.record_piece_complete()

                        self.engine.apply_priorities(t_id, priorities)
                        self._last_completed_pieces[t_id] = completed_count

                        # Compute piece counts
                        avail_list = [p.availability for p in pieces if not p.is_complete]
                        min_avail = min(avail_list, default=0)
                        stalled = sum(
                            1 for p in pieces
                            if not p.is_complete and p.state == PieceState.AVAILABLE and p.availability == 0
                        )
                        rarest = sum(
                            1 for p in pieces
                            if not p.is_complete and p.availability <= min_avail + 1
                        )

                        self._last_piece_counts[t_id] = {
                            "total": len(pieces),
                            "completed": sum(1 for p in pieces if p.is_complete),
                            "active": sum(
                                1 for p in pieces
                                if not p.is_complete and p.state in (PieceState.REQUESTED, PieceState.DOWNLOADING)
                            ),
                            "stalled": stalled,
                            "rarest_count": rarest,
                            "min_availability": min_avail,
                            "max_availability": max(avail_list, default=0),
                            "avg_availability": int(sum(avail_list) / max(len(avail_list), 1)),
                            "_start_time": self._piece_count_start[t_id],
                        }

                        await self.event_bus.publish("pieces_scheduled", {
                            "torrent": t_id,
                            "assigned": len(scored_pieces),
                        })

                    # ── Bandwidth sub-system ──────────────────────────────────
                    if self._is_due(self._last_bandwidth_update_at, self.config.bandwidth_interval, now):
                        settings = self.engine.get_session_settings()
                        tuned = self.bandwidth_optimizer.observe_and_tune(state, settings)
                        self.engine.apply_session_settings(tuned)
                        self._last_bandwidth_update_at = now

                except EngineError as e:
                    logger.warning(f"Engine iteration error on {t_id}: {e}")

            # ── Libtorrent alert loop ─────────────────────────────────────────
            if self.engine._session:
                try:
                    import libtorrent as lt
                    for alert in self.engine._session.pop_alerts():
                        if type(alert).__name__ == "save_resume_data_alert":
                            t_id = str(alert.handle.info_hash())
                            path = self.engine._resume_paths.get(t_id)
                            if path:
                                try:
                                    data = lt.bencode(lt.write_resume_data(alert.params))
                                    with open(path, "wb") as f:
                                        f.write(data)
                                    logger.info("Resume block written", extra={"torrent": t_id})
                                except Exception as e:
                                    logger.error("Failed to bencode resume", extra={"error": str(e)})
                except Exception as eval_e:
                    logger.error("Alert loop error", extra={"error": str(eval_e)})

            # ── Interval bookkeeping ──────────────────────────────────────────
            if self._is_due(self._last_peer_update_at, self.config.peer_interval, now):
                self._last_peer_update_at = now
            if self._is_due(self._last_scheduler_update_at, self.config.scheduler_interval, now):
                self._last_scheduler_update_at = now
            if self._is_due(self._last_bandwidth_update_at, self.config.bandwidth_interval, now):
                self._last_bandwidth_update_at = now

            if self._is_due(self._last_save_resume_at, self.config.autosave_resume_interval, now):
                self.engine.save_resume_data()
                self._last_save_resume_at = now
                await self.event_bus.publish("autosave_triggered", {})

    # ── Graceful shutdown ─────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        logger.info("Initiating controller shutdown")
        async with self._lock:
            self.engine.save_resume_data()
            if self.engine._session:
                try:
                    import libtorrent as lt
                    alerts_expected = len(self.engine._handles)
                    attempts = 0
                    while alerts_expected > 0 and attempts < 10:
                        for alert in self.engine._session.pop_alerts():
                            if type(alert).__name__ == "save_resume_data_alert":
                                t_id = str(alert.handle.info_hash())
                                path = self.engine._resume_paths.get(t_id)
                                if path:
                                    try:
                                        data = lt.bencode(lt.write_resume_data(alert.params))
                                        with open(path, "wb") as f:
                                            f.write(data)
                                        alerts_expected -= 1
                                    except Exception:
                                        pass
                            elif type(alert).__name__ == "save_resume_data_failed_alert":
                                alerts_expected -= 1
                        await asyncio.sleep(0.5)
                        attempts += 1
                except Exception:
                    pass
            self.engine.pause_and_shutdown()
            await self.event_bus.publish("controller_shutdown")

    @staticmethod
    def _is_due(last_at: float | None, interval: float, now: float) -> bool:
        return last_at is None or (now - last_at) >= interval
