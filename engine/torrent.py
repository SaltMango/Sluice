from __future__ import annotations

import pathlib
from pathlib import Path
from typing import Any, List, Optional
import libtorrent as lt  # type: ignore[import-not-found]

from engine.models import TorrentState, PeerInfo, PieceInfo, PieceState
from engine.exceptions import TorrentError
from engine.logger import get_logger

logger = get_logger(__name__)

DEFAULT_LISTEN_INTERFACES = "0.0.0.0:6881"

class TorrentEngine:
    """Libtorrent wrapper that exclusively returns strict domain Data Contracts."""

    def __init__(self, download_directory: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self._download_directory = (download_directory or project_root / "downloads").resolve()
        
        self._session: Any | None = None
        self._handle: Any | None = None
        self._resume_path: Path | None = None

    def start_session(self) -> None:
        if self._session is not None:
            return
            
        try:
            self._download_directory.mkdir(parents=True, exist_ok=True)
            self._session = lt.session({"listen_interfaces": DEFAULT_LISTEN_INTERFACES})
            self._session.start_dht()
            self._session.start_lsd()
            self._session.start_upnp()
            self._session.start_natpmp()
        except Exception as e:
            logger.exception("Failed to start libtorrent session")
            raise TorrentError(f"Session failure: {e}") from e

    def add_torrent(self, file_path: str | Path) -> None:
        if self._handle is not None:
            raise TorrentError("A torrent is already active globally in this engine instance")

        self.start_session()
        torrent_path = Path(file_path).expanduser().resolve()
        if not torrent_path.is_file():
            raise TorrentError(f"Torrent file not found: {torrent_path}")
            
        self._resume_path = torrent_path.with_suffix(".resume")

        try:
            params = lt.add_torrent_params()
            params.save_path = str(self._download_directory)
            params.ti = lt.torrent_info(str(torrent_path))

            # Attempt Resume Loading
            if self._resume_path.exists():
                try:
                    with open(self._resume_path, "rb") as f:
                        params.resume_data = f.read()
                    logger.info("Loaded resume data successfully")
                except Exception:
                    logger.warning("Failed to load existing resume data, starting fresh")

            assert self._session is not None
            self._handle = self._session.add_torrent(params)
        except Exception as e:
            raise TorrentError(f"Failed to add torrent: {e}") from e

    def get_state(self) -> TorrentState:
        if not self._handle:
            raise TorrentError("No active torrent handle")
            
        status = self._handle.status()
        return TorrentState(
            name=status.name,
            progress=status.progress * 100,
            download_speed=status.download_rate,
            upload_speed=status.upload_rate,
            peers_connected=status.num_peers,
            state_str=str(status.state),
        )

    def get_peers(self, active_time: float) -> list[PeerInfo]:
        if not self._handle:
            raise TorrentError("No active torrent handle")

        peer_infos = []
        for peer in self._handle.get_peer_info():
            ip_val = getattr(peer, "ip", None)
            endpoint = f"{ip_val[0]}:{ip_val[1]}" if isinstance(ip_val, tuple) else str(ip_val)
            pieces_tuple = tuple(bool(has_piece) for has_piece in peer.pieces) if hasattr(peer, "pieces") else ()
            flags = int(getattr(peer, "flags", 0))
            is_choked = bool(flags & lt.peer_info.remote_choked)
            
            peer_infos.append(PeerInfo(
                endpoint=endpoint,
                client=str(getattr(peer, "client", "")),
                download_speed=max(int(getattr(peer, "down_speed", 0)), 0),
                is_choked=is_choked,
                connection_time=active_time, # Simplify active tracking logic for now
                pieces=pieces_tuple
            ))
        return peer_infos

    def get_pieces(self) -> list[PieceInfo]:
        if not self._handle:
            raise TorrentError("No active torrent handle")
            
        info = self._handle.torrent_file()
        if not info:
             return []
        
        piece_count = info.num_pieces()
        availability = list(self._handle.piece_availability())
        
        pieces = []
        for i in range(piece_count):
            is_complete = bool(self._handle.have_piece(i))
            
            # Map states based on availability and logic checks
            # Ideally we'd hook piece download start events from libtorrent
            state = PieceState.COMPLETE if is_complete else PieceState.AVAILABLE
            if not is_complete and availability[i] > 0 and self._handle.piece_priority(i) > 0:
                 # Approximating requested/downloading states via priority
                 state = PieceState.REQUESTED
                 
            pieces.append(PieceInfo(
                index=i,
                state=state,
                availability=int(availability[i]),
                is_complete=is_complete
            ))
        return pieces

    def apply_priorities(self, priorities: list[int]) -> None:
        if not self._handle:
            return
        self._handle.prioritize_pieces(priorities)

    def get_session_settings(self) -> dict[str, int]:
        if not self._session:
             return {}
        settings = self._session.get_settings()
        return {key: int(value) for key, value in settings.items() if isinstance(value, int)}

    def apply_session_settings(self, settings: dict[str, int]) -> None:
        if not self._session:
             return
        self._session.apply_settings(settings)

    def save_resume_data(self) -> None:
        if not self._handle or not self._resume_path:
             return
        
        try:
             self._handle.save_resume_data(lt.save_resume_flags_t.flush_disk_cache)
             logger.info("Requested save_resume_data via libtorrent")
        except Exception as e:
             logger.error("Failed to request save resume data", extra={"error": str(e)})

    # Needs a dedicated loop listener for the save_resume_data_alert to actually write to disk
    # This simplifies that logic for synchronous saving assuming session has pause capabilities
    def pause_and_shutdown(self) -> None:
        if getattr(self, "_shutting_down", False):
            return
            
        self._shutting_down = True
        logger.info("Executing graceful pause and shutdown")
        
        if self._handle:
            try:
                self._handle.pause()
                # Fast save if required directly here or wait for alert. 
                # For simplicity we assume controller manages this via sync operations
            except Exception as e:
                logger.error("Error during torrent shutdown", extra={"error": str(e)})
