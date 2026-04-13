from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import REPO_ROOT, clear_engine_modules


def build_test_torrent(tmp_path: Path, lt: Any) -> Path:
    payload_root = tmp_path / "payload"
    payload_root.mkdir()
    (payload_root / "hello.txt").write_text("hello world")

    file_storage = lt.file_storage()
    lt.add_files(file_storage, str(payload_root))

    torrent = lt.create_torrent(file_storage)
    lt.set_piece_hashes(torrent, str(tmp_path))

    torrent_path = tmp_path / "sample.torrent"
    torrent_path.write_bytes(lt.bencode(torrent.generate()))
    return torrent_path


@pytest.mark.integration
@pytest.mark.usefixtures("enable_real_libtorrent")
def test_torrent_engine_with_real_libtorrent(tmp_path: Path) -> None:
    clear_engine_modules()
    import libtorrent as lt  # type: ignore[import]
    from engine.controller import Controller
    from engine.peers import PeerManager
    from engine.scheduler import Scheduler
    from engine.torrent import TorrentEngine

    torrent_path = build_test_torrent(tmp_path, lt)
    engine = TorrentEngine(download_directory=tmp_path / "downloads")
    controller_output: list[object] = []
    controller = Controller(
        engine=engine,
        stats_printer=controller_output.append,
    )
    controller.start(torrent_path)

    status = engine.get_status()
    peers = engine.get_peer_info()
    ranked_peers = PeerManager().collect(peers, now=10.0)
    priorities = Scheduler().apply(engine.get_handle(), peer_infos=peers)
    controller_snapshot = controller.tick(now=10.0)

    assert status.name == "payload"
    assert status.progress == 0.0
    assert status.download_rate == 0
    assert status.peers == 0
    assert isinstance(status.state, str)
    assert peers == []
    assert ranked_peers == []
    assert priorities == [4]
    assert list(engine.get_handle().get_piece_priorities()) == [4]
    assert controller_snapshot.bandwidth is not None
    assert controller_snapshot.bandwidth.estimated_max_bandwidth == 0
    assert controller_snapshot.bandwidth_updated is True
    assert controller_snapshot.priorities == [4]
    assert controller_snapshot.peers == []
    assert len(controller_output) == 1


@pytest.mark.integration
def test_direct_script_help_uses_real_python() -> None:
    result = subprocess.run(
        ["/usr/bin/python3", str(REPO_ROOT / "engine" / "main.py"), "--help"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Minimal torrent downloader." in result.stdout
