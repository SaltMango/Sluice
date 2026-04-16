from __future__ import annotations

import pathlib
from pathlib import Path
from typing import Any, List, Optional
import time
import libtorrent as lt  # type: ignore[import-not-found]

from engine.app_data import get_resume_dir
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
        self._handles: dict[str, Any] = {}
        self._resume_paths: dict[str, Path] = {}
        self._added_times: dict[str, float] = {}

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

    def add_torrent(self, file_path: str | Path, save_path: str | None = None) -> str:
        self.start_session()
        torrent_path = Path(file_path).expanduser().resolve()
        if not torrent_path.is_file():
            raise TorrentError(f"Torrent file not found: {torrent_path}")
            
        resume_path = get_resume_dir() / f"{torrent_path.name}.resume"

        try:
            params = lt.add_torrent_params()
            params.save_path = save_path or str(self._download_directory)
            params.ti = lt.torrent_info(str(torrent_path))

            # Attempt Resume Loading
            if resume_path.exists():
                try:
                    with open(resume_path, "rb") as f:
                        params.resume_data = f.read()
                    logger.info("Loaded resume data successfully")
                except Exception:
                    logger.warning("Failed to load existing resume data, starting fresh")

            assert self._session is not None
            handle = self._session.add_torrent(params)
            t_id = str(handle.info_hash())
            self._handles[t_id] = handle
            self._resume_paths[t_id] = resume_path
            
            import time
            self._added_times[t_id] = time.time()
            return t_id
        except Exception as e:
            raise TorrentError(f"Failed to add torrent: {e}") from e

    def add_magnet(self, magnet_link: str, save_path: str | None = None) -> str:
        self.start_session()
        try:
            params = lt.parse_magnet_uri(magnet_link)
            params.save_path = save_path or str(self._download_directory)
            
            assert self._session is not None
            handle = self._session.add_torrent(params)
            t_id = str(handle.info_hash())
            self._handles[t_id] = handle
            self._resume_paths[t_id] = get_resume_dir() / f"{t_id}.resume"
            
            import time
            self._added_times[t_id] = time.time()
            return t_id
        except Exception as e:
            raise TorrentError(f"Failed to add magnet: {e}") from e

    def get_all_active_ids(self) -> list[str]:
        return list(self._handles.keys())

    def get_state(self, t_id: str) -> TorrentState:
        handle = self._handles.get(t_id)
        if not handle:
            raise TorrentError(f"No active torrent handle for {t_id}")
            
        status = handle.status()
        state_str = "paused" if status.paused else str(status.state)
        
        return TorrentState(
            id=t_id,
            name=status.name,
            save_path=status.save_path,
            progress=status.progress * 100,
            download_speed=status.download_rate,
            upload_speed=status.upload_rate,
            peers_connected=status.num_peers,
            seeds_connected=status.num_seeds,
            state_str=state_str,
            total_size=status.total_wanted,
            total_downloaded=status.total_wanted_done,
            added_at=self._added_times.get(t_id, 0.0)
        )

    def get_peers(self, t_id: str, active_time: float) -> list[PeerInfo]:
        handle = self._handles.get(t_id)
        if not handle:
            raise TorrentError(f"No active torrent handle for {t_id}")

        peer_infos = []
        for peer in handle.get_peer_info():
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

    def get_pieces(self, t_id: str) -> list[PieceInfo]:
        handle = self._handles.get(t_id)
        if not handle:
            raise TorrentError(f"No active torrent handle for {t_id}")
            
        info = handle.torrent_file()
        if not info:
             return []
        
        piece_count = info.num_pieces()
        availability = list(handle.piece_availability())
        
        pieces = []
        for i in range(piece_count):
            is_complete = bool(handle.have_piece(i))
            
            # Map states based on availability and logic checks
            # Ideally we'd hook piece download start events from libtorrent
            state = PieceState.COMPLETE if is_complete else PieceState.AVAILABLE
            if not is_complete and availability[i] > 0 and handle.piece_priority(i) > 0:
                 # Approximating requested/downloading states via priority
                 state = PieceState.REQUESTED
                 
            pieces.append(PieceInfo(
                index=i,
                state=state,
                availability=int(availability[i]),
                is_complete=is_complete
            ))
        return pieces

    def apply_priorities(self, t_id: str, priorities: list[int]) -> None:
        handle = self._handles.get(t_id)
        if not handle:
            return
        
        try:
            current = handle.piece_priorities()
            if current != priorities:
                handle.prioritize_pieces(priorities)
        except Exception:
            handle.prioritize_pieces(priorities)

    def get_session_settings(self) -> dict[str, int]:
        if not self._session:
             return {}
        settings = self._session.get_settings()
        return {key: int(value) for key, value in settings.items() if isinstance(value, int)}

    def apply_session_settings(self, settings: dict[str, int]) -> None:
        if not self._session:
             return
             
        current = self.get_session_settings()
        changed = {k: v for k, v in settings.items() if current.get(k) != v}
        
        if changed:
            self._session.apply_settings(changed)

    def save_resume_data(self, t_id: str | None = None) -> None:
        targets = [t_id] if t_id else self._handles.keys()
        
        for k in targets:
            handle = self._handles.get(k)
            if not handle:
                continue
                
            try:
                handle.save_resume_data(lt.save_resume_flags_t.flush_disk_cache)
                logger.info("Requested save_resume_data via libtorrent", extra={"torrent": k})
            except Exception as e:
                logger.error("Failed to request save resume data", extra={"error": str(e), "torrent": k})

    def remove_torrent(self, t_id: str) -> None:
        handle = self._handles.get(t_id)
        if handle and self._session:
            self._session.remove_torrent(handle)
        self._handles.pop(t_id, None)
        self._resume_paths.pop(t_id, None)
        self._added_times.pop(t_id, None)

    def pause_torrent(self, t_id: str) -> None:
        handle = self._handles.get(t_id)
        if handle:
            handle.pause()

    def resume_torrent(self, t_id: str) -> None:
        handle = self._handles.get(t_id)
        if handle:
            handle.resume()

    # Needs a dedicated loop listener for the save_resume_data_alert to actually write to disk
    # This simplifies that logic for synchronous saving assuming session has pause capabilities
    def pause_and_shutdown(self) -> None:
        if getattr(self, "_shutting_down", False):
            return
            
        self._shutting_down = True
        logger.info("Executing graceful pause and shutdown")
        
        for t_id, handle in self._handles.items():
            try:
                handle.pause()
            except Exception as e:
                logger.error(f"Error during torrent {t_id} shutdown", extra={"error": str(e)})
