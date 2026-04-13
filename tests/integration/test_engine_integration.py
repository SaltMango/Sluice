from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT, clear_engine_modules


def build_test_torrent(tmp_path: Path, lt) -> Path:
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
def test_torrent_engine_with_real_libtorrent(enable_real_libtorrent, tmp_path: Path) -> None:
    clear_engine_modules()
    import libtorrent as lt
    from engine.peers import PeerManager
    from engine.torrent import TorrentEngine

    torrent_path = build_test_torrent(tmp_path, lt)
    engine = TorrentEngine(download_directory=tmp_path / "downloads")
    engine.start_session()
    engine.add_torrent(torrent_path)

    status = engine.get_status()
    peers = engine.get_peer_info()
    ranked_peers = PeerManager().collect(peers, now=10.0)

    assert status.name == "payload"
    assert status.progress == 0.0
    assert status.download_rate == 0
    assert status.peers == 0
    assert isinstance(status.state, str)
    assert peers == []
    assert ranked_peers == []


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
