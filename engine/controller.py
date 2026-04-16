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
        self._last_states: dict[str, TorrentState] = {}
        
        self._last_peer_update_at: float | None = None
        self._last_scheduler_update_at: float | None = None
        self._last_bandwidth_update_at: float | None = None
        self._last_save_resume_at: float | None = None

        self._lock = asyncio.Lock()

    def start(self) -> None:
        self.engine.start_session()
        self._running = True
        self._started = True
        
        now = time.monotonic()
        self._last_save_resume_at = now
        
        logger.info("Controller loop started")
        asyncio.create_task(self.event_bus.publish("controller_started", {}))

    def stop(self) -> None:
        self._running = False

    async def run(self, poll_interval: float = 0.5) -> None:
        self.start()

        try:
            while self._running:
                await self.tick()
                
                # Completion event check
                for t_id, state in list(self._last_states.items()):
                    if state.progress >= 100.0 and getattr(state, "_did_complete", False) is False:
                        setattr(state, "_did_complete", True)
                        logger.info("Download completed natively", extra={"torrent": t_id})
                        await self.event_bus.publish("download_complete", {"state": state})
                    
                if self._running:
                    await asyncio.sleep(poll_interval)
                    
        except EngineError as e:
            logger.exception("Domain error occurred in main loop", extra={"error": str(e)})
            await self.event_bus.publish("error", {"error": str(e)})
        except asyncio.CancelledError:
            logger.info("Controller loop cancelled")
        finally:
            await self.shutdown()

    def get_all_states(self) -> dict[str, TorrentState]:
        """Safe boundary for UIs to snapshot all active states instantly."""
        return self._last_states.copy()

    def get_state(self, t_id: str) -> TorrentState | None:
        return self._last_states.get(t_id)

    async def tick(self) -> None:
        async with self._lock:
            now = time.monotonic()
            
            for t_id in self.engine.get_all_active_ids():
                try:
                    # Extract state
                    state = self.engine.get_state(t_id)
                    self._last_states[t_id] = state
                    
                    # Metrics Logging
                    self.metrics.record_speed(state.download_speed)
                    
                    # Sub-system Interval triggers
                    if self._is_due(self._last_peer_update_at, self.config.peer_interval, now):
                        peers = self.engine.get_peers(t_id, active_time=now)
                        scored_peers = self.peer_manager.evaluate(peers)
                        
                        await self.event_bus.publish("peers_updated", {
                            "torrent": t_id,
                            "total": len(peers),
                            "choked": sum(1 for p in peers if p.is_choked)
                        })

                    if self._is_due(self._last_scheduler_update_at, self.config.scheduler_interval, now):
                        pieces = self.engine.get_pieces(t_id)
                        peers = self.engine.get_peers(t_id, active_time=now)
                        
                        scored_pieces = self.scheduler.score_pieces(pieces, peers)
                        
                        # Assign bucket values
                        priorities = [0] * len(pieces)
                        for sp in scored_pieces:
                            val = sp.priority.value
                            priorities[sp.info.index] = val
                            if sp.info.is_complete:
                                self.metrics.record_piece_complete()

                        self.engine.apply_priorities(t_id, priorities)
                        
                        active_pieces = sum(1 for p in pieces if not p.is_complete and p.state in (PieceState.REQUESTED, PieceState.DOWNLOADING))
                        assigned_high = sum(1 for p in priorities if p == PriorityBucket.HIGH.value)
                        assigned_low = sum(1 for p in priorities if p == PriorityBucket.LOW.value)

                        # logging omitted to save console spam
                        await self.event_bus.publish("pieces_scheduled", {"torrent": t_id, "assigned": len(scored_pieces)})

                    if self._is_due(self._last_bandwidth_update_at, self.config.bandwidth_interval, now):
                        settings = self.engine.get_session_settings()
                        tuned = self.bandwidth_optimizer.observe_and_tune(state, settings)
                        self.engine.apply_session_settings(tuned)
                        self._last_bandwidth_update_at = now
                        
                except EngineError as e:
                    logger.warning(f"Engine iteration error on {t_id}: {e}")

            # Intercept Libtorrent Event Alerts for Async operations like save_resume_data_alerts
            if self.engine._session:
                try:
                    import libtorrent as lt
                    alerts = self.engine._session.pop_alerts()
                    for alert in alerts:
                        if type(alert).__name__ == "save_resume_data_alert":
                            t_id = str(alert.handle.info_hash())
                            path = self.engine._resume_paths.get(t_id)
                            if path:
                                try:
                                    # libtorrent v1.2+ uses write_resume_data on params
                                    data = lt.bencode(lt.write_resume_data(alert.params))
                                    with open(path, "wb") as f:
                                        f.write(data)
                                    logger.info("Successfully wrote resume block to disk", extra={"torrent": t_id})
                                except Exception as e:
                                    logger.error(f"Failed to bencode resume alert payload", extra={"error": str(e)})
                except Exception as eval_e:
                    logger.error(f"Failed handling alerts natively", extra={"error": str(eval_e)})

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

    async def shutdown(self) -> None:
        logger.info("Initiating controller shutdown")
        async with self._lock:
            self.engine.save_resume_data()
            
            if self.engine._session:
                try:
                    import libtorrent as lt
                    import asyncio
                    alerts_expected = len(self.engine._handles)
                    attempts = 0
                    while alerts_expected > 0 and attempts < 10:
                        alerts = self.engine._session.pop_alerts()
                        for alert in alerts:
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
    def _is_due(last_updated_at: float | None, interval: float, now: float) -> bool:
        return last_updated_at is None or (now - last_updated_at) >= interval
