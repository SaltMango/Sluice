from dataclasses import dataclass, field
from enum import Enum
from typing import Set

class PieceState(Enum):
    """Represents the lifecycle of a single piece in the torrent."""
    AVAILABLE = "available"
    REQUESTED = "requested"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"

class PriorityBucket(Enum):
    """Discrete priority states representing explicit libtorrent priorities."""
    IGNORE = 0
    LOW = 1
    DEFAULT = 4
    MEDIUM = 5
    HIGH = 7

@dataclass(slots=True)
class PieceInfo:
    """Represents an abstracted state of a torrent piece, decoupled from libtorrent types."""
    index: int
    state: PieceState
    availability: int
    is_complete: bool = False

@dataclass(slots=True)
class PeerInfo:
    """Represents an abstracted peer connection, decoupled from libtorrent types."""
    endpoint: str
    client: str
    download_speed: int
    is_choked: bool
    connection_time: float
    pieces: tuple[bool, ...] = field(default_factory=tuple)

@dataclass(slots=True)
class TorrentState:
    """A clean domain snapshot representing the active condition of the engine for UI consumption."""
    id: str
    name: str
    save_path: str
    progress: float
    download_speed: int
    upload_speed: int
    peers_connected: int
    seeds_connected: int
    state_str: str
    total_size: int
    total_downloaded: int
    added_at: float

@dataclass(slots=True)
class ScoredPeer:
    """Represents a fully evaluated and scored peer record."""
    info: PeerInfo
    normalized_download_speed: float
    normalized_choke_state: float
    normalized_connection_time: float
    peer_score: float

@dataclass(slots=True)
class PieceScore:
    """Represents a fully evaluated and scheduled piece record."""
    info: PieceInfo
    peer_availability: int
    peer_speed: int
    score: float
    priority: PriorityBucket
