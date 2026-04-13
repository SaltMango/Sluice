from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


class FakeSession:
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config
        self.calls: list[str] = []
        self.added_params: list[dict[str, str | object]] = []

    def start_dht(self) -> None:
        self.calls.append("dht")

    def start_lsd(self) -> None:
        self.calls.append("lsd")

    def start_upnp(self) -> None:
        self.calls.append("upnp")

    def start_natpmp(self) -> None:
        self.calls.append("natpmp")

    def add_torrent(self, params: dict[str, str | object]) -> object:
        self.added_params.append(params)
        return {"handle": "added"}


def test_package_exports(import_engine) -> None:
    engine_package = import_engine("engine")

    assert engine_package.__all__ == [
        "BandwidthOptimizer",
        "BandwidthSnapshot",
        "Controller",
        "ControllerSnapshot",
        "PeerManager",
        "PeerSnapshot",
        "PieceScore",
        "Scheduler",
        "ScoredPeer",
        "TorrentEngine",
        "TorrentStatus",
    ]


def test_start_session_is_idempotent_and_creates_download_directory(
    tmp_path: Path, import_engine, libtorrent_stub
) -> None:
    torrent_module = import_engine("engine.torrent")
    sessions: list[FakeSession] = []

    def create_session(config: dict[str, str]) -> FakeSession:
        session = FakeSession(config)
        sessions.append(session)
        return session

    libtorrent_stub.session = create_session

    engine = torrent_module.TorrentEngine(download_directory=tmp_path / "downloads")

    engine.start_session()
    engine.start_session()

    assert len(sessions) == 1
    assert sessions[0].config == {"listen_interfaces": "0.0.0.0:6881"}
    assert sessions[0].calls == ["dht", "lsd", "upnp", "natpmp"]
    assert (tmp_path / "downloads").is_dir()


def test_add_torrent_uses_torrent_info_and_rejects_invalid_states(
    tmp_path: Path, import_engine, libtorrent_stub
) -> None:
    torrent_module = import_engine("engine.torrent")
    torrent_file = tmp_path / "sample.torrent"
    torrent_file.write_text("dummy")

    captured_paths: list[str] = []
    session = FakeSession({"listen_interfaces": "0.0.0.0:6881"})

    def fake_torrent_info(path: str) -> object:
        captured_paths.append(path)
        return {"path": path}

    libtorrent_stub.session = lambda _config: session
    libtorrent_stub.torrent_info = fake_torrent_info

    engine = torrent_module.TorrentEngine(download_directory=tmp_path / "downloads")
    engine.add_torrent(torrent_file)

    assert captured_paths == [str(torrent_file.resolve())]
    assert session.added_params == [
        {
            "ti": {"path": str(torrent_file.resolve())},
            "save_path": str((tmp_path / "downloads").resolve()),
        }
    ]
    assert engine._handle == {"handle": "added"}

    with pytest.raises(RuntimeError, match="already active"):
        engine.add_torrent(torrent_file)

    missing_file = tmp_path / "missing.torrent"
    other_engine = torrent_module.TorrentEngine(download_directory=tmp_path / "other-downloads")
    other_engine.start_session()
    with pytest.raises(FileNotFoundError, match="Torrent file not found"):
        other_engine.add_torrent(missing_file)


def test_get_status_and_peer_info_behaviour(tmp_path: Path, import_engine) -> None:
    torrent_module = import_engine("engine.torrent")
    engine = torrent_module.TorrentEngine(download_directory=tmp_path / "downloads")

    with pytest.raises(RuntimeError, match="No torrent has been added yet"):
        engine.get_status()

    with pytest.raises(RuntimeError, match="No torrent has been added yet"):
        engine.get_peer_info()

    with pytest.raises(RuntimeError, match="No torrent has been added yet"):
        engine.get_handle()

    with pytest.raises(RuntimeError, match="Session has not been started yet"):
        engine.get_session()

    fake_status = SimpleNamespace(
        name="ubuntu.iso",
        progress=0.5,
        download_rate=2048,
        num_peers=7,
        state="downloading",
    )
    fake_peer_list = [SimpleNamespace(ip=("127.0.0.1", 6881))]
    fake_session = SimpleNamespace()
    engine._session = fake_session
    engine._handle = SimpleNamespace(
        status=lambda: fake_status,
        get_peer_info=lambda: fake_peer_list,
    )

    status = engine.get_status()

    assert status == torrent_module.TorrentStatus(
        name="ubuntu.iso",
        progress=50.0,
        download_rate=2048,
        peers=7,
        state="downloading",
    )
    assert engine.get_peer_info() == fake_peer_list
    assert engine.get_handle() is engine._handle
    assert engine.get_session() is fake_session


def test_default_download_directory_uses_project_root(import_engine) -> None:
    torrent_module = import_engine("engine.torrent")

    engine = torrent_module.TorrentEngine()

    assert engine._download_directory == (
        Path(torrent_module.__file__).resolve().parents[1] / "downloads"
    ).resolve()
