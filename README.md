# ⚡ SpeedTube — Ultra-Fast YouTube Downloader Web App

A modern, high-performance web application designed to download YouTube videos at maximum possible speed with real-time progress telemetry, multi-stream fragment acceleration, lossless FFmpeg muxing, and instant MP3 audio extraction.

---

## 🚀 Key Features

- **⚡ Blazing Fast Multi-Threaded Engine**:
  - Leverages concurrent fragment downloads (8x to 16x concurrent streams).
  - High-bandwidth chunking (`http_chunk_size = 10MB`) to eliminate YouTube stream throttling.
- **🎥 Full HD & 4K Ultra HD Support**:
  - Automatically fetches the best separate video and audio streams and losslessly muxes them into a standard `.mp4` using system FFmpeg with `-c copy` (zero quality loss, sub-second muxing).
  - Supports 2160p (4K), 1440p (2K), 1080p60 (Full HD), 720p, 480p, and 360p.
- **🎵 Studio Quality MP3 Audio Extraction**:
  - Extracts 320 kbps (High Quality), 192 kbps (Standard), or 128 kbps MP3 files with 1 click.
- **📊 Real-Time WebSocket Telemetry**:
  - Live animated progress bar with smooth percentage (0% to 100%).
  - Live speedometer (e.g. `24.5 MB/s`), remaining ETA countdown, and downloaded size ratio.
  - Phase pipeline tracker: `Connect` ➔ `Fetch Stream` ➔ `FFmpeg Mux` ➔ `Ready`.
- **💻 Windows Native Integration**:
  - **Save to PC**: Direct browser download dialog.
  - **Show in Folder**: 1-click button to open Windows File Explorer with the downloaded file highlighted (`explorer.exe /select`).
  - **Built-in Media Player**: Inline preview video/audio player to watch or listen immediately inside the app.
- **📁 History & Management**:
  - Tracks all previously downloaded files with their sizes, formats, and modification dates.
  - Quick action buttons to replay, save again, or delete.
- **🎨 Sleek Cyberpunk/Minimalist Dark UI**:
  - Responsive glassmorphism cards, glowing neon accents, and clipboard 1-click auto-paste.

---

## 🛠️ Quick Start

### Option 1: 1-Click Launch (Windows)
Double-click `start.bat` in the project root:
```cmd
start.bat
```
This automatically initializes the virtual environment, verifies dependencies, starts the FastAPI server, and launches your default web browser at `http://127.0.0.1:8000`.

### Option 2: Python Command Line
```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run the application
python run.py
```
Or directly with Uvicorn:
```powershell
.\venv\Scripts\uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## 📁 Project Structure

```
YTDownload/
├── backend/
│   ├── app.py             # FastAPI server with WebSockets, REST APIs, & static hosting
│   ├── downloader.py      # Multi-threaded yt-dlp downloader & progress engine
│   └── config.py          # Automatic FFmpeg/Node detection and system settings
├── frontend/
│   ├── index.html         # Sleek modern responsive web interface
│   ├── style.css          # Glassmorphic dark theme and animations
│   └── app.js             # WebSocket real-time progress client and media manager
├── downloads/             # Local storage folder for downloaded videos/audio
├── venv/                  # Python 3.11 virtual environment
├── requirements.txt       # Project Python dependencies
├── run.py                 # Cross-platform runner with auto-browser launch
├── start.bat              # 1-click Windows launcher
└── README.md              # Documentation
```

---

## ⚙️ Configuration & Speed Modes

Inside the web app's **Settings** (top right gear icon), you can adjust the concurrency level:
- **4x (Balanced)**: Moderate network usage, ideal for shared connections.
- **8x (Turbo - Default)**: Optimal speed saturation for high-speed fiber/cable internet.
- **16x (Extreme)**: Maximum multi-threaded fragmentation for ultra-fast multi-gigabit connections.

---

## 💡 Tech Stack
- **Backend**: Python 3.11, FastAPI, Uvicorn, WebSockets, yt-dlp, FFmpeg 9.0 (Gyan full build).
- **Frontend**: Vanilla JavaScript (ES6+), HTML5, CSS3 Glassmorphism, Native WebSockets, HTML5 Video/Audio API.
