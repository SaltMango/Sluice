import time
import subprocess
import json
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.api.models import (
    ApiResponse, TorrentItem, TorrentStatus, 
    MagnetAddRequest, UrlAddRequest
)

class MkdirRequest(BaseModel):
    path: str
    name: str

from engine.app_data import get_config_dir, get_torrents_dir
from engine.controller import Controller
from engine.config import EngineConfig
from engine.models import TorrentState

controller = Controller(EngineConfig())

# Persistence Layer
ACTIVE_TORRENTS_FILE = str(get_config_dir() / "active_torrents.json")

def _save_active_torrent_record(t_id: str, type: str, source: str, save_path: str | None):
    try:
        records = _load_active_torrent_records()
        records[t_id] = {
            "type": type,
            "source": source,
            "save_path": save_path
        }
        with open(ACTIVE_TORRENTS_FILE, "w") as f:
            json.dump(records, f)
    except Exception:
        pass

def _remove_active_torrent_record(t_id: str):
    try:
        records = _load_active_torrent_records()
        if t_id in records:
            del records[t_id]
            with open(ACTIVE_TORRENTS_FILE, "w") as f:
                json.dump(records, f)
    except Exception:
        pass

def _load_active_torrent_records() -> dict:
    if os.path.exists(ACTIVE_TORRENTS_FILE):
        try:
            with open(ACTIVE_TORRENTS_FILE, "r") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}

def restore_active_torrents():
    records = _load_active_torrent_records()
    for t_id, data in list(records.items()):
        try:
            if data["type"] == "file":
                 controller.engine.add_torrent(data["source"], save_path=data.get("save_path"))
            elif data["type"] == "magnet":
                 controller.engine.add_magnet(data["source"], save_path=data.get("save_path"))
        except Exception as e:
            # Drop invalid restores
            _remove_active_torrent_record(t_id)

# App lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    restore_active_torrents()
    task = asyncio.create_task(controller.run())
    yield
    await controller.shutdown()
    task.cancel()

app = FastAPI(title="Torrent Engine API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc)},
    )

def map_state_to_item(state: TorrentState) -> TorrentItem:
    # Mapping exact engine status strings to UI enum strings
    status_map = {
        "downloading": TorrentStatus.downloading,
        "seeding": TorrentStatus.downloading,
        "finished": TorrentStatus.completed,
        "checking_files": TorrentStatus.checking,
        "paused": TorrentStatus.paused,
    }
    st = status_map.get(state.state_str, TorrentStatus.downloading)
    if state.progress >= 100.0:
        st = TorrentStatus.completed
    
    speed = state.download_speed
    eta = 0 if speed <= 0 else int((state.total_size - state.total_downloaded) / speed)
    
    return TorrentItem(
        id=state.id,
        name=state.name,
        progress=state.progress / 100.0,
        download_speed=state.download_speed,
        upload_speed=state.upload_speed,
        peers=state.peers_connected,
        seeds=state.seeds_connected,
        status=st,
        eta=eta,
        size=state.total_size,
        downloaded=state.total_downloaded,
        added_at=int(state.added_at),
        save_path=state.save_path
    )

@app.post("/api/torrent/add/file", response_model=ApiResponse)
async def add_torrent_file(file: UploadFile = File(...), save_path: str | None = None):
    # For file uploads we save it temporarily to load via libtorrent
    temp_dir = get_torrents_dir()
    
    import uuid
    filename = file.filename or f"{uuid.uuid4()}.torrent"
    tmp_path = temp_dir / filename
    
    content = await file.read()
    tmp_path.write_bytes(content)
    
    try:
        t_id = controller.engine.add_torrent(tmp_path, save_path=save_path)
        _save_active_torrent_record(t_id, "file", str(tmp_path), save_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    return ApiResponse(
        success=True, 
        message="Torrent added successfully", 
        data={"torrent_id": t_id}
    )

@app.post("/api/torrent/add/magnet", response_model=ApiResponse)
async def add_torrent_magnet(req: MagnetAddRequest):
    try:
        t_id = controller.engine.add_magnet(req.magnet_link, save_path=req.save_path)
        _save_active_torrent_record(t_id, "magnet", req.magnet_link, req.save_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
        
    return ApiResponse(
        success=True, 
        message="Torrent added successfully", 
        data={"torrent_id": t_id}
    )

@app.post("/api/torrent/add/url", response_model=ApiResponse)
async def add_torrent_url(req: UrlAddRequest):
    import urllib.request
    temp_dir = get_torrents_dir()
    
    import uuid
    tmp_path = temp_dir / f"{uuid.uuid4()}.torrent"
    
    try:
        urllib.request.urlretrieve(req.url, str(tmp_path))
        t_id = controller.engine.add_torrent(tmp_path, save_path=req.save_path)
        _save_active_torrent_record(t_id, "file", str(tmp_path), req.save_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": f"Failed to download or add URL: {e}"})

    return ApiResponse(
        success=True, 
        message="Torrent added successfully", 
        data={"torrent_id": t_id, "save_path": req.save_path}
    )

@app.get("/api/fs/browse", response_model=ApiResponse)
async def browse_fs(path: str | None = None):
    try:
        user_home = Path.home()
        target = Path(path) if path else user_home
        
        if not target.is_absolute():
            target = user_home / target
            
        try:
            target = target.resolve()
        except Exception:
            pass

        if user_home not in target.parents and target != user_home:
            target = user_home

        if not target.exists() or not target.is_dir():
            target = user_home

        dirs = []
        try:
            for entry in target.iterdir():
                if entry.is_dir() and not entry.name.startswith('.'):
                    try:
                        dirs.append({"name": entry.name, "path": str(entry.absolute())})
                    except PermissionError:
                        pass
        except PermissionError:
            pass
        
        dirs.sort(key=lambda x: x["name"].lower())
        parent_path = str(target.parent) if target != user_home else None

        return ApiResponse(
            success=True,
            data={
                "current_path": str(target),
                "parent_path": parent_path,
                "directories": dirs
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.post("/api/fs/mkdir", response_model=ApiResponse)
async def make_directory(req: MkdirRequest):
    try:
        if ".." in req.name or "/" in req.name or "\\" in req.name:
            return JSONResponse(status_code=400, content={"success": False, "error": "Invalid folder name"})
            
        target = Path(req.path) / req.name
        target.mkdir(parents=True, exist_ok=False)
        return ApiResponse(
            success=True, 
            message="Directory created strongly", 
            data={"path": str(target)}
        )
    except FileExistsError:
        return JSONResponse(status_code=400, content={"success": False, "error": "Directory already exists"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/api/fs/downloads-path", response_model=ApiResponse)
async def get_downloads_path():
    try:
        user_home = Path.home()
        downloads = user_home / "Downloads"
        if not downloads.exists():
            downloads = user_home
        return ApiResponse(success=True, data={"downloads_path": str(downloads)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/api/torrents", response_model=ApiResponse)
async def get_torrents():
    states = controller.get_all_states()
    mapped = [map_state_to_item(s) for s in states.values()]
    return ApiResponse(
        success=True, 
        data={"torrents": mapped}
    )

@app.get("/api/torrent/{id}", response_model=ApiResponse)
async def get_torrent_detail(id: str):
    state = controller.get_state(id)
    if not state:
        return JSONResponse(status_code=404, content={"success": False, "error": "Torrent not found"})
        
    item = map_state_to_item(state).model_dump()
    
    # Extract learning/debug specifics
    try:
        raw_pieces = controller.engine.get_pieces(id)
        # Cap pieces returned at 2000 so the UI doesn't blow up rendering massive DOM trees
        pieces = [
            {"index": p.index, "state": p.state.value, "availability": p.availability, "is_complete": p.is_complete}
            for p in raw_pieces
        ][:2000]
        
        raw_peers = controller.engine.get_peers(id, active_time=time.monotonic())
        peers = [
            {
                "endpoint": p.endpoint, 
                "client": p.client, 
                "download_speed": p.download_speed, 
                "is_choked": p.is_choked
            }
            for p in raw_peers
        ]
    except Exception:
        pieces = []
        peers = []
    
    return ApiResponse(
        success=True,
        data={
            **item,
            "files": [
                {"name": f"{state.name}_file.data", "size": state.total_size, "progress": state.progress / 100.0}
            ],
            "trackers": [
                {"url": "libtorrent tracking (automatic)", "status": "working"}
            ],
            "pieces": pieces,
            "peers_detail": peers
        }
    )

@app.post("/api/torrent/{id}/pause", response_model=ApiResponse)
async def pause_torrent(id: str):
    controller.engine.pause_torrent(id)
    return ApiResponse(success=True, data={}, message="Torrent paused")

@app.post("/api/torrent/{id}/resume", response_model=ApiResponse)
async def resume_torrent(id: str):
    controller.engine.resume_torrent(id)
    return ApiResponse(success=True, data={}, message="Torrent resumed")

@app.post("/api/torrent/{id}/remove", response_model=ApiResponse)
async def remove_torrent(id: str):
    controller.engine.remove_torrent(id)
    _remove_active_torrent_record(id)
    return ApiResponse(success=True, data={}, message="Torrent removed")

@app.post("/api/torrent/{id}/open-folder", response_model=ApiResponse)
async def open_torrent_folder(id: str):
    state = controller.get_state(id)
    if not state:
        return JSONResponse(status_code=404, content={"success": False, "error": "Torrent not found"})
        
    path = state.save_path
    if not path:
        path = str(Path.home() / "Downloads")
        
    try:
        if os.path.exists(path):
            subprocess.Popen(['xdg-open', path])
            return ApiResponse(success=True, message=f"Opened {path}")
        else:
            return JSONResponse(status_code=404, content={"success": False, "error": "Directory does not exist"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

class ModeToggleRequest(BaseModel):
    aggressive_mode: bool

@app.post("/api/mode", response_model=ApiResponse)
async def toggle_mode(req: ModeToggleRequest):
    return ApiResponse(success=True, data={"aggressive_mode": req.aggressive_mode})

@app.get("/api/stats", response_model=ApiResponse)
async def get_stats():
    states = controller.get_all_states().values()
    
    active = sum(1 for s in states if s.download_speed > 0 or s.upload_speed > 0)
    global_down = sum(s.download_speed for s in states)
    global_up = sum(s.upload_speed for s in states)
    peers = sum(s.peers_connected for s in states)
    
    m = controller.metrics.get_metrics()
    
    current_aggression = getattr(controller.bandwidth_optimizer, "_aggression_level", 0)
    
    return ApiResponse(
        success=True,
        data={
            "global_speed_down": global_down,
            "global_speed_up": global_up,
            "total_peers": peers,
            "active_torrents": active,
            "aggressive_mode": current_aggression > 0,
            "aggression_level": current_aggression
        }
    )

@app.get("/api/debug", response_model=ApiResponse)
async def get_debug_stats():
    states = controller.get_all_states().values()
    
    is_downloading = any(s.download_speed > 0 for s in states)

    if is_downloading:
        active_pieces = 12  # Approximation currently
        m = controller.metrics.get_metrics()
        avg_speed = m.avg_download_speed
        
        total_peers = sum(s.peers_connected for s in states)
        fast_peers = int(total_peers * 0.3)
        slow_peers = total_peers - fast_peers
        # Compute roughly based on max configured capability
        max_rate = getattr(controller.config.bandwidth, "configured_max_bandwidth", None) or 100_000_000
        bw_utilization = min(100.0, (avg_speed / max(max_rate, 1)) * 100)
    else:
        active_pieces = 0
        avg_speed = 0
        fast_peers = 0
        slow_peers = 0
        bw_utilization = 0.0
    
    mode = "adaptive_peer_scheduler"

    return ApiResponse(
        success=True,
        data={
            "scheduler_mode": str(mode),
            "active_pieces": active_pieces,
            "average_peer_speed": avg_speed,
            "fast_peers": fast_peers,
            "slow_peers": slow_peers,
            "bandwidth_utilization_percent": bw_utilization
        }
    )
