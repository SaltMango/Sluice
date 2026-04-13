from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from engine.config import BandwidthConfig
from engine.logger import get_logger

if TYPE_CHECKING:
    from engine.models import TorrentState

logger = get_logger(__name__)

class BandwidthOptimizer:
    """Adapts libtorrent session settings based on observed download utilization via pure State tracking."""

    def __init__(self, config: BandwidthConfig | None = None) -> None:
        self.config = config or BandwidthConfig()
        
        self._speed_samples: deque[int] = deque(maxlen=self.config.peak_sample_window)
        
        self._baseline_settings: dict[str, int] | None = None
        self._last_applied_settings: dict[str, int] = {}
        self._aggression_level = 0
        self._underutilized_ticks = 0
        self._cooldown_remaining = 0

    def observe_and_tune(self, state: TorrentState, session_settings: dict[str, int]) -> dict[str, int]:
        """Observes the domain state and returns tuned session setting overrides."""
        if self._baseline_settings is None:
            self._baseline_settings = dict(session_settings)
            self._last_applied_settings = self._select_bandwidth_settings(session_settings)

        current_speed = max(int(state.download_speed), 0)
        self._speed_samples.append(current_speed)
        
        rolling_peak = max(self._speed_samples, default=current_speed)
        estimated_max_bandwidth = self._estimate_max_bandwidth(rolling_peak)
        utilization_ratio = self._compute_utilization_ratio(current_speed, estimated_max_bandwidth)
        
        is_underutilized = (
            state.progress < 100.0
            and state.peers_connected > 0
            and estimated_max_bandwidth > 0
            and utilization_ratio < self.config.utilization_threshold
        )
        is_unstable = self._is_unstable(current_speed=current_speed, rolling_peak=rolling_peak)

        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1

        if is_unstable:
            self._backoff()
        elif is_underutilized and self._cooldown_remaining == 0:
            self._underutilized_ticks += 1
            if self._underutilized_ticks >= self.config.underutilized_ticks_for_aggression:
                self._increase_aggression()
                self._underutilized_ticks = 0
        else:
            self._underutilized_ticks = 0

        applied_settings = self._last_applied_settings or self._select_bandwidth_settings(session_settings)
        return applied_settings

    def _increase_aggression(self) -> None:
        if self._baseline_settings is None:
            return
        if self._aggression_level >= self.config.max_aggression_level:
            return

        self._aggression_level += 1
        logger.info("Bandwidth aggression increased", extra={"level": self._aggression_level})
        
        tuned_settings = self._build_aggressive_settings(
            self._baseline_settings, self._aggression_level
        )
        self._last_applied_settings = tuned_settings

    def _backoff(self) -> None:
        self._underutilized_ticks = 0
        self._cooldown_remaining = self.config.backoff_cooldown_ticks
        if self._baseline_settings is None:
            return

        if self._aggression_level > 0:
            self._aggression_level -= 1
            logger.info("Bandwidth backoff triggered", extra={"level": self._aggression_level})

        tuned_settings = self._build_aggressive_settings(
            self._baseline_settings, self._aggression_level
        )
        self._last_applied_settings = tuned_settings

    @staticmethod
    def _select_bandwidth_settings(settings: dict[str, int]) -> dict[str, int]:
        # Filter down into subset we actually care to tweak
        return {
            "connections_limit": int(settings.get("connections_limit", 200)),
            "connection_speed": int(settings.get("connection_speed", 20)),
            "max_out_request_queue": int(settings.get("max_out_request_queue", 500)),
            "max_allowed_in_request_queue": int(settings.get("max_allowed_in_request_queue", 2000)),
            "request_queue_time": int(settings.get("request_queue_time", 3)),
        }

    @staticmethod
    def _build_aggressive_settings(baseline: dict[str, int], aggression_level: int) -> dict[str, int]:
        return {
            "connections_limit": min(
                int(baseline.get("connections_limit", 200)) + aggression_level * 25,
                400,
            ),
            "connection_speed": min(
                int(baseline.get("connection_speed", 20)) + aggression_level * 10,
                100,
            ),
            "max_out_request_queue": min(
                int(baseline.get("max_out_request_queue", 500)) + aggression_level * 150,
                1500,
            ),
            "max_allowed_in_request_queue": min(
                int(baseline.get("max_allowed_in_request_queue", 2000)) + aggression_level * 500,
                4000,
            ),
            "request_queue_time": max(
                int(baseline.get("request_queue_time", 3)) - aggression_level,
                1,
            ),
        }

    def _estimate_max_bandwidth(self, rolling_peak: int) -> int:
        if self.config.configured_max_bandwidth is not None:
            return self.config.configured_max_bandwidth
        return rolling_peak

    @staticmethod
    def _compute_utilization_ratio(current_speed: int, estimated_max_bandwidth: int) -> float:
        if estimated_max_bandwidth <= 0:
            return 0.0
        return min(max(current_speed / estimated_max_bandwidth, 0.0), 1.0)

    def _is_unstable(self, current_speed: int, rolling_peak: int) -> bool:
        if self._aggression_level == 0:
            return False
        if rolling_peak <= 0:
            return False
        return current_speed <= rolling_peak * self.config.instability_threshold
