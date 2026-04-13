from __future__ import annotations

import asyncio
from typing import Any
from types import SimpleNamespace

import pytest


class FakeHandle:
    def __init__(self) -> None:
        self.applied_priorities: list[int] | None = None

    def prioritize_pieces(self, priorities: list[int]) -> None:
        self.applied_priorities = priorities


class FakeSession:
    def __init__(self) -> None:
        self.settings = {
            "connections_limit": 200,
            "connection_speed": 30,
            "max_out_request_queue": 500,
            "max_allowed_in_request_queue": 2000,
            "request_queue_time": 3,
        }
        self.applied_settings: list[dict[str, int]] = []

    def get_settings(self) -> dict[str, int]:
        return dict(self.settings)

    def apply_settings(self, settings: dict[str, int]) -> None:
        self.applied_settings.append(dict(settings))
        self.settings.update(settings)


class FakeEngine:
    def __init__(self) -> None:
        self.started = False
        self.added_torrent: str | None = None
        self.peer_calls = 0
        self.status_calls = 0
        self.handle = FakeHandle()
        self.session = FakeSession()
        self.peer_sequences = [
            [SimpleNamespace(ip=("10.0.0.1", 6881), down_speed=300, flags=0, pieces=[True, False])],
            [SimpleNamespace(ip=("10.0.0.2", 6881), down_speed=500, flags=0, pieces=[True, True])],
            [SimpleNamespace(ip=("10.0.0.3", 6881), down_speed=700, flags=0, pieces=[False, True])],
        ]
        self.status_sequences = [
            SimpleNamespace(name="demo", progress=10.0, download_rate=100, peers=1, state="downloading"),
            SimpleNamespace(name="demo", progress=30.0, download_rate=200, peers=2, state="downloading"),
            SimpleNamespace(name="demo", progress=100.0, download_rate=0, peers=0, state="seeding"),
        ]

    def start_session(self) -> None:
        self.started = True

    def add_torrent(self, torrent_file: str) -> None:
        self.added_torrent = torrent_file

    def get_peer_info(self) -> list[object]:
        index = min(self.peer_calls, len(self.peer_sequences) - 1)
        self.peer_calls += 1
        return list(self.peer_sequences[index])

    def get_handle(self) -> FakeHandle:
        return self.handle

    def get_session(self) -> FakeSession:
        return self.session

    def get_status(self) -> object:
        index = min(self.status_calls, len(self.status_sequences) - 1)
        self.status_calls += 1
        return self.status_sequences[index]


class FakePeerManager:
    def __init__(self) -> None:
        self.calls: list[tuple[list[object], float]] = []

    def collect(self, peer_infos: list[object], now: float | None = None) -> list[object]:
        self.calls.append((list(peer_infos), 0.0 if now is None else now))
        return [SimpleNamespace(endpoint=f"peer-{len(peer_infos)}", peer_score=float(len(peer_infos)))]


class FakeScheduler:
    def __init__(self) -> None:
        self.score_calls: list[tuple[object, list[object]]] = []
        self.apply_calls: list[tuple[object, list[SimpleNamespace]]] = []

    def score_pieces(self, torrent_handle: object, peer_infos: list[object] | None = None) -> list[object]:
        peers = [] if peer_infos is None else list(peer_infos)
        self.score_calls.append((torrent_handle, peers))
        return [SimpleNamespace(index=0, priority=4), SimpleNamespace(index=1, priority=6)]

    def apply_scored_pieces(
        self, torrent_handle: Any, scored_pieces: list[SimpleNamespace]
    ) -> list[int]:
        pieces = list(scored_pieces)
        self.apply_calls.append((torrent_handle, pieces))
        priorities = [0] * len(pieces)
        for piece in pieces:
            priorities[piece.index] = piece.priority
        torrent_handle.prioritize_pieces(priorities)
        return priorities


class FakeBandwidthOptimizer:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def observe(self, status: object, session: object) -> object:
        self.calls.append((status, session))
        return SimpleNamespace(
            current_speed=getattr(status, "download_rate", 0),
            estimated_max_bandwidth=1000,
            rolling_peak=max(getattr(status, "download_rate", 0), 1),
            utilization_ratio=0.5,
            is_underutilized=False,
            is_unstable=False,
            aggressive_mode=False,
            aggression_level=0,
            settings={"connections_limit": 200},
        )


def test_controller_tick_respects_intervals_and_caches_state(import_engine) -> None:
    controller_module = import_engine("engine.controller")
    engine = FakeEngine()
    peer_manager = FakePeerManager()
    scheduler = FakeScheduler()
    bandwidth = FakeBandwidthOptimizer()
    printed: list[object] = []
    controller = controller_module.Controller(
        engine=engine,
        peer_manager=peer_manager,
        scheduler=scheduler,
        bandwidth_optimizer=bandwidth,
        stats_printer=printed.append,
    )

    controller.start("demo.torrent")

    first = controller.tick(now=0.0)
    second = controller.tick(now=0.5)
    third = controller.tick(now=1.0)
    fourth = controller.tick(now=2.0)

    assert engine.started is True
    assert engine.added_torrent == "demo.torrent"
    assert first.peers_updated is True
    assert first.scheduler_updated is True
    assert first.bandwidth_updated is True
    assert second.peers_updated is False
    assert second.scheduler_updated is False
    assert second.bandwidth_updated is False
    assert third.peers_updated is True
    assert third.scheduler_updated is False
    assert third.bandwidth_updated is True
    assert fourth.peers_updated is True
    assert fourth.scheduler_updated is True
    assert fourth.bandwidth_updated is True
    assert fourth.status.progress == 100.0
    assert fourth.priorities == [4, 6]
    assert fourth.bandwidth is not None
    assert engine.handle.applied_priorities == [4, 6]
    assert engine.session.applied_settings == []
    assert len(peer_manager.calls) == 3
    assert len(scheduler.score_calls) == 2
    assert len(scheduler.apply_calls) == 2
    assert len(bandwidth.calls) == 3
    assert len(printed) == 4
    assert controller.last_snapshot == fourth


def test_controller_tick_requires_start_and_validates_intervals(import_engine) -> None:
    controller_module = import_engine("engine.controller")
    engine = FakeEngine()

    with pytest.raises(ValueError, match="peer_interval"):
        controller_module.Controller(engine=engine, peer_interval=0.0)

    with pytest.raises(ValueError, match="scheduler_interval"):
        controller_module.Controller(engine=engine, scheduler_interval=0.0)

    with pytest.raises(ValueError, match="bandwidth_interval"):
        controller_module.Controller(engine=engine, bandwidth_interval=0.0)

    controller = controller_module.Controller(engine=engine, stats_printer=lambda _snapshot: None)

    with pytest.raises(RuntimeError, match="not been started"):
        controller.tick()

    controller.start("demo.torrent")
    controller.stop()
    assert controller._running is False
    assert controller_module.Controller._is_due(None, 1.0, 10.0) is True
    assert controller_module.Controller._is_due(9.5, 1.0, 10.0) is False
    assert controller_module.Controller._is_due(9.0, 1.0, 10.0) is True
    assert controller_module.Controller._format_speed(512) == "512.0 B/s"
    assert controller_module.Controller._format_speed(2048) == "2.0 KiB/s"
    assert controller_module.Controller._format_speed(5 * 1024 * 1024) == "5.0 MiB/s"
    assert controller_module.Controller._format_speed(3 * 1024 * 1024 * 1024) == "3.0 GiB/s"


def test_controller_run_is_async_and_stops_on_completion(import_engine) -> None:
    controller_module = import_engine("engine.controller")
    engine = FakeEngine()
    peer_manager = FakePeerManager()
    scheduler = FakeScheduler()
    bandwidth = FakeBandwidthOptimizer()
    current_time = {"value": 0.0}
    sleeps: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleeps.append(duration)
        current_time["value"] += duration

    controller = controller_module.Controller(
        engine=engine,
        peer_manager=peer_manager,
        scheduler=scheduler,
        bandwidth_optimizer=bandwidth,
        clock=lambda: current_time["value"],
        sleep_func=fake_sleep,
        stats_printer=lambda _snapshot: None,
    )

    snapshot = asyncio.run(controller.run("demo.torrent", poll_interval=1.0))

    assert snapshot is not None
    assert snapshot.status.progress == 100.0
    assert sleeps == [1.0, 1.0]
    assert controller._running is False


def test_controller_run_validates_arguments(import_engine) -> None:
    controller_module = import_engine("engine.controller")
    controller = controller_module.Controller(engine=FakeEngine(), stats_printer=lambda _snapshot: None)

    with pytest.raises(ValueError, match="poll_interval"):
        asyncio.run(controller.run("demo.torrent", poll_interval=0.0))

    with pytest.raises(ValueError, match="max_iterations"):
        asyncio.run(controller.run("demo.torrent", max_iterations=0))


def test_controller_uses_cached_peers_for_scheduler_only_tick(import_engine) -> None:
    controller_module = import_engine("engine.controller")
    engine = FakeEngine()
    peer_manager = FakePeerManager()
    scheduler = FakeScheduler()
    bandwidth = FakeBandwidthOptimizer()
    controller = controller_module.Controller(
        engine=engine,
        peer_manager=peer_manager,
        scheduler=scheduler,
        bandwidth_optimizer=bandwidth,
        peer_interval=10.0,
        scheduler_interval=2.0,
        bandwidth_interval=10.0,
        stats_printer=lambda _snapshot: None,
    )

    controller.start("demo.torrent")
    controller.tick(now=0.0)
    scheduler_only = controller.tick(now=2.0)

    assert scheduler_only.peers_updated is False
    assert scheduler_only.scheduler_updated is True
    assert scheduler_only.bandwidth_updated is False
    assert len(peer_manager.calls) == 1
    assert len(scheduler.score_calls) == 2
    assert engine.peer_calls == 1


def test_controller_run_honors_max_iterations(import_engine) -> None:
    controller_module = import_engine("engine.controller")
    engine = FakeEngine()
    engine.status_sequences = [
        SimpleNamespace(name="demo", progress=10.0, download_rate=100, peers=1, state="downloading"),
        SimpleNamespace(name="demo", progress=20.0, download_rate=100, peers=1, state="downloading"),
    ]
    current_time = {"value": 0.0}
    sleeps: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleeps.append(duration)
        current_time["value"] += duration

    controller = controller_module.Controller(
        engine=engine,
        scheduler=FakeScheduler(),
        bandwidth_optimizer=FakeBandwidthOptimizer(),
        clock=lambda: current_time["value"],
        sleep_func=fake_sleep,
        stats_printer=lambda _snapshot: None,
    )

    snapshot = asyncio.run(controller.run("demo.torrent", poll_interval=0.5, max_iterations=1))

    assert snapshot is not None
    assert snapshot.iteration == 1
    assert snapshot.status.progress == 10.0
    assert sleeps == []
    assert controller._running is False


def test_controller_default_stats_printer_outputs_line(
    import_engine, capsys: pytest.CaptureFixture[str]
) -> None:
    controller_module = import_engine("engine.controller")
    controller = controller_module.Controller(engine=FakeEngine())
    snapshot = controller_module.ControllerSnapshot(
        iteration=1,
        status=SimpleNamespace(progress=42.0, download_rate=2048, peers=3),
        peers=[SimpleNamespace()],
        piece_scores=[],
        priorities=[4, 6],
        bandwidth=SimpleNamespace(aggressive_mode=True),
        peers_updated=True,
        scheduler_updated=True,
        bandwidth_updated=True,
    )

    controller._default_stats_printer(snapshot)

    output = capsys.readouterr().out
    assert "Progress:  42.00%" in output
    assert "Download:    2.0 KiB/s" in output
    assert "Peers:   3" in output
    assert "Ranked:   1" in output
    assert "Scheduled:   2" in output
    assert "Mode: aggressive" in output
