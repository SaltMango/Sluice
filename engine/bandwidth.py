from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .torrent import TorrentStatus

MAX_CONNECTIONS_LIMIT = 400
MAX_CONNECTION_SPEED = 100
MAX_OUT_REQUEST_QUEUE = 1500
MAX_ALLOWED_IN_REQUEST_QUEUE = 4000
MIN_REQUEST_QUEUE_TIME = 1
DEFAULT_PEAK_SAMPLE_WINDOW = 20


@dataclass(slots=True)
class BandwidthSnapshot:
    current_speed: int
    estimated_max_bandwidth: int
    rolling_peak: int
    utilization_ratio: float
    is_underutilized: bool
    is_unstable: bool
    aggressive_mode: bool
    aggression_level: int
    settings: dict[str, int]


class BandwidthOptimizer:
    """Adapts libtorrent session settings based on observed download utilization."""

    def __init__(
        self,
        *,
        configured_max_bandwidth: int | None = None,
        peak_sample_window: int = DEFAULT_PEAK_SAMPLE_WINDOW,
        utilization_threshold: float = 0.75,
        instability_threshold: float = 0.40,
        underutilized_ticks_for_aggression: int = 2,
        backoff_cooldown_ticks: int = 2,
        max_aggression_level: int = 3,
    ) -> None:
        if configured_max_bandwidth is not None and configured_max_bandwidth <= 0:
            raise ValueError("configured_max_bandwidth must be positive when provided.")
        if peak_sample_window <= 0:
            raise ValueError("peak_sample_window must be positive.")
        if not 0 < utilization_threshold <= 1:
            raise ValueError("utilization_threshold must be between 0 and 1.")
        if not 0 < instability_threshold <= 1:
            raise ValueError("instability_threshold must be between 0 and 1.")
        if underutilized_ticks_for_aggression <= 0:
            raise ValueError("underutilized_ticks_for_aggression must be positive.")
        if backoff_cooldown_ticks < 0:
            raise ValueError("backoff_cooldown_ticks cannot be negative.")
        if max_aggression_level < 0:
            raise ValueError("max_aggression_level cannot be negative.")

        self._configured_max_bandwidth = configured_max_bandwidth
        self._speed_samples: deque[int] = deque(maxlen=peak_sample_window)
        self._utilization_threshold = utilization_threshold
        self._instability_threshold = instability_threshold
        self._underutilized_ticks_for_aggression = underutilized_ticks_for_aggression
        self._backoff_cooldown_ticks = backoff_cooldown_ticks
        self._max_aggression_level = max_aggression_level

        self._baseline_settings: dict[str, int] | None = None
        self._last_applied_settings: dict[str, int] = {}
        self._aggression_level = 0
        self._underutilized_ticks = 0
        self._cooldown_remaining = 0

    def observe(self, status: TorrentStatus, session: Any) -> BandwidthSnapshot:
        settings = self._current_settings(session)
        if self._baseline_settings is None:
            self._baseline_settings = dict(settings)
            self._last_applied_settings = self._select_bandwidth_settings(settings)

        current_speed = max(int(status.download_rate), 0)
        self._speed_samples.append(current_speed)
        rolling_peak = max(self._speed_samples, default=current_speed)
        estimated_max_bandwidth = self._estimate_max_bandwidth(rolling_peak)
        utilization_ratio = self._compute_utilization_ratio(
            current_speed, estimated_max_bandwidth
        )
        is_underutilized = (
            status.progress < 100.0
            and status.peers > 0
            and estimated_max_bandwidth > 0
            and utilization_ratio < self._utilization_threshold
        )
        is_unstable = self._is_unstable(
            current_speed=current_speed, rolling_peak=rolling_peak
        )

        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1

        if is_unstable:
            self._backoff(session)
        elif is_underutilized and self._cooldown_remaining == 0:
            self._underutilized_ticks += 1
            if self._underutilized_ticks >= self._underutilized_ticks_for_aggression:
                self._increase_aggression(session)
                self._underutilized_ticks = 0
        else:
            self._underutilized_ticks = 0

        applied_settings = (
            self._last_applied_settings or self._select_bandwidth_settings(settings)
        )
        return BandwidthSnapshot(
            current_speed=current_speed,
            estimated_max_bandwidth=estimated_max_bandwidth,
            rolling_peak=rolling_peak,
            utilization_ratio=utilization_ratio,
            is_underutilized=is_underutilized,
            is_unstable=is_unstable,
            aggressive_mode=self._aggression_level > 0,
            aggression_level=self._aggression_level,
            settings=dict(applied_settings),
        )

    def _increase_aggression(self, session: Any) -> None:
        if self._baseline_settings is None:
            return
        if self._aggression_level >= self._max_aggression_level:
            return

        self._aggression_level += 1
        tuned_settings = self._build_aggressive_settings(
            self._baseline_settings, self._aggression_level
        )
        self._apply_settings(session, tuned_settings)
        self._last_applied_settings = tuned_settings

    def _backoff(self, session: Any) -> None:
        self._underutilized_ticks = 0
        self._cooldown_remaining = self._backoff_cooldown_ticks
        if self._baseline_settings is None:
            return

        if self._aggression_level > 0:
            self._aggression_level -= 1

        tuned_settings = self._build_aggressive_settings(
            self._baseline_settings, self._aggression_level
        )
        self._apply_settings(session, tuned_settings)
        self._last_applied_settings = tuned_settings

    @staticmethod
    def _apply_settings(session: Any, settings: dict[str, int]) -> None:
        session.apply_settings(settings)

    @staticmethod
    def _select_bandwidth_settings(settings: dict[str, int]) -> dict[str, int]:
        return {
            "connections_limit": int(settings["connections_limit"]),
            "connection_speed": int(settings["connection_speed"]),
            "max_out_request_queue": int(settings["max_out_request_queue"]),
            "max_allowed_in_request_queue": int(
                settings["max_allowed_in_request_queue"]
            ),
            "request_queue_time": int(settings["request_queue_time"]),
        }

    @staticmethod
    def _build_aggressive_settings(
        baseline: dict[str, int], aggression_level: int
    ) -> dict[str, int]:
        return {
            "connections_limit": min(
                int(baseline["connections_limit"]) + aggression_level * 25,
                MAX_CONNECTIONS_LIMIT,
            ),
            "connection_speed": min(
                int(baseline["connection_speed"]) + aggression_level * 10,
                MAX_CONNECTION_SPEED,
            ),
            "max_out_request_queue": min(
                int(baseline["max_out_request_queue"]) + aggression_level * 150,
                MAX_OUT_REQUEST_QUEUE,
            ),
            "max_allowed_in_request_queue": min(
                int(baseline["max_allowed_in_request_queue"]) + aggression_level * 500,
                MAX_ALLOWED_IN_REQUEST_QUEUE,
            ),
            "request_queue_time": max(
                int(baseline["request_queue_time"]) - aggression_level,
                MIN_REQUEST_QUEUE_TIME,
            ),
        }

    def _estimate_max_bandwidth(self, rolling_peak: int) -> int:
        if self._configured_max_bandwidth is not None:
            return self._configured_max_bandwidth
        return rolling_peak

    @staticmethod
    def _compute_utilization_ratio(
        current_speed: int, estimated_max_bandwidth: int
    ) -> float:
        if estimated_max_bandwidth <= 0:
            return 0.0
        return min(max(current_speed / estimated_max_bandwidth, 0.0), 1.0)

    def _is_unstable(self, current_speed: int, rolling_peak: int) -> bool:
        if self._aggression_level == 0:
            return False
        if rolling_peak <= 0:
            return False
        return current_speed <= rolling_peak * self._instability_threshold

    @staticmethod
    def _current_settings(session: Any) -> dict[str, int]:
        settings = session.get_settings()
        return {
            key: int(value) for key, value in settings.items() if isinstance(value, int)
        }
