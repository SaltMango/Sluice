from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


DEFAULT_PIECE_PRIORITY = 4
MAX_PIECE_PRIORITY = 7
MIN_ACTIVE_PIECE_PRIORITY = 1


@dataclass(slots=True)
class PieceScore:
    index: int
    availability: int
    peer_availability: int
    peer_speed: int
    is_complete: bool
    norm_rarity: float
    norm_position: float
    norm_peer_availability: float
    norm_peer_speed: float
    score: float
    priority: int


class Scheduler:
    """Scores pieces and applies libtorrent piece priorities."""

    def __init__(
        self,
        rarity_weight: float = 0.35,
        position_weight: float = 0.20,
        peer_weight: float = 0.25,
        speed_weight: float = 0.20,
    ) -> None:
        total_weight = rarity_weight + position_weight + peer_weight + speed_weight
        if total_weight <= 0:
            raise ValueError("Scheduler weights must sum to a positive value.")

        self._rarity_weight = rarity_weight / total_weight
        self._position_weight = position_weight / total_weight
        self._peer_weight = peer_weight / total_weight
        self._speed_weight = speed_weight / total_weight

    def score_pieces(self, torrent_handle: Any, peer_infos: Sequence[Any] | None = None) -> list[PieceScore]:
        piece_count = self._piece_count(torrent_handle)
        if piece_count == 0:
            return []

        availability = self._expand_metric(
            values=list(torrent_handle.piece_availability()),
            size=piece_count,
        )
        if peer_infos is None:
            peer_infos = list(torrent_handle.get_peer_info())

        peer_availability, peer_speed = self._collect_peer_metrics(peer_infos=peer_infos, piece_count=piece_count)

        rarity_values = self._normalize_inverse(availability)
        position_values = self._build_position_values(piece_count)
        peer_availability_values = self._normalize_linear(peer_availability)
        peer_speed_values = self._normalize_linear(peer_speed)

        raw_scores: list[float] = []
        complete_flags = [bool(torrent_handle.have_piece(index)) for index in range(piece_count)]

        for index in range(piece_count):
            if complete_flags[index]:
                raw_scores.append(0.0)
                continue

            raw_scores.append(
                rarity_values[index] * self._rarity_weight
                + position_values[index] * self._position_weight
                + peer_availability_values[index] * self._peer_weight
                + peer_speed_values[index] * self._speed_weight
            )

        priorities = self._build_priority_list(raw_scores=raw_scores, complete_flags=complete_flags)

        scored_pieces = [
            PieceScore(
                index=index,
                availability=availability[index],
                peer_availability=peer_availability[index],
                peer_speed=peer_speed[index],
                is_complete=complete_flags[index],
                norm_rarity=rarity_values[index],
                norm_position=position_values[index],
                norm_peer_availability=peer_availability_values[index],
                norm_peer_speed=peer_speed_values[index],
                score=raw_scores[index],
                priority=priorities[index],
            )
            for index in range(piece_count)
        ]
        return sorted(scored_pieces, key=lambda piece: (piece.priority, piece.score), reverse=True)

    def generate_priority_list(
        self,
        torrent_handle: Any,
        peer_infos: Sequence[Any] | None = None,
    ) -> list[int]:
        scored_pieces = self.score_pieces(torrent_handle=torrent_handle, peer_infos=peer_infos)
        return self.priorities_from_scored_pieces(scored_pieces)

    def apply(self, torrent_handle: Any, peer_infos: Sequence[Any] | None = None) -> list[int]:
        priorities = self.generate_priority_list(torrent_handle=torrent_handle, peer_infos=peer_infos)
        torrent_handle.prioritize_pieces(priorities)
        return priorities

    def apply_scored_pieces(self, torrent_handle: Any, scored_pieces: Sequence[PieceScore]) -> list[int]:
        priorities = self.priorities_from_scored_pieces(scored_pieces)
        torrent_handle.prioritize_pieces(priorities)
        return priorities

    @staticmethod
    def _piece_count(torrent_handle: Any) -> int:
        return int(torrent_handle.torrent_file().num_pieces())

    @staticmethod
    def priorities_from_scored_pieces(scored_pieces: Sequence[PieceScore]) -> list[int]:
        priorities = [0] * len(scored_pieces)
        for piece in scored_pieces:
            priorities[piece.index] = piece.priority
        return priorities

    @staticmethod
    def _expand_metric(values: Sequence[int], size: int) -> list[int]:
        metric = [0] * size
        for index, value in enumerate(values[:size]):
            metric[index] = int(value)
        return metric

    @staticmethod
    def _collect_peer_metrics(peer_infos: Sequence[Any], piece_count: int) -> tuple[list[int], list[int]]:
        peer_availability = [0] * piece_count
        peer_speed = [0] * piece_count

        for peer in peer_infos:
            peer_pieces = list(getattr(peer, "pieces", []))
            speed = max(int(getattr(peer, "down_speed", 0)), 0)

            for index, has_piece in enumerate(peer_pieces[:piece_count]):
                if not has_piece:
                    continue

                peer_availability[index] += 1
                peer_speed[index] += speed

        return peer_availability, peer_speed

    @staticmethod
    def _normalize_linear(values: Sequence[int]) -> list[float]:
        if not values:
            return []

        upper_bound = max(values)
        if upper_bound <= 0:
            return [0.0] * len(values)

        return [min(max(value / upper_bound, 0.0), 1.0) for value in values]

    @staticmethod
    def _normalize_inverse(values: Sequence[int]) -> list[float]:
        if not values:
            return []

        minimum = min(values)
        maximum = max(values)
        if maximum == minimum:
            return [1.0] * len(values)

        span = maximum - minimum
        return [(maximum - value) / span for value in values]

    @staticmethod
    def _build_position_values(piece_count: int) -> list[float]:
        if piece_count == 0:
            return []
        if piece_count == 1:
            return [1.0]

        divisor = piece_count - 1
        return [1.0 - (index / divisor) for index in range(piece_count)]

    @staticmethod
    def _build_priority_list(raw_scores: Sequence[float], complete_flags: Sequence[bool]) -> list[int]:
        incomplete_scores = [score for score, is_complete in zip(raw_scores, complete_flags) if not is_complete]
        if not incomplete_scores:
            return [0 if is_complete else DEFAULT_PIECE_PRIORITY for is_complete in complete_flags]

        minimum = min(incomplete_scores)
        maximum = max(incomplete_scores)

        priorities: list[int] = []
        for score, is_complete in zip(raw_scores, complete_flags):
            if is_complete:
                priorities.append(0)
                continue

            if maximum == minimum:
                priorities.append(DEFAULT_PIECE_PRIORITY)
                continue

            normalized_score = (score - minimum) / (maximum - minimum)
            priority = MIN_ACTIVE_PIECE_PRIORITY + round(
                normalized_score * (MAX_PIECE_PRIORITY - MIN_ACTIVE_PIECE_PRIORITY)
            )
            priorities.append(priority)

        return priorities
