from typing import Optional, List, Any
from pydantic import BaseModel, Field
from enum import Enum

class TorrentStatus(str, Enum):
    downloading = "downloading"
    paused = "paused"
    completed = "completed"
    checking = "checking"
    error = "error"

class TorrentItem(BaseModel):
    id: str
    name: str
    progress: float
    download_speed: int
    upload_speed: int
    peers: int
    seeds: int
    status: TorrentStatus
    eta: int
    size: int
    downloaded: int
    added_at: int
    error: Optional[str] = None
    tune_level: int = 0
    save_path: Optional[str] = None

class ApiResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None
    error: Optional[str] = None

class MagnetAddRequest(BaseModel):
    magnet_link: str
    save_path: Optional[str] = None

class UrlAddRequest(BaseModel):
    url: str
    save_path: Optional[str] = None
