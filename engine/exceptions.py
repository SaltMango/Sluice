class EngineError(Exception):
    """Base class for all torrent engine exceptions."""
    pass

class TorrentError(EngineError):
    """Errors related to underlying libtorrent bindings and state."""
    pass

class PeerError(EngineError):
    """Errors arising from peer connection logic and parsing."""
    pass

class SchedulerError(EngineError):
    """Failures occurring during piece scheduling operations."""
    pass

class BandwidthError(EngineError):
    """Errors related to computing bandwidth or setting limits."""
    pass
