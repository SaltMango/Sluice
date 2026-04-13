from __future__ import annotations

import time
from typing import Sequence

from engine.config import PeerConfig
from engine.models import PeerInfo, ScoredPeer
from engine.utils import normalize_linear

class PeerManager:
    """Ranks pure PeerInfo constructs strictly against config directives."""

    def __init__(self, config: PeerConfig | None = None) -> None:
        self.config = config or PeerConfig()

        total_weight = self.config.speed_weight + self.config.choke_weight + self.config.connection_weight
        if total_weight <= 0:
            raise ValueError("Peer score weights must sum to a positive value.")

        self._speed_weight = self.config.speed_weight / total_weight
        self._choke_weight = self.config.choke_weight / total_weight
        self._connection_weight = self.config.connection_weight / total_weight

    def evaluate(self, peers: Sequence[PeerInfo]) -> list[ScoredPeer]:
        if not peers:
            return []

        speeds = [p.download_speed for p in peers]
        connection_times = [p.connection_time for p in peers]

        norm_speeds = normalize_linear(speeds)
        norm_times = normalize_linear(connection_times)

        scored_peers = []
        for i, peer in enumerate(peers):
            norm_choke = 0.0 if peer.is_choked else 1.0
            
            peer_score = (
                norm_speeds[i] * self._speed_weight
                + norm_choke * self._choke_weight
                + norm_times[i] * self._connection_weight
            )

            scored_peers.append(
                ScoredPeer(
                    info=peer,
                    normalized_download_speed=norm_speeds[i],
                    normalized_choke_state=norm_choke,
                    normalized_connection_time=norm_times[i],
                    peer_score=peer_score,
                )
            )

        # Backpressure boundary: limit top peers if they exceed active request load capacity limits
        # by trimming the scored pool or passing instructions via ScoredPeer. (Here we sort them)
        sorted_peers = sorted(scored_peers, key=lambda p: p.peer_score, reverse=True)
        return sorted_peers
