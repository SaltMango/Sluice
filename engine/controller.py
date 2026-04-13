from __future__ import annotations

import asyncio
import time
from pathlib import Path

from engine.config import EngineConfig
from engine.models import TorrentState, PieceState, PriorityBucket
from engine.exceptions import EngineError
from engine.logger import get_logger
from engine.events import EventBus
from engine.metrics import MetricsCollector

from engine.bandwidth import BandwidthOptimizer
from engine.peers import PeerManager
from engine.scheduler import Scheduler
from engine.torrent import TorrentEngine

logger = get_logger(__name__)

class Controller:
    """Coordinates engine polling, domain decoupled models, events, and fault-tolerant state loops."""

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
        self._last_state: TorrentState | None = None
        
        self._last_peer_update_at: float | None = None
        self._last_scheduler_update_at: float | None = None
        self._last_bandwidth_update_at: float | None = None
        self._last_save_resume_at: float | None = None

        self._lock = asyncio.Lock()

    def start(self, torrent_file: str | Path) -> None:
        self.engine.start_session()
        self.engine.add_torrent(torrent_file)
        
        self._running = True
        self._started = True
        
        now = time.monotonic()
        self._last_save_resume_at = now
        
        logger.info("Controller started", extra={"torrent": str(torrent_file)})
        asyncio.create_task(self.event_bus.publish("controller_started", {"torrent": str(torrent_file)}))

    def stop(self) -> None:
        self._running = False

    async def run(self, torrent_file: str | Path, poll_interval: float = 0.5) -> None:
        self.start(torrent_file)

        try:
            while self._running:
                await self.tick()
                
                if self._last_state and self._last_state.progress >= 100.0:
                    logger.info("Download completed natively")
                    await self.event_bus.publish("download_complete", {"state": self._last_state})
                    self.stop()
                    
                if self._running:
                    await asyncio.sleep(poll_interval)
                    
        except EngineError as e:
            logger.exception("Domain error occurred in main loop", extra={"error": str(e)})
            await self.event_bus.publish("error", {"error": str(e)})
        except asyncio.CancelledError:
            logger.info("Controller loop cancelled")
        finally:
            await self.shutdown()

    def get_state(self) -> TorrentState | None:
        """Safe boundary for UIs to snapshot the absolute state instantly."""
        return self._last_state

    async def tick(self) -> None:
        async with self._lock:
            now = time.monotonic()
            
            # Extract state
            state = self.engine.get_state()
            self._last_state = state
            
            # Metrics Logging
            self.metrics.record_speed(state.download_speed)
            
            # Sub-system Interval triggers
            if self._is_due(self._last_peer_update_at, self.config.peer_interval, now):
                peers = self.engine.get_peers(active_time=now)
                scored_peers = self.peer_manager.evaluate(peers)
                self._last_peer_update_at = now
                
                await self.event_bus.publish("peers_updated", {
                    "total": len(peers),
                    "choked": sum(1 for p in peers if p.is_choked)
                })

            if self._is_due(self._last_scheduler_update_at, self.config.scheduler_interval, now):
                pieces = self.engine.get_pieces()
                peers = self.engine.get_peers(active_time=now)
                
                scored_pieces = self.scheduler.score_pieces(pieces, peers)
                
                # Assign bucket values
                priorities = [0] * len(pieces)
                for sp in scored_pieces:
                    val = sp.priority.value
                    priorities[sp.info.index] = val
                    if sp.info.is_complete:
                        self.metrics.record_piece_complete()

                self.engine.apply_priorities(priorities)
                self._last_scheduler_update_at = now
                
                active_pieces = sum(1 for p in pieces if not p.is_complete and p.state in (PieceState.REQUESTED, PieceState.DOWNLOADING))
                assigned_high = sum(1 for p in priorities if p == PriorityBucket.HIGH.value)
                assigned_low = sum(1 for p in priorities if p == PriorityBucket.LOW.value)

                logger.debug("scheduler_decisions", extra={
                    "assigned_total": len(scored_pieces),
                    "active_pieces": active_pieces,
                    "high_priority_count": assigned_high,
                    "low_priority_count": assigned_low,
                })
                await self.event_bus.publish("pieces_scheduled", {"assigned": len(scored_pieces)})

            if self._is_due(self._last_bandwidth_update_at, self.config.bandwidth_interval, now):
                settings = self.engine.get_session_settings()
                tuned = self.bandwidth_optimizer.observe_and_tune(state, settings)
                self.engine.apply_session_settings(tuned)
                self._last_bandwidth_update_at = now
                
            if self._is_due(self._last_save_resume_at, self.config.autosave_resume_interval, now):
                self.engine.save_resume_data()
                self._last_save_resume_at = now
                await self.event_bus.publish("autosave_triggered")

            # Detailed loop tracking
            m = self.metrics.get_metrics()
            logger.debug("torrent_status", extra={
                "progress": round(state.progress, 2),
                "speed_kb": round(state.download_speed / 1024, 2),
                "peers": state.peers_connected,
                "avg_speed_kb": round(m.avg_download_speed / 1024, 2)
            })

    async def shutdown(self) -> None:
        logger.info("Initiating controller shutdown")
        async with self._lock:
            self.engine.save_resume_data()
            self.engine.pause_and_shutdown()
            await self.event_bus.publish("controller_shutdown")

    @staticmethod
    def _is_due(last_updated_at: float | None, interval: float, now: float) -> bool:
        return last_updated_at is None or (now - last_updated_at) >= interval
