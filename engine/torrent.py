from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import libtorrent as lt


DEFAULT_LISTEN_INTERFACES = "0.0.0.0:6881"


@dataclass(slots=True)
class TorrentStatus:
    name: str
    progress: float
    download_rate: int
    peers: int
    state: str


class TorrentEngine:
    """Minimal libtorrent wrapper for a single active torrent."""

    def __init__(self, download_directory: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self._download_directory = (download_directory or project_root / "downloads").resolve()
        self._session: Any | None = None
        self._handle: Any | None = None

    def start_session(self) -> None:
        if self._session is not None:
            return

        self._download_directory.mkdir(parents=True, exist_ok=True)
        self._session = lt.session({"listen_interfaces": DEFAULT_LISTEN_INTERFACES})
        self._session.start_dht()
        self._session.start_lsd()
        self._session.start_upnp()
        self._session.start_natpmp()

    def add_torrent(self, file_path: str | Path) -> None:
        if self._handle is not None:
            raise RuntimeError("A torrent is already active in this engine instance.")

        self.start_session()

        torrent_path = Path(file_path).expanduser().resolve()
        if not torrent_path.is_file():
            raise FileNotFoundError(f"Torrent file not found: {torrent_path}")

        torrent_info = lt.torrent_info(str(torrent_path))
        params = {
            "ti": torrent_info,
            "save_path": str(self._download_directory),
        }
        self._handle = self._session.add_torrent(params)

    def get_status(self) -> TorrentStatus:
        if self._handle is None:
            raise RuntimeError("No torrent has been added yet.")

        status = self._handle.status()
        return TorrentStatus(
            name=status.name,
            progress=status.progress * 100,
            download_rate=status.download_rate,
            peers=status.num_peers,
            state=self._resolve_state_name(status.state),
        )

    def get_peer_info(self) -> list[Any]:
        if self._handle is None:
            raise RuntimeError("No torrent has been added yet.")

        return list(self._handle.get_peer_info())

    @staticmethod
    def _resolve_state_name(state: object) -> str:
        return str(state)
