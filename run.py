"""
SpeedTube Server Launcher
Runs the FastAPI app via Uvicorn.
"""
import sys
import webbrowser
import threading
import time
import uvicorn

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    print("=" * 60)
    print(" ⚡ SpeedTube - Ultra-Fast YouTube Downloader")
    print(" Starting local server at http://127.0.0.1:8000")
    print("=" * 60)
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=False, log_level="info")
