import time
import uuid
from typing import Dict
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.api.models import (
    ApiResponse, TorrentItem, TorrentStatus, 
    MagnetAddRequest, UrlAddRequest
)

import asyncio
import random
from contextlib import asynccontextmanager

MOCK_AGGRESSION_LEVEL = 0

async def _mock_engine_loop():
    global MOCK_AGGRESSION_LEVEL
    while True:
        await asyncio.sleep(2)
        if not MOCK_AGGRESSIVE_MODE:
            if random.random() > 0.7:
                MOCK_AGGRESSION_LEVEL = min(MOCK_AGGRESSION_LEVEL + 1, 3)
            elif random.random() > 0.5:
                MOCK_AGGRESSION_LEVEL = max(MOCK_AGGRESSION_LEVEL - 1, 0)
        else:
            MOCK_AGGRESSION_LEVEL = 3

        now = get_current_time()
        for t_id, torrent in list(MOCK_TORRENTS.items()):
            if torrent.status == TorrentStatus.checking:
                if now - torrent.added_at > 3:
                    torrent.status = TorrentStatus.downloading
                    torrent.size = random.randint(500_000_000, 5_000_000_000)
            elif torrent.status == TorrentStatus.downloading:
                speed = random.randint(1_000_000, 5_000_000)
                torrent.download_speed = speed
                torrent.upload_speed = int(speed * 0.2)
                torrent.peers = random.randint(10, 50)
                torrent.seeds = random.randint(5, 20)
                torrent.downloaded += speed * 2
                if torrent.size > 0:
                    torrent.progress = min(torrent.downloaded / torrent.size, 1.0)
                    if torrent.progress >= 1.0:
                        torrent.status = TorrentStatus.completed
                        torrent.download_speed = 0
                        torrent.eta = 0
                    else:
                        remaining = torrent.size - torrent.downloaded
                        torrent.eta = int(remaining / speed)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_mock_engine_loop())
    yield
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

# --- MOCK STATE ---
MOCK_TORRENTS: Dict[str, TorrentItem] = {}
MOCK_AGGRESSIVE_MODE = False

class ModeToggleRequest(BaseModel):
    aggressive_mode: bool

def get_current_time() -> int:
    return int(time.time())

@app.post("/api/torrent/add/file", response_model=ApiResponse)
async def add_torrent_file(file: UploadFile = File(...)):
    new_id = str(uuid.uuid4())
    await file.read(1024) # dummy read
    
    mock_torrent = TorrentItem(
        id=new_id,
        name=file.filename or "uploaded.torrent",
        progress=0.0,
        download_speed=0,
        upload_speed=0,
        peers=0,
        seeds=0,
        status=TorrentStatus.checking,
        eta=0,
        size=1024 * 1024 * 100, 
        downloaded=0,
        added_at=get_current_time()
    )
    MOCK_TORRENTS[new_id] = mock_torrent
    
    return ApiResponse(
        success=True, 
        message="Torrent added successfully", 
        data={"torrent_id": new_id}
    )

@app.post("/api/torrent/add/magnet", response_model=ApiResponse)
async def add_torrent_magnet(req: MagnetAddRequest):
    new_id = str(uuid.uuid4())
    mock_torrent = TorrentItem(
        id=new_id,
        name="magnet-download",
        progress=0.0,
        download_speed=0,
        upload_speed=0,
        peers=0,
        seeds=0,
        status=TorrentStatus.checking,
        eta=0,
        size=0,
        downloaded=0,
        added_at=get_current_time()
    )
    MOCK_TORRENTS[new_id] = mock_torrent
    
    return ApiResponse(
        success=True, 
        message="Torrent added successfully", 
        data={"torrent_id": new_id}
    )

@app.post("/api/torrent/add/url", response_model=ApiResponse)
async def add_torrent_url(req: UrlAddRequest):
    new_id = str(uuid.uuid4())
    mock_torrent = TorrentItem(
        id=new_id,
        name="url-download",
        progress=0.0,
        download_speed=0,
        upload_speed=0,
        peers=0,
        seeds=0,
        status=TorrentStatus.checking,
        eta=0,
        size=0,
        downloaded=0,
        added_at=get_current_time()
    )
    MOCK_TORRENTS[new_id] = mock_torrent
    
    return ApiResponse(
        success=True, 
        message="Torrent added successfully", 
        data={"torrent_id": new_id}
    )

@app.get("/api/torrents", response_model=ApiResponse)
async def get_torrents():
    return ApiResponse(
        success=True, 
        data={"torrents": list(MOCK_TORRENTS.values())}
    )

@app.get("/api/torrent/{id}", response_model=ApiResponse)
async def get_torrent_detail(id: str):
    if id not in MOCK_TORRENTS:
        return JSONResponse(status_code=404, content={"success": False, "error": "Torrent not found"})
        
    base_item = MOCK_TORRENTS[id].model_dump()
    
    return ApiResponse(
        success=True,
        data={
            **base_item,
            "files": [
                {"name": f"{base_item['name']}", "size": base_item['size'], "progress": base_item['progress']}
            ],
            "trackers": [
                {"url": "udp://tracker.opentrackr.org:1337/announce", "status": "working"}
            ]
        }
    )

@app.post("/api/torrent/{id}/pause", response_model=ApiResponse)
async def pause_torrent(id: str):
    if id not in MOCK_TORRENTS:
        return JSONResponse(status_code=404, content={"success": False, "error": "Torrent not found"})
    MOCK_TORRENTS[id].status = TorrentStatus.paused
    MOCK_TORRENTS[id].download_speed = 0
    return ApiResponse(success=True, data={}, message="Torrent paused")

@app.post("/api/torrent/{id}/resume", response_model=ApiResponse)
async def resume_torrent(id: str):
    if id not in MOCK_TORRENTS:
        return JSONResponse(status_code=404, content={"success": False, "error": "Torrent not found"})
    MOCK_TORRENTS[id].status = TorrentStatus.downloading
    return ApiResponse(success=True, data={}, message="Torrent resumed")

@app.post("/api/torrent/{id}/remove", response_model=ApiResponse)
async def remove_torrent(id: str):
    if id not in MOCK_TORRENTS:
        return JSONResponse(status_code=404, content={"success": False, "error": "Torrent not found"})
    del MOCK_TORRENTS[id]
    return ApiResponse(success=True, data={}, message="Torrent removed")

@app.get("/api/stats", response_model=ApiResponse)
async def get_stats():
    global MOCK_AGGRESSIVE_MODE
    active = sum(1 for t in MOCK_TORRENTS.values() if t.status == TorrentStatus.downloading)
    global_down = sum(t.download_speed for t in MOCK_TORRENTS.values())
    global_up = sum(t.upload_speed for t in MOCK_TORRENTS.values())
    peers = sum(t.peers for t in MOCK_TORRENTS.values())
    
    return ApiResponse(
        success=True,
        data={
            "global_speed_down": global_down,
            "global_speed_up": global_up,
            "total_peers": peers,
            "active_torrents": active,
            "aggressive_mode": MOCK_AGGRESSIVE_MODE,
            "aggression_level": MOCK_AGGRESSION_LEVEL
        }
    )

@app.post("/api/mode", response_model=ApiResponse)
async def toggle_mode(req: ModeToggleRequest):
    global MOCK_AGGRESSIVE_MODE
    MOCK_AGGRESSIVE_MODE = req.aggressive_mode
    return ApiResponse(success=True, data={"aggressive_mode": MOCK_AGGRESSIVE_MODE})


