from __future__ import annotations

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
        peer_speed_values = normalize_linear(peer_speed)

        raw_scores: list[float] = []
        for i, p in enumerate(pieces):
            if p.is_complete or p.state == PieceState.AVAILABLE == False:
                raw_scores.append(0.0)
                continue

            raw_scores.append(
                rarity_values[i] * self._rarity_weight
                + position_values[i] * self._position_weight
                + peer_availability_values[i] * self._peer_weight
                + peer_speed_values[i] * self._speed_weight
            )

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

        buckets = []
        for i, piece in enumerate(pieces):
            if piece.is_complete or piece.state == PieceState.COMPLETE:
                buckets.append(PriorityBucket.IGNORE)
                continue
                
            score = scores[i]
            
            # Guardrail: Guarantee Absolute Rarest are protected.
            if self.config.min_rarest_pieces_always_downloaded and piece.availability <= min_availability + 1:
                buckets.append(PriorityBucket.HIGH)
                continue

            if maximum == minimum:
                buckets.append(PriorityBucket.DEFAULT)
                continue

            norm = (score - minimum) / (maximum - minimum)
            if norm >= 0.75:
                buckets.append(PriorityBucket.HIGH)
            elif norm >= 0.40:
                buckets.append(PriorityBucket.MEDIUM)
            elif norm >= 0.15:
                buckets.append(PriorityBucket.DEFAULT)
            else:
                buckets.append(PriorityBucket.LOW)

        return buckets
