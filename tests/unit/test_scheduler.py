from __future__ import annotations

from types import SimpleNamespace

import pytest


class FakeTorrentFile:
    def __init__(self, piece_count: int) -> None:
        self._piece_count = piece_count

    def num_pieces(self) -> int:
        return self._piece_count


class FakeHandle:
    def __init__(
        self,
        *,
        piece_count: int,
        availability: list[int],
        peer_infos: list[object],
        completed: set[int] | None = None,
    ) -> None:
        self._torrent_file = FakeTorrentFile(piece_count)
        self._availability = availability
        self._peer_infos = peer_infos
        self._completed = completed or set()
        self.applied_priorities: list[int] | None = None

    def torrent_file(self) -> FakeTorrentFile:
        return self._torrent_file

    def piece_availability(self) -> list[int]:
        return self._availability

    def get_peer_info(self) -> list[object]:
        return self._peer_infos

    def have_piece(self, index: int) -> bool:
        return index in self._completed

    def prioritize_pieces(self, priorities: list[int]) -> None:
        self.applied_priorities = priorities


def test_scheduler_scores_pieces_and_applies_priorities(import_engine) -> None:
    scheduler_module = import_engine("engine.scheduler")
    scheduler = scheduler_module.Scheduler(
        rarity_weight=0.6,
        position_weight=0.1,
        peer_weight=0.2,
        speed_weight=0.1,
    )
    handle = FakeHandle(
        piece_count=3,
        availability=[6, 1, 3],
        peer_infos=[
            SimpleNamespace(pieces=[True, False, True], down_speed=800),
            SimpleNamespace(pieces=[False, True, False], down_speed=400),
            SimpleNamespace(pieces=[False, True, True], down_speed=600),
        ],
        completed={2},
    )

    scored = scheduler.score_pieces(handle)
    priorities = scheduler.generate_priority_list(handle)
    applied = scheduler.apply(handle)

    assert [piece.index for piece in scored] == [1, 0, 2]
    assert priorities == [1, 7, 0]
    assert applied == priorities
    assert handle.applied_priorities == priorities

    top_piece = scored[0]
    assert top_piece.norm_rarity == 1.0
    assert top_piece.norm_position == 0.5
    assert top_piece.norm_peer_availability == 1.0
    assert top_piece.norm_peer_speed == 1000 / 1400
    assert top_piece.priority == 7

    completed_piece = next(piece for piece in scored if piece.index == 2)
    assert completed_piece.is_complete is True
    assert completed_piece.score == 0.0
    assert completed_piece.priority == 0


def test_scheduler_handles_empty_and_flat_scoring_cases(import_engine) -> None:
    scheduler_module = import_engine("engine.scheduler")
    scheduler = scheduler_module.Scheduler()

    empty_handle = FakeHandle(piece_count=0, availability=[], peer_infos=[])
    assert scheduler.score_pieces(empty_handle) == []
    assert scheduler.generate_priority_list(empty_handle) == []
    assert scheduler.apply(empty_handle) == []
    assert empty_handle.applied_priorities == []

    flat_handle = FakeHandle(
        piece_count=2,
        availability=[4],
        peer_infos=[SimpleNamespace(pieces=[False], down_speed=-10)],
    )
    scored = scheduler.score_pieces(flat_handle)

    assert scheduler.generate_priority_list(flat_handle) == [1, 7]
    assert scheduler_module.Scheduler.priorities_from_scored_pieces(scored) == [1, 7]
    assert scheduler_module.Scheduler._expand_metric([9], 3) == [9, 0, 0]
    assert scheduler_module.Scheduler._collect_peer_metrics(flat_handle.get_peer_info(), 2) == ([0, 0], [0, 0])
    assert scheduler_module.Scheduler._normalize_linear([]) == []
    assert scheduler_module.Scheduler._normalize_linear([0, 0]) == [0.0, 0.0]
    assert scheduler_module.Scheduler._normalize_inverse([]) == []
    assert scheduler_module.Scheduler._normalize_inverse([5, 5]) == [1.0, 1.0]
    assert scheduler_module.Scheduler._build_position_values(0) == []
    assert scheduler_module.Scheduler._build_position_values(1) == [1.0]
    assert scheduler_module.Scheduler._build_priority_list([0.0], [True]) == [0]
    assert [piece.priority for piece in scored] == [7, 1]


def test_scheduler_rejects_invalid_weights(import_engine) -> None:
    scheduler_module = import_engine("engine.scheduler")

    with pytest.raises(ValueError, match="sum to a positive value"):
        scheduler_module.Scheduler(
            rarity_weight=0.0,
            position_weight=0.0,
            peer_weight=0.0,
            speed_weight=0.0,
        )


def test_scheduler_apply_scored_pieces(import_engine) -> None:
    scheduler_module = import_engine("engine.scheduler")
    scheduler = scheduler_module.Scheduler()

    handle = FakeHandle(
        piece_count=2,
        availability=[1, 2],
        peer_infos=[],
    )
    scored = [SimpleNamespace(index=0, priority=5), SimpleNamespace(index=1, priority=2)]

    priorities = scheduler.apply_scored_pieces(handle, scored)

    assert priorities == [5, 2]
    assert handle.applied_priorities == [5, 2]
