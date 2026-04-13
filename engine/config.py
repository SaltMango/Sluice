from dataclasses import dataclass

@dataclass
class SchedulerConfig:
    rarity_weight: float = 0.35
    position_weight: float = 0.20
    peer_weight: float = 0.25
    speed_weight: float = 0.20
    # Guardrail: Guaranty this much priority weight bandwidth to absolute rarest pieces.
    min_rarest_pieces_always_downloaded: bool = True
    rarest_bandwidth_guarantee_percent: float = 0.25
    # Damping guardrail
    min_cycles_before_reprioritize: int = 3
    # Deterministic testing seed
    seed: int | None = None

@dataclass
class PeerConfig:
    speed_weight: float = 0.6
    choke_weight: float = 0.25
    connection_weight: float = 0.15
    # Overload limits
    max_active_requests_per_peer: int = 15
    max_global_requests: int = 1500

@dataclass
class BandwidthConfig:
    configured_max_bandwidth: int | None = None
    peak_sample_window: int = 20
    utilization_threshold: float = 0.75
    instability_threshold: float = 0.40
    underutilized_ticks_for_aggression: int = 2
    backoff_cooldown_ticks: int = 2
    max_aggression_level: int = 3

from dataclasses import dataclass, field

@dataclass
class EngineConfig:
    peer_interval: float = 1.0
    scheduler_interval: float = 2.0
    bandwidth_interval: float = 1.0
    autosave_resume_interval: float = 60.0
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    peers: PeerConfig = field(default_factory=PeerConfig)
    bandwidth: BandwidthConfig = field(default_factory=BandwidthConfig)
