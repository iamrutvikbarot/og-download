"""
FastAPI application server with WebSockets, REST endpoints, and static file hosting.
"""
import os
import sys
import glob
import json
import uuid
import asyncio
import urllib.parse
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import (
    BASE_DIR,
    DOWNLOADS_DIR,
    FFMPEG_PATH,
    FFMPEG_DIR,
    NODE_PATH,
    DEFAULT_CONCURRENT_FRAGMENTS,
)
from backend.downloader import (
    extract_video_info,
    DownloadTask,
    format_bytes,
)

app = FastAPI(title="OG Download - Ultra-Fast YouTube Downloader")

# Enable CORS for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=6)

# Global settings state
APP_SETTINGS = {
    "concurrent_fragments": DEFAULT_CONCURRENT_FRAGMENTS,
    "downloads_dir": str(DOWNLOADS_DIR),
}

class InfoRequest(BaseModel):
    url: str

class SettingsRequest(BaseModel):
    concurrent_fragments: int

class OpenFolderRequest(BaseModel):
    filename: Optional[str] = None

@app.get("/api/status")
async def get_system_status():
    """Return backend health and capability report."""
    return {
        "status": "ready",
        "ffmpeg_installed": bool(FFMPEG_PATH),
        "ffmpeg_path": FFMPEG_PATH,
        "node_installed": bool(NODE_PATH),
        "node_path": NODE_PATH,
        "downloads_dir": APP_SETTINGS["downloads_dir"],
        "concurrent_fragments": APP_SETTINGS["concurrent_fragments"],
    }

@app.post("/api/info")
async def get_info(req: InfoRequest):
    """Retrieve video metadata and format listing."""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Please enter a YouTube video URL.")

    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(executor, extract_video_info, url)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.api_route("/api/direct-download", methods=["GET", "HEAD"])
async def direct_download(
    url: str,
    type: str = "video",
    height: Optional[int] = None,
    format_id: Optional[str] = None,
    audio_quality: str = "320"
):
    """
    Direct 1-step download endpoint:
    Processes the video at maximum speed and returns the file directly as an attachment stream.
    """
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing YouTube URL.")

    task_id = str(uuid.uuid4())[:8]
    loop = asyncio.get_running_loop()

    task = DownloadTask(
        task_id=task_id,
        url=url,
        download_type=type,
        height=int(height) if height else None,
        format_id=str(format_id) if format_id else None,
        audio_quality=str(audio_quality),
        concurrent_fragments=APP_SETTINGS["concurrent_fragments"]
    )

    try:
        result = await loop.run_in_executor(executor, task.run)
        safe_name = os.path.basename(result["filename"])
        filepath = Path(APP_SETTINGS["downloads_dir"]) / safe_name
        
        if not filepath.exists():
            raise HTTPException(status_code=500, detail="Download failed to save file.")

        return FileResponse(
            path=str(filepath),
            filename=safe_name,
            media_type="application/octet-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings")
async def get_settings():
    return APP_SETTINGS

@app.post("/api/settings")
async def update_settings(req: SettingsRequest):
    if req.concurrent_fragments in [4, 8, 16, 24, 32]:
        APP_SETTINGS["concurrent_fragments"] = req.concurrent_fragments
        return {"status": "success", "settings": APP_SETTINGS}
    raise HTTPException(status_code=400, detail="Invalid fragments value. Choose 4, 8, 16, or 32.")

@app.websocket("/ws/download")
async def websocket_download(websocket: WebSocket):
    """WebSocket connection to stream live download events to the frontend."""
    await websocket.accept()
    loop = asyncio.get_running_loop()

    try:
        while True:
            raw_msg = await websocket.receive_text()
            data = json.loads(raw_msg)
            
            action = data.get("action")
            if action == "start":
                url = data.get("url", "").strip()
                download_type = data.get("type", "video") # 'video' or 'audio'
                height = data.get("height")
                format_id = data.get("format_id")
                audio_quality = data.get("audio_quality", "320")
                task_id = str(uuid.uuid4())[:8]

                def notify_client(event: Dict[str, Any]):
                    # Thread-safe dispatch back to websocket
                    try:
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_text(json.dumps(event)),
                            loop
                        )
                    except Exception:
                        pass

                task = DownloadTask(
                    task_id=task_id,
                    url=url,
                    download_type=download_type,
                    height=int(height) if height else None,
                    format_id=str(format_id) if format_id else None,
                    audio_quality=str(audio_quality),
                    concurrent_fragments=APP_SETTINGS["concurrent_fragments"],
                    progress_callback=notify_client
                )

                # Execute in threadpool
                await loop.run_in_executor(executor, task.run)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"status": "error", "message": str(e)}))
        except Exception:
            pass

@app.api_route("/api/download/{filename:path}", methods=["GET", "HEAD"])
async def download_file(filename: str):
    """Deliver the downloaded file directly to the user's browser."""
    # Prevent directory traversal and decode URL percent-encoding
    decoded_name = urllib.parse.unquote(filename)
    safe_name = os.path.basename(decoded_name)
    filepath = Path(APP_SETTINGS["downloads_dir"]) / safe_name
    
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Requested file was not found.")

    return FileResponse(
        path=str(filepath),
        filename=safe_name,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.api_route("/api/stream/{filename:path}", methods=["GET", "HEAD"])
async def stream_media(filename: str):
    """Stream audio or video for inline browser HTML5 preview player."""
    decoded_name = urllib.parse.unquote(filename)
    safe_name = os.path.basename(decoded_name)
    filepath = Path(APP_SETTINGS["downloads_dir"]) / safe_name
    
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    ext = filepath.suffix.lower()
    media_type = "video/mp4"
    if ext == ".mp3":
        media_type = "audio/mpeg"
    elif ext == ".m4a":
        media_type = "audio/mp4"
    elif ext == ".webm":
        media_type = "video/webm"

    return FileResponse(
        path=str(filepath),
        media_type=media_type
    )

@app.get("/api/history")
async def get_download_history():
    """Retrieve history of downloaded media files."""
    downloads_path = Path(APP_SETTINGS["downloads_dir"])
    files = []

    for ext in ("*.mp4", "*.m4a", "*.mp3", "*.webm", "*.mkv"):
        for p in downloads_path.glob(ext):
            try:
                stat = p.stat()
                encoded_name = urllib.parse.quote(p.name)
                files.append({
                    "filename": p.name,
                    "filepath": str(p),
                    "size": stat.st_size,
                    "size_formatted": format_bytes(stat.st_size),
                    "modified": stat.st_mtime,
                    "is_audio": p.suffix.lower() in [".mp3", ".m4a", ".wav", ".aac"],
                    "ext": p.suffix.lower().lstrip("."),
                    "download_url": f"/api/download/{encoded_name}",
                    "stream_url": f"/api/stream/{encoded_name}",
                })
            except Exception:
                continue

    # Sort descending by latest modified
    files.sort(key=lambda x: x["modified"], reverse=True)
    return files

@app.delete("/api/history/{filename:path}")
async def delete_downloaded_file(filename: str):
    """Remove a downloaded file from disk."""
    decoded_name = urllib.parse.unquote(filename)
    safe_name = os.path.basename(decoded_name)
    filepath = Path(APP_SETTINGS["downloads_dir"]) / safe_name
    if filepath.exists() and filepath.is_file():
        try:
            filepath.unlink()
            return {"status": "success", "message": f"{safe_name} deleted."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="File does not exist.")

@app.post("/api/open-folder")
async def open_download_folder(req: OpenFolderRequest = None):
    """Open Windows File Explorer with optional file selected."""
    downloads_path = Path(APP_SETTINGS["downloads_dir"])
    try:
        if req and req.filename:
            decoded_name = urllib.parse.unquote(req.filename)
            target = downloads_path / os.path.basename(decoded_name)
            if target.exists():
                # Open Explorer with file highlighted
                subprocess.Popen(["explorer.exe", f"/select,{str(target)}"])
                return {"status": "success", "message": "File Explorer opened."}

        # Otherwise just open folder
        if sys.platform == "win32":
            os.startfile(str(downloads_path))
        else:
            subprocess.Popen(["xdg-open", str(downloads_path)])
        return {"status": "success", "message": "Folder opened."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {str(e)}")

# Mount static files for frontend
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
