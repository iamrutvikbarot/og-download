"""
Core downloader engine leveraging yt-dlp with optimized multi-threaded fragment fetching.
"""
import os
import re
import io
import json
import base64
import http.cookiejar
import math
import time
import asyncio
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional
import yt_dlp

from backend.config import (
    BASE_DIR,
    FFMPEG_PATH,
    FFMPEG_DIR,
    NODE_PATH,
    DOWNLOADS_DIR,
    DEFAULT_CONCURRENT_FRAGMENTS,
    DEFAULT_BUFFER_SIZE,
    DEFAULT_HTTP_CHUNK_SIZE
)

def format_bytes(size: Optional[int | float]) -> str:
    """Format byte size into human readable string."""
    if not size or math.isnan(size) or size <= 0:
        return "Unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {units[i]}"

def format_duration(seconds: Optional[int | float]) -> str:
    """Format duration in seconds to MM:SS or HH:MM:SS."""
    if not seconds:
        return "00:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def normalize_youtube_url(url: str) -> str:
    """Normalize shortened, embed, or tracking-param URLs to direct watch URLs."""
    url = url.strip()
    match = re.search(r"(?:v=|\/|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})", url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return url

def normalize_and_save_cookies(raw_content: str) -> Optional[str]:
    """
    Robustly normalizes raw cookie strings from Netscape format, JSON format (Cookie-Editor),
    base64 encoded strings, or escaped newlines/tabs from cloud environment variables.
    Validates with MozillaCookieJar before writing to prevent any LoadError exceptions.
    """
    if not raw_content or not raw_content.strip():
        return None

    raw = raw_content.strip()

    # 1. Base64 auto-detection
    try:
        decoded = base64.b64decode(raw).decode("utf-8", errors="ignore")
        if "youtube" in decoded.lower():
            raw = decoded.strip()
    except Exception:
        pass

    # 2. Unescape literal escaped \n and \t from cloud dashboard textareas
    if "\\n" in raw and "\n" not in raw:
        raw = raw.replace("\\r", "").replace("\\n", "\n").replace("\\t", "\t")

    lines_out = ["# Netscape HTTP Cookie File", "# Automatically normalized for yt-dlp", ""]

    # 3. JSON format detection (e.g. from Cookie-Editor extension)
    if (raw.startswith("[") and raw.endswith("]")) or (raw.startswith("{") and raw.endswith("}")):
        try:
            items = json.loads(raw)
            if isinstance(items, dict):
                items = [items]
            for item in items:
                domain = item.get("domain", ".youtube.com")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = item.get("path", "/")
                secure = "TRUE" if item.get("secure", False) else "FALSE"
                expiry = int(item.get("expirationDate", item.get("expiry", 2147483647)) or 2147483647)
                name = item.get("name", "")
                value = item.get("value", "")
                if name:
                    lines_out.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")
        except Exception:
            pass
    else:
        # 4. Standard Netscape lines or space-separated lines
        for line in raw.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("#"):
                continue
            parts = re.split(r"\t+|\s{2,}", line_s)
            if len(parts) >= 7:
                lines_out.append("\t".join(parts[:7]))
            elif len(parts) >= 2:
                name = parts[-2]
                val = parts[-1]
                lines_out.append(f".youtube.com\tTRUE\t/\tTRUE\t2147483647\t{name}\t{val}")

    if len(lines_out) <= 3:
        return None

    final_content = "\n".join(lines_out) + "\n"

    # 5. Strict validation with MozillaCookieJar to prevent any yt-dlp Netscape format errors
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar._really_load(io.StringIO(final_content), "validation", True, True)
    except Exception as e:
        print(f"Cookie validation error: {e}")
        return None

    target_path = Path("/tmp/cookies.txt") if os.name != "nt" else (BASE_DIR / "cookies_active.txt")
    try:
        target_path.write_text(final_content, encoding="utf-8")
        return str(target_path)
    except Exception as e:
        print(f"Failed to write cookie file: {e}")
        return None

def get_cookie_file_path() -> Optional[str]:
    """Retrieve verified cookie file path if available."""
    cookie_env = os.environ.get("YTDL_COOKIES")
    if cookie_env:
        res = normalize_and_save_cookies(cookie_env)
        if res:
            return res

    for p in [Path("cookies.txt"), BASE_DIR / "cookies.txt", Path("/tmp/cookies.txt")]:
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                res = normalize_and_save_cookies(content)
                if res:
                    return res
            except Exception:
                pass
    return None

def get_base_ydl_opts() -> Dict[str, Any]:
    """Base options for yt-dlp with FFmpeg location."""
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "no_color": True,
        "noplaylist": True,
        "source_address": "0.0.0.0",  # Force IPv4 to eliminate IPv6 network delays
        "socket_timeout": 15,
    }
    if FFMPEG_PATH:
        opts["ffmpeg_location"] = FFMPEG_DIR or FFMPEG_PATH

    cookie_file = get_cookie_file_path()
    if cookie_file:
        opts["cookiefile"] = cookie_file

    return opts

# In-memory fast cache for video metadata (15 min TTL)
_INFO_CACHE: Dict[str, Dict[str, Any]] = {}
_INFO_CACHE_EXPIRY: Dict[str, float] = {}
_INFO_YDL_INSTANCE: Optional[yt_dlp.YoutubeDL] = None

def get_info_extraction_opts() -> Dict[str, Any]:
    """Ultra-fast options specifically tuned for metadata and format extraction."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "skip_download": True,
        "youtube_include_dash_manifest": False,  # Skip extra DASH manifest HTTP request
        "youtube_include_hls_manifest": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "getcomments": False,
        "noplaylist": True,
        "source_address": "0.0.0.0",  # Force IPv4 to eliminate IPv6 network delays
        "allowed_extractors": ["youtube", "generic"],
        "extract_flat": False,
        "no_color": True,
        "ignoreerrors": False,
        "socket_timeout": 8,
    }

    cookie_file = get_cookie_file_path()
    if cookie_file:
        opts["cookiefile"] = cookie_file

    return opts

def get_shared_info_ydl() -> yt_dlp.YoutubeDL:
    """Persistent warm YoutubeDL instance to eliminate cold-start extractor init overhead."""
    global _INFO_YDL_INSTANCE
    if _INFO_YDL_INSTANCE is None:
        _INFO_YDL_INSTANCE = yt_dlp.YoutubeDL(get_info_extraction_opts())
    return _INFO_YDL_INSTANCE

def extract_video_info(url: str) -> Dict[str, Any]:
    """
    Extract video metadata, thumbnail, title, channel, duration, and clean format options.
    Fast extraction without downloading media streams.
    """
    url = normalize_youtube_url(url)
    cache_key = url.strip()
    now = time.time()
    if cache_key in _INFO_CACHE and now < _INFO_CACHE_EXPIRY.get(cache_key, 0):
        return _INFO_CACHE[cache_key]

    ydl = get_shared_info_ydl()
    try:
        info = ydl.extract_info(url, download=False)
    except Exception:
        # Recreate shared instance if it hit a transient socket error
        global _INFO_YDL_INSTANCE
        _INFO_YDL_INSTANCE = None
        opts = get_info_extraction_opts()
        try:
            with yt_dlp.YoutubeDL(opts) as fresh_ydl:
                info = fresh_ydl.extract_info(url, download=False)
        except Exception:
            # Fallback to android player_client if datacenter IP triggers YouTube bot detection
            opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
            with yt_dlp.YoutubeDL(opts) as fallback_ydl:
                info = fallback_ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Unable to retrieve information for the provided URL.")

    title = info.get("title", "Unknown Title")
    duration = info.get("duration", 0)
    channel = info.get("uploader") or info.get("channel", "Unknown Channel")
    channel_url = info.get("uploader_url") or info.get("channel_url", "")
    thumbnail = info.get("thumbnail") or (info.get("thumbnails")[-1]["url"] if info.get("thumbnails") else "")
    view_count = info.get("view_count", 0)
    upload_date = info.get("upload_date", "")
    description = info.get("description", "")
    if description and len(description) > 200:
        description = description[:200] + "..."

    # Parse formats
    raw_formats = info.get("formats", [])
    
    # Determine best audio bitrate for size calculations
    best_audio_tbr = 128
    best_audio_size = 0
    for f in raw_formats:
        if f.get("vcodec") == "none" and f.get("acodec") != "none":
            tbr = f.get("tbr") or f.get("abr") or 0
            if tbr > best_audio_tbr:
                best_audio_tbr = tbr
            size = f.get("filesize") or f.get("filesize_approx") or 0
            if size > best_audio_size:
                best_audio_size = size

    # Map video formats by height resolution (2160p, 1440p, 1080p, 720p, 480p, 360p)
    video_resolutions: Dict[int, Dict[str, Any]] = {}
    for f in raw_formats:
        height = f.get("height")
        if not height or height < 144:
            continue
        
        vcodec = f.get("vcodec", "")
        if vcodec == "none":
            continue

        fps = f.get("fps") or 30
        ext = f.get("ext", "mp4")
        filesize = f.get("filesize") or f.get("filesize_approx") or 0
        
        # If filesize is not reported, estimate based on bitrate and duration
        if not filesize and duration:
            tbr = (f.get("tbr") or f.get("vbr") or 0) + best_audio_tbr
            if tbr > 0:
                filesize = int((tbr * 1024 / 8) * duration)

        # Store the highest quality/FPS variant for each resolution
        if height not in video_resolutions or (fps > video_resolutions[height]["fps"]) or (ext == "mp4" and video_resolutions[height]["ext"] != "mp4"):
            label = f"{height}p"
            if height >= 2160:
                badge = "4K Ultra HD"
            elif height >= 1440:
                badge = "2K Quad HD"
            elif height >= 1080:
                badge = "Full HD"
            elif height >= 720:
                badge = "HD"
            else:
                badge = "SD"

            if fps and fps >= 50:
                label += f" {int(fps)}fps"

            video_resolutions[height] = {
                "height": height,
                "label": label,
                "badge": badge,
                "fps": fps,
                "ext": "mp4",
                "filesize": filesize,
                "filesize_formatted": format_bytes(filesize),
                "format_id": f.get("format_id"),
                "vcodec": vcodec[:10] if vcodec else "mp4"
            }

    # Sort video formats descending by height
    sorted_video_formats = sorted(video_resolutions.values(), key=lambda x: x["height"], reverse=True)

    # Audio format choices
    audio_formats = [
        {
            "quality": "320",
            "label": "MP3 High Quality (320 kbps)",
            "ext": "mp3",
            "badge": "Audio (Studio)",
            "filesize": int((320 * 1024 / 8) * duration) if duration else 0,
            "filesize_formatted": format_bytes(int((320 * 1024 / 8) * duration)) if duration else "High Quality",
        },
        {
            "quality": "192",
            "label": "MP3 Standard (192 kbps)",
            "ext": "mp3",
            "badge": "Audio (Standard)",
            "filesize": int((192 * 1024 / 8) * duration) if duration else 0,
            "filesize_formatted": format_bytes(int((192 * 1024 / 8) * duration)) if duration else "Standard Quality",
        },
        {
            "quality": "128",
            "label": "MP3 Compact (128 kbps)",
            "ext": "mp3",
            "badge": "Audio (Fast)",
            "filesize": int((128 * 1024 / 8) * duration) if duration else 0,
            "filesize_formatted": format_bytes(int((128 * 1024 / 8) * duration)) if duration else "Fast Download",
        }
    ]

    result = {
        "id": info.get("id"),
        "url": url,
        "title": title,
        "channel": channel,
        "channel_url": channel_url,
        "duration": duration,
        "duration_formatted": format_duration(duration),
        "thumbnail": thumbnail,
        "views": f"{view_count:,}" if view_count else "Unknown",
        "upload_date": f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}" if len(upload_date) == 8 else upload_date,
        "description": description,
        "video_formats": sorted_video_formats,
        "audio_formats": audio_formats,
        "best_format_summary": sorted_video_formats[0]["label"] if sorted_video_formats else "Best Available",
    }

    # Cache result for instant repeat/paste retrieval (15 min TTL)
    _INFO_CACHE[cache_key] = result
    _INFO_CACHE_EXPIRY[cache_key] = now + 900
    video_id = info.get("id")
    if video_id:
        _INFO_CACHE[video_id] = result
        _INFO_CACHE_EXPIRY[video_id] = now + 900

    return result

class DownloadTask:
    """Manages an active download with real-time progress dispatching."""
    
    def __init__(
        self,
        task_id: str,
        url: str,
        download_type: str = "video",
        height: Optional[int] = None,
        format_id: Optional[str] = None,
        audio_quality: str = "320",
        concurrent_fragments: int = DEFAULT_CONCURRENT_FRAGMENTS,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.task_id = task_id
        self.url = url
        self.download_type = download_type
        self.height = height
        self.format_id = format_id
        self.audio_quality = audio_quality
        self.concurrent_fragments = concurrent_fragments
        self.progress_callback = progress_callback
        self.final_filename: Optional[str] = None
        self.final_filepath: Optional[str] = None
        self.is_completed = False
        self.has_error = False
        self.error_message: Optional[str] = None
        self.current_stream_index = 1
        self.total_streams = 2 if download_type == "video" else 1

    def _notify(self, data: Dict[str, Any]):
        if self.progress_callback:
            data["task_id"] = self.task_id
            self.progress_callback(data)

    def _progress_hook(self, d: Dict[str, Any]):
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            
            percent = 0.0
            if total > 0:
                percent = round((downloaded / total) * 100, 1)

            speed = d.get("speed")
            speed_str = format_bytes(speed) + "/s" if speed else d.get("_speed_str", "-- MB/s")
            
            eta = d.get("eta")
            eta_str = f"{int(eta)}s" if eta is not None else d.get("_eta_str", "--")

            # Determine stream phase
            filename = d.get("filename", "")
            stream_label = "Video Stream" if ("f" in filename and ("mp4" in filename or "webm" in filename)) else "Audio Stream"
            if self.download_type == "audio":
                stream_label = "Audio Stream"

            self._notify({
                "status": "downloading",
                "phase": stream_label,
                "percent": percent,
                "downloaded_bytes": downloaded,
                "downloaded_str": format_bytes(downloaded),
                "total_bytes": total,
                "total_str": format_bytes(total),
                "speed": speed_str,
                "eta": eta_str,
            })

        elif status == "finished":
            self._notify({
                "status": "stream_finished",
                "phase": "Processing Stream",
                "percent": 100,
                "message": "Stream download finished. Preparing next step...",
            })

    def _postprocessor_hook(self, d: Dict[str, Any]):
        status = d.get("status")
        pp_name = d.get("postprocessor", "")
        if status == "started":
            msg = "Merging video and audio streams with FFmpeg..."
            if "ExtractAudio" in pp_name:
                msg = f"Converting audio to MP3 ({self.audio_quality} kbps)..."
            self._notify({
                "status": "processing",
                "phase": "FFmpeg Muxing",
                "percent": 99,
                "message": msg,
            })
        elif status == "finished":
            self._notify({
                "status": "processing",
                "phase": "Finalizing",
                "percent": 100,
                "message": "Stream processing complete.",
            })

    def run(self) -> Dict[str, Any]:
        """Execute download synchronously (run inside executor)."""
        opts = get_base_ydl_opts()
        
        # Output template: Video title and extension only (no ID, no tag)
        outtmpl = str(DOWNLOADS_DIR / "%(title).150s.%(ext)s")

        # High speed options
        opts.update({
            "concurrent_fragment_downloads": self.concurrent_fragments,
            "buffersize": DEFAULT_BUFFER_SIZE,
            "http_chunk_size": DEFAULT_HTTP_CHUNK_SIZE,
            "retries": 5,
            "fragment_retries": 5,
            "file_access_retries": 5,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "windowsfilenames": True,
            "outtmpl": outtmpl,
            "overwrites": True,
        })

        if self.download_type == "audio":
            # Audio-only extraction (MP3)
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.audio_quality,
                }],
            })
        else:
            # Video + Audio download and merge into MP4
            if self.format_id:
                fmt_str = (
                    f"{self.format_id}+bestaudio[ext=m4a]/"
                    f"{self.format_id}+bestaudio/"
                    f"{self.format_id}"
                )
            elif self.height:
                fmt_str = (
                    f"bestvideo[height={self.height}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height={self.height}]+bestaudio/"
                    f"bestvideo[height<={self.height}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={self.height}]+bestaudio/"
                    f"best[height<={self.height}]/best"
                )
            else:
                fmt_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"

            opts.update({
                "format": fmt_str,
                "merge_output_format": "mp4",
            })

        self._notify({
            "status": "starting",
            "phase": "Initializing Engine",
            "percent": 0,
            "message": f"Starting multi-threaded download ({self.concurrent_fragments} concurrent connections)...",
        })

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if not info:
                    raise ValueError("Failed to extract media data.")
                
                # Determine final file name
                if self.download_type == "audio":
                    filename = ydl.prepare_filename(info)
                    filename = re.sub(r"\.[^.]+$", ".mp3", filename)
                else:
                    filename = ydl.prepare_filename(info)
                    # If merged into mp4
                    mp4_candidate = re.sub(r"\.[^.]+$", ".mp4", filename)
                    if os.path.exists(mp4_candidate):
                        filename = mp4_candidate

                self.final_filepath = filename
                self.final_filename = os.path.basename(filename)
                self.is_completed = True

                file_size = os.path.getsize(filename) if os.path.exists(filename) else 0

                result = {
                    "task_id": self.task_id,
                    "status": "completed",
                    "filename": self.final_filename,
                    "filepath": self.final_filepath,
                    "filesize": file_size,
                    "filesize_formatted": format_bytes(file_size),
                    "title": info.get("title"),
                    "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration"),
                    "download_url": f"/api/download/{urllib.parse.quote(self.final_filename)}?t={int(time.time() * 1000)}",
                    "stream_url": f"/api/stream/{urllib.parse.quote(self.final_filename)}",
                }
                
                self._notify({
                    **result,
                    "percent": 100,
                    "phase": "Done",
                    "message": "Download and merge complete! Ready to save.",
                })
                return result

        except Exception as e:
            self.has_error = True
            self.error_message = str(e)
            self._notify({
                "status": "error",
                "phase": "Error",
                "error": str(e),
                "message": f"Download failed: {str(e)}",
            })
            raise
