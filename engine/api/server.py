import time
import subprocess
import json
import os
from dataclasses import asdict
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
import asyncio

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
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

# ── Persistence ───────────────────────────────────────────────────────────────

ACTIVE_TORRENTS_FILE = str(get_config_dir() / "active_torrents.json")

def _save_active_torrent_record(t_id: str, type: str, source: str, save_path: str | None):
    try:
        records = _load_active_torrent_records()
        records[t_id] = {"type": type, "source": source, "save_path": save_path}
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
        except Exception:
            _remove_active_torrent_record(t_id)

# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    restore_active_torrents()
    task = asyncio.create_task(controller.run())
    yield
    await controller.shutdown()
    task.cancel()

app = FastAPI(title="Sluice Torrent Engine API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})

# ── Mapping helpers ───────────────────────────────────────────────────────────

def map_state_to_item(state: TorrentState) -> TorrentItem:
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
        save_path=state.save_path,
    )

# ── Torrent CRUD ──────────────────────────────────────────────────────────────

@app.post("/api/torrent/add/file", response_model=ApiResponse)
async def add_torrent_file(file: UploadFile = File(...), save_path: str | None = None):
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
    return ApiResponse(success=True, message="Torrent added successfully", data={"torrent_id": t_id})

@app.post("/api/torrent/add/magnet", response_model=ApiResponse)
async def add_torrent_magnet(req: MagnetAddRequest):
    try:
        t_id = controller.engine.add_magnet(req.magnet_link, save_path=req.save_path)
        _save_active_torrent_record(t_id, "magnet", req.magnet_link, req.save_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    return ApiResponse(success=True, message="Torrent added successfully", data={"torrent_id": t_id})

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
        return JSONResponse(status_code=500, content={"success": False, "error": f"Failed: {e}"})
    return ApiResponse(success=True, message="Torrent added", data={"torrent_id": t_id, "save_path": req.save_path})

# ── Filesystem ────────────────────────────────────────────────────────────────

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
        return ApiResponse(success=True, data={
            "current_path": str(target),
            "parent_path": parent_path,
            "directories": dirs,
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.post("/api/fs/mkdir", response_model=ApiResponse)
async def make_directory(req: MkdirRequest):
    try:
        if ".." in req.name or "/" in req.name or "\\" in req.name:
            return JSONResponse(status_code=400, content={"success": False, "error": "Invalid folder name"})
        target = Path(req.path) / req.name
        target.mkdir(parents=True, exist_ok=False)
        return ApiResponse(success=True, message="Directory created", data={"path": str(target)})
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

# ── Torrent list ──────────────────────────────────────────────────────────────

@app.get("/api/torrents", response_model=ApiResponse)
async def get_torrents():
    states = controller.get_all_states()
    mapped = [map_state_to_item(s) for s in states.values()]
    return ApiResponse(success=True, data={"torrents": mapped})

# ── Torrent detail (PER-TORRENT only) ────────────────────────────────────────

@app.get("/api/torrent/{id}", response_model=ApiResponse)
async def get_torrent_detail(id: str):
    state = controller.get_state(id)
    if not state:
        return JSONResponse(status_code=404, content={"success": False, "error": "Torrent not found"})

    item = map_state_to_item(state).model_dump()

    # Piece map (capped at 2000 for UI)
    try:
        raw_pieces = controller.engine.get_pieces(id)
        pieces = [
            {"index": p.index, "state": p.state.value, "availability": p.availability, "is_complete": p.is_complete}
            for p in raw_pieces
        ][:2000]
    except Exception:
        pieces = []

    # Peer detail
    try:
        peers_detail = [
            {"endpoint": p.endpoint, "client": p.client, "download_speed": p.download_speed, "is_choked": p.is_choked}
            for p in controller.get_cached_peers(id)
        ]
    except Exception:
        peers_detail = []

    # ── Per-torrent structured metrics block ──────────────────────────────
    try:
        torrent_metrics = controller.build_torrent_metrics(id)
        metrics_dict = _metrics_to_dict(torrent_metrics) if torrent_metrics else {}
    except Exception:
        metrics_dict = {}

    return ApiResponse(
        success=True,
        data={
            **item,
            "files": [
                {"name": f"{state.name}_file.data", "size": state.total_size, "progress": state.progress / 100.0}
            ],
            "trackers": [{"url": "libtorrent tracking (automatic)", "status": "working"}],
            "pieces": pieces,
            "peers_detail": peers_detail,
            "metrics": metrics_dict,      # ← structured per-torrent metrics
        },
    )

# ── Torrent controls ──────────────────────────────────────────────────────────

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
    path = state.save_path or str(Path.home() / "Downloads")
    try:
        if os.path.exists(path):
            subprocess.Popen(['xdg-open', path])
            return ApiResponse(success=True, message=f"Opened {path}")
        return JSONResponse(status_code=404, content={"success": False, "error": "Directory does not exist"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# ── Global stats (lightweight — for header bar) ───────────────────────────────

@app.get("/api/stats", response_model=ApiResponse)
async def get_stats():
    states = list(controller.get_all_states().values())
    active = sum(1 for s in states if s.download_speed > 0 or s.upload_speed > 0)
    global_down = sum(s.download_speed for s in states)
    global_up = sum(s.upload_speed for s in states)
    total_peers = sum(s.peers_connected for s in states)
    current_aggression = getattr(controller.bandwidth_optimizer, "_aggression_level", 0)

    return ApiResponse(success=True, data={
        "global_speed_down": global_down,
        "global_speed_up": global_up,
        "total_peers": total_peers,
        "active_torrents": active,
        "aggressive_mode": current_aggression > 0,
        "aggression_level": current_aggression,
    })

# ── Debug endpoint (GLOBAL scope + per-torrent breakdown) ─────────────────────
#
# Supports ?include=speed,peers,pieces,scheduler,health  (comma-separated)
# Default: all sections included.
# Example: GET /api/debug?include=peers,scheduler

@app.get("/api/debug", response_model=ApiResponse)
async def get_debug_stats(
    include: Optional[str] = Query(default=None, description="Comma-separated sections: speed,peers,pieces,scheduler,health,time")
):
    requested = set(s.strip() for s in include.split(",")) if include else None
    include_all = requested is None

    def want(section: str) -> bool:
        return include_all or section in requested  # type: ignore[operator]

    states = list(controller.get_all_states().values())

    # ── Global aggregates ─────────────────────────────────────────────────
    global_down = sum(s.download_speed for s in states)
    global_up = sum(s.upload_speed for s in states)
    total_peers = sum(s.peers_connected for s in states)
    active_count = sum(1 for s in states if s.download_speed > 0)

    global_data: dict = {
        "active_torrents": active_count,
        "total_speed_down": global_down,
        "total_speed_up": global_up,
        "total_peers": total_peers,
    }

    if want("speed"):
        m = controller.metrics.speed
        global_data["speed"] = {
            "avg_10s": round(m.rolling_avg(), 0),
            "peak": round(m._peak, 0),
            "current": float(m._current),
            "history": list(m._history),
        }

    if want("health"):
        metrics_obj = controller.metrics.speed.build_health_metrics(
            bw_utilization=sum(controller._last_bw_utilization.values()) / max(len(states), 1)
        )
        global_data["health"] = {
            "efficiency": metrics_obj.efficiency,
            "stability": metrics_obj.stability,
            "bandwidth_utilization": metrics_obj.bandwidth_utilization,
            "stall_events": metrics_obj.stall_events,
            "stall_time": metrics_obj.stall_time,
        }

    if want("time"):
        time_m = controller.metrics.speed.build_time_metrics()
        global_data["time"] = {
            "ttfb": time_m.ttfb,
            "t50": time_m.t50,
            "session_uptime": time_m.session_uptime,
        }

    # ── Per-torrent breakdown ─────────────────────────────────────────────
    torrents_data = []
    for state in states:
        t_entry: dict = {"id": state.id, "name": state.name, "progress": round(state.progress, 1)}

        try:
            tm = controller.build_torrent_metrics(state.id)
            if tm:
                torrent_dict = _metrics_to_dict(tm)
                # Filter to requested sections
                if not include_all and requested:
                    torrent_dict = {k: v for k, v in torrent_dict.items() if k in requested}
                t_entry["metrics"] = torrent_dict
        except Exception:
            t_entry["metrics"] = {}

        torrents_data.append(t_entry)

    return ApiResponse(success=True, data={
        "global": global_data,
        "torrents": torrents_data,
        "scheduler": {
            "mode": _derive_mode(controller.config.scheduler),
            "weights": {
                "rarity": controller.config.scheduler.rarity_weight,
                "speed": controller.config.scheduler.speed_weight,
                "peer": controller.config.scheduler.peer_weight,
                "position": controller.config.scheduler.position_weight,
            },
        } if want("scheduler") else {},
    })

# ── Mode toggle ────────────────────────────────────────────────────────────────

class ModeToggleRequest(BaseModel):
    aggressive_mode: bool

@app.post("/api/mode", response_model=ApiResponse)
async def toggle_mode(req: ModeToggleRequest):
    return ApiResponse(success=True, data={"aggressive_mode": req.aggressive_mode})

# ── Internal helpers ───────────────────────────────────────────────────────────

def _metrics_to_dict(tm) -> dict:
    """Serialize TorrentMetrics dataclasses to plain dict for JSON."""
    return {
        "speed": {
            "current": tm.speed.current,
            "avg_10s": tm.speed.avg_10s,
            "peak": tm.speed.peak,
            "variance": tm.speed.variance,
            "history": tm.speed.history,
        },
        "peers": {
            "total": tm.peers.total,
            "active": tm.peers.active,
            "fast": tm.peers.fast,
            "slow": tm.peers.slow,
            "seeds": tm.peers.seeds,
            "avg_speed": tm.peers.avg_speed,
            "fast_threshold": tm.peers.fast_threshold,
        },
        "pieces": {
            "total": tm.pieces.total,
            "completed": tm.pieces.completed,
            "active": tm.pieces.active,
            "stalled": tm.pieces.stalled,
            "rarest_count": tm.pieces.rarest_count,
            "completion_rate": tm.pieces.completion_rate,
            "min_availability": tm.pieces.min_availability,
            "max_availability": tm.pieces.max_availability,
            "avg_availability": tm.pieces.avg_availability,
        },
        "scheduler": {
            "mode": tm.scheduler.mode,
            "avg_score": tm.scheduler.avg_score,
            "top_score": tm.scheduler.top_score,
            "low_score": tm.scheduler.low_score,
            "high_priority_count": tm.scheduler.high_priority_count,
            "rare_pieces_boosted": tm.scheduler.rare_pieces_boosted,
            "pieces_scored": tm.scheduler.pieces_scored,
            "decision_distribution": tm.scheduler.decision_distribution,
        },
        "health": {
            "efficiency": tm.health.efficiency,
            "stability": tm.health.stability,
            "bandwidth_utilization": tm.health.bandwidth_utilization,
            "stall_events": tm.health.stall_events,
            "stall_time": tm.health.stall_time,
        },
        "time": {
            "ttfb": tm.time.ttfb,
            "t50": tm.time.t50,
            "session_uptime": tm.time.session_uptime,
        },
    }

def _derive_mode(config) -> str:
    if getattr(config, "speed_weight", 0) >= 0.45:
        return "aggressive"
    if getattr(config, "rarity_weight", 0) >= 0.50:
        return "safe"
    return "balanced"
