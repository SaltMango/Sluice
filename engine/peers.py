from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence

import libtorrent as lt  # type: ignore[import-not-found]


@dataclass(slots=True)
class PeerSnapshot:
    endpoint: str
    client: str
    download_speed: int
    is_choked: bool
    connection_time: float


@dataclass(slots=True)
class ScoredPeer:
    endpoint: str
    client: str
    download_speed: int
    is_choked: bool
    connection_time: float
    normalized_download_speed: float
    normalized_choke_state: float
    normalized_connection_time: float
    peer_score: float


class PeerManager:
    """Collects libtorrent peer data and ranks peers by a weighted score."""

    def __init__(
        self,
        speed_weight: float = 0.6,
        choke_weight: float = 0.25,
        connection_weight: float = 0.15,
    ) -> None:
        total_weight = speed_weight + choke_weight + connection_weight
        if total_weight <= 0:
            raise ValueError("Peer score weights must sum to a positive value.")

        self._speed_weight = speed_weight / total_weight
        self._choke_weight = choke_weight / total_weight
        self._connection_weight = connection_weight / total_weight
        self._first_seen_at: dict[str, float] = {}

    def collect(self, peer_infos: Sequence[Any], now: float | None = None) -> list[ScoredPeer]:
        observed_at = time.monotonic() if now is None else now
        snapshots = self._build_snapshots(peer_infos=peer_infos, observed_at=observed_at)
        return self._score_snapshots(snapshots)

    def collect_from_handle(self, torrent_handle: Any, now: float | None = None) -> list[ScoredPeer]:
        return self.collect(peer_infos=list(torrent_handle.get_peer_info()), now=now)

    def _build_snapshots(self, peer_infos: Sequence[Any], observed_at: float) -> list[PeerSnapshot]:
        snapshots: list[PeerSnapshot] = []
        active_endpoints: set[str] = set()

        for peer in peer_infos:
            endpoint = self._peer_endpoint(peer)
            active_endpoints.add(endpoint)

            first_seen_at = self._first_seen_at.setdefault(endpoint, observed_at)
            snapshots.append(
                PeerSnapshot(
                    endpoint=endpoint,
                    client=str(getattr(peer, "client", "")),
                    download_speed=max(int(getattr(peer, "down_speed", 0)), 0),
                    is_choked=self._is_remote_choking(peer),
                    connection_time=max(observed_at - first_seen_at, 0.0),
                )
            )

        self._first_seen_at = {
            endpoint: first_seen_at
            for endpoint, first_seen_at in self._first_seen_at.items()
            if endpoint in active_endpoints
        }
        return snapshots

    def _score_snapshots(self, snapshots: Sequence[PeerSnapshot]) -> list[ScoredPeer]:
        if not snapshots:
            return []

        max_download_speed = max(snapshot.download_speed for snapshot in snapshots)
        max_connection_time = max(snapshot.connection_time for snapshot in snapshots)

        scored_peers = [
            self._score_snapshot(
                snapshot=snapshot,
                max_download_speed=max_download_speed,
                max_connection_time=max_connection_time,
            )
            for snapshot in snapshots
        ]
        return sorted(scored_peers, key=lambda peer: peer.peer_score, reverse=True)

    def _score_snapshot(
        self,
        snapshot: PeerSnapshot,
        max_download_speed: int,
        max_connection_time: float,
    ) -> ScoredPeer:
        normalized_download_speed = self._normalize(snapshot.download_speed, max_download_speed)
        normalized_choke_state = 0.0 if snapshot.is_choked else 1.0
        normalized_connection_time = self._normalize(snapshot.connection_time, max_connection_time)

        peer_score = (
            normalized_download_speed * self._speed_weight
            + normalized_choke_state * self._choke_weight
            + normalized_connection_time * self._connection_weight
        )

        return ScoredPeer(
            endpoint=snapshot.endpoint,
            client=snapshot.client,
            download_speed=snapshot.download_speed,
            is_choked=snapshot.is_choked,
            connection_time=snapshot.connection_time,
            normalized_download_speed=normalized_download_speed,
            normalized_choke_state=normalized_choke_state,
            normalized_connection_time=normalized_connection_time,
            peer_score=peer_score,
        )

    @staticmethod
    def _normalize(value: float, upper_bound: float) -> float:
        if upper_bound <= 0:
            return 0.0
        return min(max(value / upper_bound, 0.0), 1.0)

    @staticmethod
    def _is_remote_choking(peer: Any) -> bool:
        flags = int(getattr(peer, "flags", 0))
        return bool(flags & lt.peer_info.remote_choked)

    @staticmethod
    def _peer_endpoint(peer: Any) -> str:
        ip = getattr(peer, "ip", None)
        if isinstance(ip, tuple):
            host, port = ip
            return f"{host}:{port}"
        if ip is not None:
            return str(ip)
        return "unknown"
