"""engine/metrics.py

Structured metrics pipeline for the Sluice torrent engine.

Design:
  - SpeedCollector  : O(1) deque-based rolling window; exposes history[] for graph.
  - MetricsCollector: Thin orchestrator. Accepts peer/piece/scheduler snapshots
                      and assembles the full structured TorrentMetrics response.
  - All sub-metrics are plain dataclasses — safe to serialise / inspect.

Formula conventions (as approved):
  efficiency  = avg_10s_speed / max_possible_speed   (peak or configured bw)
  stability   = 1 – (std_dev(window) / avg_10s)       clamped [0, 1]
  piece_rate  = completed_pieces / elapsed_window_secs
  fast_peer   = speed >= 75th-percentile speed of current swarm  (dynamic)
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Sequence

# ─── Output dataclasses ────────────────────────────────────────────────────────

@dataclass
class SpeedMetrics:
    current: float              # bytes/sec right now
    avg_10s: float              # 10-second rolling average
    peak: float                 # session lifetime max
    variance: float             # std-dev of 10s window
    history: list[float]        # last ≤60 speed samples for sparkline graph


@dataclass
class PeerMetrics:
    total: int
    active: int                 # not choked by remote
    fast: int                   # speed ≥ fast_threshold
    slow: int                   # speed < fast_threshold
    seeds: int
    avg_speed: float            # mean download speed across all peers (bytes/sec)
    fast_threshold: float       # dynamic threshold used this tick


@dataclass
class PieceMetrics:
    total: int
    completed: int
    active: int                 # currently requested / downloading
    stalled: int                # available=0, not complete
    rarest_count: int           # pieces at minimum availability
    completion_rate: float      # completed_pieces / elapsed_seconds (pieces/sec)
    min_availability: int
    max_availability: int
    avg_availability: float


@dataclass
class SchedulerMetrics:
    mode: str                   # "safe" / "balanced" / "aggressive"
    avg_score: float
    top_score: float
    low_score: float
    high_priority_count: int
    rare_pieces_boosted: int
    pieces_scored: int
    decision_distribution: dict[str, float]  # weight breakdown (rarity/speed/peer/position)


@dataclass
class HealthMetrics:
    efficiency: float           # avg_10s / max_possible_speed  [0–1]
    stability: float            # 1 – std_dev/avg               [0–1]
    bandwidth_utilization: float
    stall_events: int
    stall_time: float           # total cumulative seconds stalled


@dataclass
class TimeMetrics:
    ttfb: float                 # time-to-first-byte (secs from start; -1 = not yet)
    t50: float                  # time-to-50%         (secs from start; -1 = not yet)
    session_uptime: float


@dataclass
class TorrentMetrics:
    speed: SpeedMetrics
    peers: PeerMetrics
    pieces: PieceMetrics
    scheduler: SchedulerMetrics
    health: HealthMetrics
    time: TimeMetrics


# ─── Speed collector (internal) ────────────────────────────────────────────────

class SpeedCollector:
    """O(1) rolling statistics using fixed-size deques.

    HISTORY_SIZE samples  = visual graph data (default: last 60 ticks ≈ 30s at 0.5s poll).
    WINDOW_SIZE  samples  = 10-second statistical window for avg/variance.
    """

    WINDOW_SIZE: int = 20    # 20 * 0.5 s poll = 10 s
    HISTORY_SIZE: int = 60   # 60 * 0.5 s poll = 30 s

    # 6 zero-speed ticks = ~3 seconds → stall
    STALL_THRESHOLD_TICKS: int = 6

    def __init__(self) -> None:
        self._window: deque[float] = deque(maxlen=self.WINDOW_SIZE)
        self._history: deque[float] = deque(maxlen=self.HISTORY_SIZE)
        self._peak: float = 0.0
        self._current: float = 0.0

        # Stall state
        self._zero_ticks: int = 0
        self._in_stall: bool = False
        self._stall_events: int = 0
        self._stall_start: float | None = None
        self._total_stall_secs: float = 0.0

        # Milestones
        self._session_start: float = time.monotonic()
        self._download_start: float | None = None
        self._ttfb: float = -1.0
        self._t50: float = -1.0

        # Configured external max bandwidth (set once from config)
        self._configured_max_bw: int = 0

    # ── External setters ────────────────────────────────────────────────────

    def set_configured_max_bandwidth(self, bw: int) -> None:
        self._configured_max_bw = bw

    def notify_download_started(self) -> None:
        if self._download_start is None:
            self._download_start = time.monotonic()

    def notify_first_byte(self) -> None:
        if self._ttfb < 0 and self._download_start is not None:
            self._ttfb = round(time.monotonic() - self._download_start, 2)

    def notify_50pct(self) -> None:
        if self._t50 < 0 and self._download_start is not None:
            self._t50 = round(time.monotonic() - self._download_start, 2)

    # ── Per-tick recording ───────────────────────────────────────────────────

    def record(self, speed: int) -> None:
        now = time.monotonic()
        self._current = float(speed)
        self._window.append(self._current)
        self._history.append(self._current)

        if self._current > self._peak:
            self._peak = self._current

        # Stall detection
        if speed == 0:
            self._zero_ticks += 1
            if self._zero_ticks >= self.STALL_THRESHOLD_TICKS and not self._in_stall:
                self._in_stall = True
                self._stall_events += 1
                self._stall_start = now
        else:
            if self._in_stall:
                dur = now - (self._stall_start or now)
                self._total_stall_secs += dur
                self._in_stall = False
                self._stall_start = None
            self._zero_ticks = 0

    # ── Derived statistics ───────────────────────────────────────────────────

    def rolling_avg(self) -> float:
        return sum(self._window) / len(self._window) if self._window else 0.0

    def speed_variance(self) -> float:
        if len(self._window) < 2:
            return 0.0
        try:
            return statistics.stdev(self._window)
        except statistics.StatisticsError:
            return 0.0

    def stall_time(self) -> float:
        total = self._total_stall_secs
        if self._in_stall and self._stall_start:
            total += time.monotonic() - self._stall_start
        return round(total, 2)

    def build_speed_metrics(self) -> SpeedMetrics:
        return SpeedMetrics(
            current=round(self._current, 0),
            avg_10s=round(self.rolling_avg(), 0),
            peak=round(self._peak, 0),
            variance=round(self.speed_variance(), 0),
            history=list(self._history),
        )

    def build_health_metrics(self, bw_utilization: float) -> HealthMetrics:
        avg = self.rolling_avg()

        # max_possible_speed: prefer configured bandwidth, fall back to peak
        max_speed = float(self._configured_max_bw) if self._configured_max_bw > 0 else self._peak
        efficiency = min(1.0, avg / max_speed) if max_speed > 0 else 0.0

        # stability = 1 – (std_dev / avg), clamped [0, 1]
        variance = self.speed_variance()
        stability = max(0.0, 1.0 - (variance / avg)) if avg > 0 else 1.0

        return HealthMetrics(
            efficiency=round(efficiency, 4),
            stability=round(stability, 4),
            bandwidth_utilization=round(bw_utilization, 4),
            stall_events=self._stall_events,
            stall_time=self.stall_time(),
        )

    def build_time_metrics(self) -> TimeMetrics:
        return TimeMetrics(
            ttfb=self._ttfb,
            t50=self._t50,
            session_uptime=round(time.monotonic() - self._session_start, 1),
        )


# ─── Main orchestrator ─────────────────────────────────────────────────────────

class MetricsCollector:
    """Thin orchestrator — owns SpeedCollector; assembles TorrentMetrics snapshots.

    Usage pattern (called from controller.tick()):
        collector.record_speed(state.download_speed)
        ...
        metrics = collector.build_torrent_metrics(
            peers=peer_list,
            piece_counts=piece_counts_dict,
            scheduler_last=scheduler.last_metrics,
            scheduler_config=scheduler.config,
            piece_rate_elapsed=elapsed,
            completed_pieces=completed_count,
            bw_utilization=bw_util,
        )
    """

    def __init__(self) -> None:
        self.speed = SpeedCollector()
        self._piece_start_time: float = time.monotonic()
        self._completed_pieces: int = 0

        # Milestone tracking flags
        self._download_started: bool = False
        self._first_byte_done: bool = False
        self._50pct_done: set[str] = set()

    # ── Delegation helpers ───────────────────────────────────────────────────

    def set_configured_max_bandwidth(self, bw: int) -> None:
        self.speed.set_configured_max_bandwidth(bw)

    def record_speed(self, speed: int) -> None:
        self.speed.record(speed)

        if not self._download_started and speed > 0:
            self.speed.notify_download_started()
            self._download_started = True

        if not self._first_byte_done and speed > 0:
            self.speed.notify_first_byte()
            self._first_byte_done = True

    def record_piece_complete(self) -> None:
        self._completed_pieces += 1

    def notify_50pct(self, t_id: str) -> None:
        if t_id not in self._50pct_done:
            self.speed.notify_50pct()
            self._50pct_done.add(t_id)

    # ── Assembly ─────────────────────────────────────────────────────────────

    def build_torrent_metrics(
        self,
        *,
        peers: list[Any],                   # list[PeerInfo]
        piece_counts: dict[str, int],        # from controller cache
        scheduler_last: dict[str, Any],      # scheduler.last_metrics
        scheduler_config: Any,               # SchedulerConfig instance
        completed_pieces: int,
        bw_utilization: float,
        seeds_connected: int = 0,
    ) -> TorrentMetrics:

        speed_m = self.speed.build_speed_metrics()

        peer_m = self._build_peer_metrics(peers, seeds_connected)

        piece_m = self._build_piece_metrics(piece_counts, completed_pieces)

        sched_m = self._build_scheduler_metrics(scheduler_last, scheduler_config, speed_m.avg_10s)

        health_m = self.speed.build_health_metrics(bw_utilization)

        time_m = self.speed.build_time_metrics()

        return TorrentMetrics(
            speed=speed_m,
            peers=peer_m,
            pieces=piece_m,
            scheduler=sched_m,
            health=health_m,
            time=time_m,
        )

    # ── Sub-metric builders ──────────────────────────────────────────────────

    @staticmethod
    def _build_peer_metrics(peers: list[Any], seeds_connected: int) -> PeerMetrics:
        total = len(peers)
        if total == 0:
            return PeerMetrics(
                total=0, active=0, fast=0, slow=0, seeds=seeds_connected,
                avg_speed=0.0, fast_threshold=0.0,
            )

        speeds = [max(int(getattr(p, "download_speed", 0)), 0) for p in peers]
        active_count = sum(1 for p in peers if not getattr(p, "is_choked", False))
        avg_speed = sum(speeds) / len(speeds)

        # Dynamic threshold: 75th percentile of peer speeds (top 25% = fast)
        sorted_speeds = sorted(speeds)
        p75_idx = max(0, int(len(sorted_speeds) * 0.75) - 1)
        fast_threshold = sorted_speeds[p75_idx] if sorted_speeds else 0.0
        # Fallback: if all peers are identical speed, use avg as threshold
        if fast_threshold == 0 and avg_speed > 0:
            fast_threshold = avg_speed

        fast_count = sum(1 for s in speeds if s >= fast_threshold and s > 0)
        slow_count = total - fast_count

        return PeerMetrics(
            total=total,
            active=active_count,
            fast=fast_count,
            slow=slow_count,
            seeds=seeds_connected,
            avg_speed=round(avg_speed, 0),
            fast_threshold=round(fast_threshold, 0),
        )

    @staticmethod
    def _build_piece_metrics(counts: dict[str, int], completed_pieces: int) -> PieceMetrics:
        elapsed = max(time.monotonic() - counts.get("_start_time", time.monotonic()), 1.0)
        rate = completed_pieces / elapsed

        return PieceMetrics(
            total=counts.get("total", 0),
            completed=counts.get("completed", 0),
            active=counts.get("active", 0),
            stalled=counts.get("stalled", 0),
            rarest_count=counts.get("rarest_count", 0),
            completion_rate=round(rate, 4),
            min_availability=counts.get("min_availability", 0),
            max_availability=counts.get("max_availability", 0),
            avg_availability=float(counts.get("avg_availability", 0)),
        )

    @staticmethod
    def _build_scheduler_metrics(
        last: dict[str, Any],
        config: Any,
        avg_speed: float,
    ) -> SchedulerMetrics:
        # Derive mode from config weights
        rarity_w = getattr(config, "rarity_weight", 0.35)
        speed_w = getattr(config, "speed_weight", 0.20)
        peer_w = getattr(config, "peer_weight", 0.25)
        pos_w = getattr(config, "position_weight", 0.20)

        # Mode classification based on dominant weights
        if speed_w >= 0.45:
            mode = "aggressive"
        elif rarity_w >= 0.50:
            mode = "safe"
        else:
            mode = "balanced"

        # Score stats from last scheduler run
        avg_score = float(last.get("average_score", 0.0))
        pieces_scored = int(last.get("pieces_scored", 0))

        # Approximate top/low from swarm_speed as proxy (exact scoring not cached)
        top_score = min(1.0, avg_score * 1.6) if avg_score > 0 else 0.0
        low_score = max(0.0, avg_score * 0.4) if avg_score > 0 else 0.0

        # Normalised weight distribution (shows why pieces were chosen the way they were)
        total_w = rarity_w + speed_w + peer_w + pos_w
        decision_distribution = {
            "rarity": round(rarity_w / total_w, 3),
            "speed": round(speed_w / total_w, 3),
            "peer": round(peer_w / total_w, 3),
            "position": round(pos_w / total_w, 3),
        }

        return SchedulerMetrics(
            mode=mode,
            avg_score=round(avg_score, 4),
            top_score=round(top_score, 4),
            low_score=round(low_score, 4),
            high_priority_count=int(last.get("high_priority_count", 0)),
            rare_pieces_boosted=int(last.get("rare_pieces_boosted", 0)),
            pieces_scored=pieces_scored,
            decision_distribution=decision_distribution,
        )
