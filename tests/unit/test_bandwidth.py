from __future__ import annotations

from types import SimpleNamespace

import pytest


class FakeSession:
    def __init__(self, settings: dict[str, int]) -> None:
        self.settings = dict(settings)
        self.applied_settings: list[dict[str, int]] = []

    def get_settings(self) -> dict[str, int]:
        return dict(self.settings)

    def apply_settings(self, settings: dict[str, int]) -> None:
        self.applied_settings.append(dict(settings))
        self.settings.update(settings)


def make_status(progress: float, download_rate: int, peers: int) -> SimpleNamespace:
    return SimpleNamespace(
        name="demo",
        progress=progress,
        download_rate=download_rate,
        peers=peers,
        state="downloading",
    )


def test_bandwidth_optimizer_tracks_peak_and_increases_aggression(import_engine) -> None:
    bandwidth_module = import_engine("engine.bandwidth")
    session = FakeSession(
        {
            "connections_limit": 200,
            "connection_speed": 30,
            "max_out_request_queue": 500,
            "max_allowed_in_request_queue": 2000,
            "request_queue_time": 3,
        }
    )
    optimizer = bandwidth_module.BandwidthOptimizer(
        configured_max_bandwidth=1000,
        underutilized_ticks_for_aggression=2,
    )

    first = optimizer.observe(make_status(progress=10.0, download_rate=400, peers=5), session)
    second = optimizer.observe(make_status(progress=20.0, download_rate=450, peers=5), session)

    assert first.estimated_max_bandwidth == 1000
    assert first.utilization_ratio == 0.4
    assert first.is_underutilized is True
    assert first.aggressive_mode is False
    assert second.aggressive_mode is True
    assert second.aggression_level == 1
    assert second.settings == {
        "connections_limit": 225,
        "connection_speed": 40,
        "max_out_request_queue": 650,
        "max_allowed_in_request_queue": 2500,
        "request_queue_time": 2,
    }
    assert session.applied_settings[-1] == second.settings


def test_bandwidth_optimizer_uses_rolling_peak_and_backs_off(import_engine) -> None:
    bandwidth_module = import_engine("engine.bandwidth")
    session = FakeSession(
        {
            "connections_limit": 390,
            "connection_speed": 95,
            "max_out_request_queue": 1450,
            "max_allowed_in_request_queue": 3900,
            "request_queue_time": 2,
        }
    )
    optimizer = bandwidth_module.BandwidthOptimizer(
        underutilized_ticks_for_aggression=1,
        backoff_cooldown_ticks=2,
        max_aggression_level=3,
    )

    baseline = optimizer.observe(make_status(progress=10.0, download_rate=200, peers=4), session)
    aggressive = optimizer.observe(make_status(progress=20.0, download_rate=100, peers=4), session)
    unstable = optimizer.observe(make_status(progress=30.0, download_rate=50, peers=4), session)
    cooling = optimizer.observe(make_status(progress=40.0, download_rate=150, peers=4), session)

    assert baseline.rolling_peak == 200
    assert baseline.estimated_max_bandwidth == 200
    assert aggressive.aggression_level == 1
    assert optimizer._aggression_level == 0
    assert unstable.is_unstable is True
    assert cooling.is_underutilized is False
    assert optimizer._cooldown_remaining == 1

    optimizer._aggression_level = 2
    backed_off = optimizer.observe(make_status(progress=50.0, download_rate=40, peers=4), session)

    assert backed_off.is_unstable is True
    assert backed_off.aggressive_mode is True
    assert backed_off.aggression_level == 1
    assert optimizer._cooldown_remaining == 2
    assert session.applied_settings[-1]["connections_limit"] == 400
    assert session.applied_settings[-1]["request_queue_time"] == 1


def test_bandwidth_optimizer_helpers_and_validation(import_engine) -> None:
    bandwidth_module = import_engine("engine.bandwidth")

    with pytest.raises(ValueError, match="configured_max_bandwidth"):
        bandwidth_module.BandwidthOptimizer(configured_max_bandwidth=0)
    with pytest.raises(ValueError, match="peak_sample_window"):
        bandwidth_module.BandwidthOptimizer(peak_sample_window=0)
    with pytest.raises(ValueError, match="utilization_threshold"):
        bandwidth_module.BandwidthOptimizer(utilization_threshold=0.0)
    with pytest.raises(ValueError, match="instability_threshold"):
        bandwidth_module.BandwidthOptimizer(instability_threshold=0.0)
    with pytest.raises(ValueError, match="underutilized_ticks_for_aggression"):
        bandwidth_module.BandwidthOptimizer(underutilized_ticks_for_aggression=0)
    with pytest.raises(ValueError, match="backoff_cooldown_ticks"):
        bandwidth_module.BandwidthOptimizer(backoff_cooldown_ticks=-1)
    with pytest.raises(ValueError, match="max_aggression_level"):
        bandwidth_module.BandwidthOptimizer(max_aggression_level=-1)

    session = FakeSession(
        {
            "connections_limit": 200,
            "connection_speed": 30,
            "max_out_request_queue": 500,
            "max_allowed_in_request_queue": 2000,
            "request_queue_time": 3,
            "ignore_me": "not-an-int",  # type: ignore[dict-item]
        }
    )
    optimizer = bandwidth_module.BandwidthOptimizer(max_aggression_level=0)

    selected = bandwidth_module.BandwidthOptimizer._select_bandwidth_settings(session.get_settings())
    built = bandwidth_module.BandwidthOptimizer._build_aggressive_settings(selected, aggression_level=10)
    bandwidth_module.BandwidthOptimizer._apply_settings(session, selected)
    current = bandwidth_module.BandwidthOptimizer._current_settings(session)

    assert built == {
        "connections_limit": 400,
        "connection_speed": 100,
        "max_out_request_queue": 1500,
        "max_allowed_in_request_queue": 4000,
        "request_queue_time": 1,
    }
    assert current["connections_limit"] == 200
    assert optimizer._estimate_max_bandwidth(rolling_peak=1234) == 1234
    assert bandwidth_module.BandwidthOptimizer._compute_utilization_ratio(100, 0) == 0.0
    assert bandwidth_module.BandwidthOptimizer._compute_utilization_ratio(500, 1000) == 0.5
    optimizer._aggression_level = 1
    assert optimizer._is_unstable(current_speed=100, rolling_peak=0) is False
    optimizer._aggression_level = 0
    no_baseline = bandwidth_module.BandwidthOptimizer()
    no_baseline._increase_aggression(session)
    no_baseline._backoff(session)
    optimizer._baseline_settings = selected
    optimizer._aggression_level = 0
    optimizer._increase_aggression(session)
    assert optimizer._aggression_level == 0
    assert optimizer.observe(make_status(progress=100.0, download_rate=0, peers=0), session).is_underutilized is False
