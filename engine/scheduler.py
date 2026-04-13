from __future__ import annotations

import math
import random
from typing import Sequence

from engine.config import SchedulerConfig
from engine.models import PieceInfo, PeerInfo, PieceScore, PriorityBucket, PieceState
from engine.utils import normalize_linear, normalize_inverse

class Scheduler:
    """Scores domain pieces explicitly using configurable constraints and dampening logic."""

    def __init__(self, config: SchedulerConfig | None = None) -> None:
        self.config = config or SchedulerConfig()

        total_weight = (
            self.config.rarity_weight
            + self.config.position_weight
            + self.config.peer_weight
            + self.config.speed_weight
        )
        if total_weight <= 0:
            raise ValueError("Scheduler weights must sum to a positive value")

        self._rarity_weight = self.config.rarity_weight / total_weight
        self._position_weight = self.config.position_weight / total_weight
        self._peer_weight = self.config.peer_weight / total_weight
        self._speed_weight = self.config.speed_weight / total_weight
        
        self._random = random.Random(self.config.seed)
        self._ticks = 0
        self._last_priorities: list[PieceScore] = []
        self.last_metrics: dict[str, float | int] = {}

    def score_pieces(self, pieces: Sequence[PieceInfo], peers: Sequence[PeerInfo]) -> list[PieceScore]:
        piece_count = len(pieces)
        if piece_count == 0:
            return []

        self._ticks += 1
        
        # Stability Damping
        if self._last_priorities and self._ticks % max(1, self.config.min_cycles_before_reprioritize) != 0:
            return self._last_priorities
            
        peer_availability = [0] * piece_count
        peer_speed = [0] * piece_count

        for peer in peers:
            speed = max(peer.download_speed, 0)
            for i, has_piece in enumerate(peer.pieces[:piece_count]):
                if has_piece:
                    peer_availability[i] += 1
                    peer_speed[i] += speed

        availabilities = [p.availability for p in pieces]
        
        # Deterministic noise for resolving pure ties
        if self.config.seed is not None:
             noise = [self._random.uniform(0.000, 0.001) for _ in range(piece_count)]
        else:
             noise = [0.0] * piece_count

        rarity_values = [v + n for v, n in zip(normalize_inverse(availabilities), noise)]
        position_values = self._build_position_values(piece_count)
        peer_availability_values = normalize_linear(peer_availability)
        # Apply sub-linear scaling to peer speed
        peer_speed_scaled = [math.sqrt(s) for s in peer_speed]
        peer_speed_values = normalize_linear(peer_speed_scaled)

        total_speed = sum(max(p.download_speed, 0) for p in peers)
        self.last_metrics = {
            "swarm_speed_computed": total_speed,
            "pieces_scored": 0,
            "rare_pieces_boosted": 0,
            "high_priority_count": 0,
            "average_score": 0.0,
        }

        # Dynamically balance speed weight in high bandwidth environments
        current_speed_weight = self._speed_weight
        if total_speed > 10 * 1024 * 1024:  # > 10 MB/s
            current_speed_weight *= 1.2

        raw_scores: list[float] = []
        for i, p in enumerate(pieces):
            if p.is_complete or p.state != PieceState.AVAILABLE:
                raw_scores.append(0.0)
                continue

            self.last_metrics["pieces_scored"] += 1
            raw_scores.append(
                rarity_values[i] * self._rarity_weight
                + position_values[i] * self._position_weight
                + peer_availability_values[i] * self._peer_weight
                + peer_speed_values[i] * current_speed_weight
            )

        pieces_scored = self.last_metrics["pieces_scored"]
        # Cast required for strict typing checks because dict is mixed values
        assert isinstance(pieces_scored, int)
        if pieces_scored > 0:
            self.last_metrics["average_score"] = float(sum(raw_scores) / pieces_scored)

        priorities = self._build_priority_buckets(raw_scores, pieces)

        scored_pieces = [
            PieceScore(
                info=pieces[i],
                peer_availability=peer_availability[i],
                peer_speed=peer_speed[i],
                score=raw_scores[i],
                priority=priorities[i],
            )
            for i in range(piece_count)
        ]
        
        sorted_pieces = sorted(scored_pieces, key=lambda p: (p.priority.value, p.score), reverse=True)
        self._last_priorities = sorted_pieces
        return sorted_pieces

    def _build_position_values(self, piece_count: int) -> list[float]:
        if piece_count == 0:
            return []
        if piece_count == 1:
            return [1.0]

        divisor = piece_count - 1
        return [1.0 - (index / divisor) for index in range(piece_count)]

    def _build_priority_buckets(self, scores: Sequence[float], pieces: Sequence[PieceInfo]) -> list[PriorityBucket]:
        incomplete_scores = [s for i, s in enumerate(scores) if not pieces[i].is_complete and pieces[i].state != PieceState.COMPLETE]
        
        if not incomplete_scores:
            return [PriorityBucket.IGNORE if p.is_complete else PriorityBucket.DEFAULT for p in pieces]

        minimum = min(incomplete_scores)
        maximum = max(incomplete_scores)
        
        # Calculate availability for rarest pieces
        min_availability = min([p.availability for p in pieces if not p.is_complete], default=1)

        # Determine guardrail limits to prevent rare-piece starvation from flooding HIGH priority
        max_rarest_boost = int(len(pieces) * self.config.rarest_bandwidth_guarantee_percent)
        rarest_boosted_count = 0

        # Percentile thresholds: sort incomplete scores to find dynamic distribution
        sorted_scores = sorted(incomplete_scores)
        n = len(sorted_scores)
        
        # Dynamic Percentiles: Top 15% HIGH, next 25% MEDIUM (top 40%), next 45% DEFAULT (top 85%), rest LOW
        high_thresh = sorted_scores[max(0, int(n * 0.85))] if n > 0 else 0.0
        medium_thresh = sorted_scores[max(0, int(n * 0.60))] if n > 0 else 0.0
        default_thresh = sorted_scores[max(0, int(n * 0.15))] if n > 0 else 0.0

        buckets = []
        high_count = 0
        for i, piece in enumerate(pieces):
            if piece.is_complete or piece.state == PieceState.COMPLETE:
                buckets.append(PriorityBucket.IGNORE)
                continue
                
            score = scores[i]
            
            # Guardrail: Guarantee Absolute Rarest are protected up to a bandwidth capacity limit.
            if self.config.min_rarest_pieces_always_downloaded and piece.availability <= min_availability + 1:
                if rarest_boosted_count < max_rarest_boost:
                    buckets.append(PriorityBucket.HIGH)
                    rarest_boosted_count += 1
                    high_count += 1
                    continue

            if maximum == minimum:
                buckets.append(PriorityBucket.DEFAULT)
                continue

            if score >= high_thresh:
                buckets.append(PriorityBucket.HIGH)
                high_count += 1
            elif score >= medium_thresh:
                buckets.append(PriorityBucket.MEDIUM)
            elif score >= default_thresh:
                buckets.append(PriorityBucket.DEFAULT)
            else:
                buckets.append(PriorityBucket.LOW)

        self.last_metrics["rare_pieces_boosted"] = rarest_boosted_count
        self.last_metrics["high_priority_count"] = high_count

        return buckets
