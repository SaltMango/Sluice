from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_peer_manager_collects_scores_and_tracks_connection_time(
    import_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    peers_module = import_engine("engine.peers")
    monkeypatch.setattr(peers_module.time, "monotonic", lambda: 100.0)

    manager = peers_module.PeerManager()
    initial = manager.collect(
        [
            SimpleNamespace(ip=("10.0.0.1", 6881), client="fast", down_speed=1000, flags=0),
            SimpleNamespace(
                ip=("10.0.0.2", 6881),
                client="slow",
                down_speed=250,
                flags=peers_module.lt.peer_info.remote_choked,
            ),
        ]
    )

    assert [peer.endpoint for peer in initial] == ["10.0.0.1:6881", "10.0.0.2:6881"]
    assert initial[0].peer_score > initial[1].peer_score
    assert initial[0].normalized_download_speed == 1.0
    assert initial[0].normalized_choke_state == 1.0
    assert initial[1].normalized_choke_state == 0.0
    assert initial[0].connection_time == 0.0

    follow_up = manager.collect(
        [SimpleNamespace(ip=("10.0.0.1", 6881), client="fast", down_speed=500, flags=0)],
        now=112.0,
    )

    assert len(follow_up) == 1
    assert follow_up[0].connection_time == 12.0
    assert manager._first_seen_at == {"10.0.0.1:6881": 100.0}


def test_peer_manager_collect_from_handle_and_helper_paths(import_engine) -> None:
    peers_module = import_engine("engine.peers")
    manager = peers_module.PeerManager()

    handle = SimpleNamespace(
        get_peer_info=lambda: [
            SimpleNamespace(ip="10.0.0.3:51413", client=None, down_speed=-5, flags=0),
            SimpleNamespace(ip=None, flags=0),
        ]
    )
    scored = manager.collect_from_handle(handle, now=50.0)

    assert [peer.endpoint for peer in scored] == ["10.0.0.3:51413", "unknown"]
    assert all(peer.download_speed == 0 for peer in scored)
    assert all(peer.normalized_connection_time == 0.0 for peer in scored)
    assert peers_module.PeerManager._normalize(10.0, 0.0) == 0.0
    assert peers_module.PeerManager._normalize(12.0, 6.0) == 1.0
    assert peers_module.PeerManager._normalize(-1.0, 10.0) == 0.0
    assert peers_module.PeerManager._score_snapshots(manager, []) == []


def test_peer_manager_rejects_invalid_weights(import_engine) -> None:
    peers_module = import_engine("engine.peers")

    with pytest.raises(ValueError, match="sum to a positive value"):
        peers_module.PeerManager(speed_weight=0.0, choke_weight=0.0, connection_weight=0.0)
