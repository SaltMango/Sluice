from dataclasses import dataclass
from typing import List
import time

@dataclass
class Metrics:
    avg_download_speed: float = 0.0
    piece_completion_rate: float = 0.0
    peer_efficiency: float = 0.0

class MetricsCollector:
    """Aggregates active torrent metrics over time."""
    def __init__(self):
        self._speed_samples: List[int] = []
        self._start_time = time.time()
        self._completed_pieces = 0

    def record_speed(self, speed: int):
        self._speed_samples.append(speed)
        # Keep window reasonable
        if len(self._speed_samples) > 100:
            self._speed_samples.pop(0)

    def record_piece_complete(self):
        self._completed_pieces += 1

    def get_metrics(self) -> Metrics:
        avg_speed = sum(self._speed_samples) / max(len(self._speed_samples), 1)
        uptime = max(time.time() - self._start_time, 1.0)
        completion_rate = self._completed_pieces / uptime
        
        return Metrics(
            avg_download_speed=avg_speed,
            piece_completion_rate=completion_rate,
            peer_efficiency=0.0 # To be calculated based on active payloads vs dropped
        )
