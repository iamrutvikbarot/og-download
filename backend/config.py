"""
Configuration and system dependency resolution for SpeedTube Downloader.
"""
import os
import shutil
import glob
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
try:
    DOWNLOADS_DIR = BASE_DIR / "downloads"
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
except (OSError, PermissionError):
    DOWNLOADS_DIR = Path("/tmp/downloads")
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

def find_ffmpeg_bin() -> str | None:
    """
    Find ffmpeg executable.
    Checks system PATH, common Windows WinGet locations, and environment variables.
    """
    # 1. System PATH
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg

    # 2. Check WinGet Gyan.FFmpeg or other winget packages
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_pattern = os.path.join(
            local_app_data, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "bin", "ffmpeg.exe"
        )
        matches = glob.glob(winget_pattern, recursive=True)
        if matches:
            return matches[0]

        winget_pattern_root = os.path.join(
            local_app_data, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "ffmpeg.exe"
        )
        matches = glob.glob(winget_pattern_root, recursive=True)
        if matches:
            return matches[0]

    # 3. Check Program Files
    for prog_dir in [os.environ.get("ProgramFiles", "C:\\Program Files"), os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")]:
        if prog_dir:
            matches = glob.glob(os.path.join(prog_dir, "*ffmpeg*", "**", "ffmpeg.exe"), recursive=True)
            if matches:
                return matches[0]

    return None

FFMPEG_PATH = find_ffmpeg_bin()
FFMPEG_DIR = os.path.dirname(FFMPEG_PATH) if FFMPEG_PATH else None

# Ensure FFmpeg is in the PATH if found
if FFMPEG_DIR and FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

# Node.js check for yt-dlp JS challenges
NODE_PATH = shutil.which("node")

# High performance configuration defaults
DEFAULT_CONCURRENT_FRAGMENTS = 16  # High concurrency (16 parallel fragment streams)
DEFAULT_BUFFER_SIZE = 4 * 1024 * 1024       # 4MB stream buffer
DEFAULT_HTTP_CHUNK_SIZE = 20971520          # 20MB chunk size for maximum throughput
