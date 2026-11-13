/**
 * SpeedTube - Ultra-Fast YouTube Downloader
 * High Configuration by Default (16x Multi-Threaded Streaming, Glass Theme, Direct System Download)
 */

// Application State
const state = {
  currentVideo: null,
  lastAnalyzedUrl: "",
  isAnalyzing: false,
  isDownloading: false,
  activeBtn: null,
  socket: null,
  settings: {
    concurrent_fragments: 16,
    downloads_dir: "",
  },
  theme: "glass",
};

// DOM References
const el = {
  urlInput: document.getElementById("urlInput"),
  inputWrapper: document.getElementById("inputWrapper"),
  inputSpinner: document.getElementById("inputSpinner"),
  pasteBtn: document.getElementById("pasteBtn"),
  clearBtn: document.getElementById("clearBtn"),

  // Skeleton & Results Card
  loadingSkeleton: document.getElementById("loadingSkeleton"),
  videoResultCard: document.getElementById("videoResultCard"),
  videoThumb: document.getElementById("videoThumb"),
  videoDuration: document.getElementById("videoDuration"),
  videoViews: document.getElementById("videoViews"),
  videoDate: document.getElementById("videoDate"),
  videoTitle: document.getElementById("videoTitle"),
  channelName: document.getElementById("channelName"),
  channelAvatar: document.getElementById("channelAvatar"),
  videoFormatsList: document.getElementById("videoFormatsList"),
  audioFormatsList: document.getElementById("audioFormatsList"),
  previewThumbBtn: document.getElementById("previewThumbBtn"),

  // Toast Container
  toastContainer: document.getElementById("toastContainer"),

  // Dynamic Thumbnail Backdrop
  thumbBackdrop: document.getElementById("thumbBackdrop"),
};

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initSystem();
  setupEventListeners();
  handleInputChange();
});

// Theme Management (Frosted Glass Only)
function initTheme() {
  document.documentElement.setAttribute("data-theme", "glass");
}

// System Status Check
async function initSystem() {
  try {
    const res = await fetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      state.settings.concurrent_fragments = data.concurrent_fragments || 16;
      state.settings.downloads_dir = data.downloads_dir || "";
    }
  } catch (err) {
    console.error("System init check failed:", err);
  }
}

// Event Listeners setup
let inputDebounceTimer = null;

function setupEventListeners() {
  // Input handling with instant auto-detection
  el.urlInput.addEventListener("input", () => {
    handleInputChange();
    const val = el.urlInput.value.trim();

    // If input is empty, immediately clear below content
    if (!val) {
      resetResultsAndState();
      return;
    }

    // Auto-detect YouTube URL on input and render immediately
    clearTimeout(inputDebounceTimer);
    if (isYouTubeUrl(val) && val !== state.lastAnalyzedUrl) {
      inputDebounceTimer = setTimeout(() => {
        handleAnalyze();
      }, 50);
    }
  });

  // Paste Event: instantly auto-load formats with 0 delay
  el.urlInput.addEventListener("paste", (e) => {
    clearTimeout(inputDebounceTimer);
    setTimeout(() => {
      handleInputChange();
      const val = el.urlInput.value.trim();
      if (val && isYouTubeUrl(val)) {
        handleAnalyze();
      }
    }, 0);
  });

  // Keyboard controls: Ctrl+E or Escape instantly clears URL and below content
  el.urlInput.addEventListener("keydown", (e) => {
    if (((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "e") || e.key === "Escape") {
      e.preventDefault();
      el.urlInput.value = "";
      handleInputChange();
      resetResultsAndState();
      return;
    }
    if (e.key === "Enter") {
      clearTimeout(inputDebounceTimer);
      handleAnalyze();
    }
  });

  el.clearBtn.addEventListener("click", () => {
    el.urlInput.value = "";
    handleInputChange();
    resetResultsAndState();
    el.urlInput.focus();
  });

  el.pasteBtn.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        clearTimeout(inputDebounceTimer);
        el.urlInput.value = text.trim();
        handleInputChange();
        handleAnalyze();
      }
    } catch (e) {
      showToast("Clipboard access denied. Please paste manually (Ctrl+V).", "error");
    }
  });

  // Format Tabs (Video vs Audio)
  document.querySelectorAll(".picker-tabs .tab-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll(".picker-tabs .tab-btn").forEach((b) => b.classList.remove("active"));
      const target = e.currentTarget;
      target.classList.add("active");
      const tab = target.dataset.tab;
      if (tab === "video") {
        el.videoFormatsList.classList.remove("hidden");
        el.audioFormatsList.classList.add("hidden");
      } else {
        el.videoFormatsList.classList.add("hidden");
        el.audioFormatsList.classList.remove("hidden");
      }
    });
  });
}

function resetResultsAndState() {
  clearTimeout(inputDebounceTimer);
  if (el.videoResultCard) el.videoResultCard.classList.add("hidden");
  if (el.loadingSkeleton) el.loadingSkeleton.classList.add("hidden");
  state.currentVideo = null;
  state.lastAnalyzedUrl = "";
  setAnalyzingState(false);
  if (el.thumbBackdrop) {
    el.thumbBackdrop.classList.remove("active");
    setTimeout(() => {
      if (!state.currentVideo && el.thumbBackdrop) {
        el.thumbBackdrop.style.backgroundImage = "";
      }
    }, 700);
  }
}

function handleInputChange() {
  const val = el.urlInput.value.trim();
  const hasText = val.length > 0;
  if (hasText) {
    el.clearBtn.classList.remove("hidden");
    el.pasteBtn.classList.add("hidden");
  } else {
    el.clearBtn.classList.add("hidden");
    el.pasteBtn.classList.remove("hidden");
    // When input is cleared (Ctrl+E, backspace, delete), immediately hide below content
    resetResultsAndState();
  }
}

function normalizeYouTubeUrl(rawUrl) {
  if (!rawUrl) return "";
  const match = rawUrl.match(/(?:v=|\/|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})/);
  if (match && match[1]) {
    return `https://www.youtube.com/watch?v=${match[1]}`;
  }
  return rawUrl.trim();
}

function isYouTubeUrl(url) {
  if (!url) return false;
  const t = url.trim().toLowerCase();
  return (t.includes("youtube.com/") || t.includes("youtu.be/")) && /(?:v=|\/|youtu\.be\/|embed\/|shorts\/)[a-zA-Z0-9_-]{11}/.test(t);
}

// Auto-Load Everything when URL is provided
async function handleAnalyze() {
  let url = el.urlInput.value.trim();
  if (!url) {
    resetResultsAndState();
    return;
  }

  url = normalizeYouTubeUrl(url);

  if (!isYouTubeUrl(url)) {
    showToast("Please enter a valid YouTube video URL", "error");
    return;
  }

  if (state.isAnalyzing) return;
  state.isAnalyzing = true;
  state.lastAnalyzedUrl = url;

  // Show Skeleton loading state smoothly
  el.videoResultCard.classList.add("hidden");
  el.loadingSkeleton.classList.remove("hidden");
  setAnalyzingState(true);

  try {
    const res = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Unable to extract video details.");
    }

    const data = await res.json();
    state.currentVideo = data;
    renderVideoResult(data);
    // Success toast removed per user request (no success alerts, UI displays formats cleanly)
  } catch (err) {
    showToast(err.message || "Failed to load video formats", "error");
    state.lastAnalyzedUrl = "";
  } finally {
    el.loadingSkeleton.classList.add("hidden");
    setAnalyzingState(false);
  }
}

function setAnalyzingState(loading) {
  state.isAnalyzing = loading;
  if (el.inputSpinner) {
    el.inputSpinner.classList.toggle("hidden", !loading);
  }
  if (el.inputWrapper) {
    el.inputWrapper.classList.toggle("loading-pulse", loading);
  }
}

// Render Video Information & Formats
function renderVideoResult(data) {
  el.videoThumb.src = data.thumbnail || "";
  el.videoDuration.textContent = data.duration_formatted;
  el.videoViews.textContent = `${data.views} views`;
  el.videoDate.textContent = data.upload_date ? `Uploaded: ${data.upload_date}` : "";
  el.videoTitle.textContent = data.title;
  el.channelName.textContent = data.channel;
  el.channelAvatar.textContent = data.channel ? data.channel.charAt(0).toUpperCase() : "Y";

  // Dynamic Blurred Thumbnail Background
  if (data.thumbnail && el.thumbBackdrop) {
    el.thumbBackdrop.style.backgroundImage = `url("${data.thumbnail}")`;
    el.thumbBackdrop.classList.add("active");
  }

  el.previewThumbBtn.onclick = () => {
    window.open(data.url, "_blank");
  };

  // Render Video Formats
  el.videoFormatsList.innerHTML = "";
  if (data.video_formats && data.video_formats.length > 0) {
    data.video_formats.forEach((fmt) => {
      const row = document.createElement("div");
      row.className = "format-row";
      row.title = `Click to download ${fmt.label}`;

      let badgeClass = "badge-hd";
      if (fmt.height >= 2160) badgeClass = "badge-4k";
      else if (fmt.height >= 1440) badgeClass = "badge-2k";
      else if (fmt.height >= 1080) badgeClass = "badge-fhd";

      row.innerHTML = `
        <div class="format-left">
          <span class="quality-badge ${badgeClass}">${fmt.badge}</span>
          <span class="format-name">${fmt.label}</span>
        </div>
        <div class="format-right">
          <span class="format-size" data-orig="${fmt.filesize_formatted}">${fmt.filesize_formatted}</span>
        </div>
      `;

      row.addEventListener("click", () => {
        startDownload("video", fmt.height, fmt.format_id, "320", row);
      });

      el.videoFormatsList.appendChild(row);
    });
  } else {
    el.videoFormatsList.innerHTML = `<div class="empty-state"><p>No video formats found.</p></div>`;
  }

  // Render Audio Formats
  el.audioFormatsList.innerHTML = "";
  data.audio_formats.forEach((afmt) => {
    const row = document.createElement("div");
    row.className = "format-row";
    row.title = `Click to download MP3 (${afmt.label})`;
    row.innerHTML = `
      <div class="format-left">
        <span class="quality-badge badge-audio">${afmt.badge}</span>
        <span class="format-name">${afmt.label}</span>
      </div>
      <div class="format-right">
        <span class="format-size" data-orig="${afmt.filesize_formatted}">${afmt.filesize_formatted}</span>
      </div>
    `;

    row.addEventListener("click", () => {
      startDownload("audio", null, null, afmt.quality, row);
    });

    el.audioFormatsList.appendChild(row);
  });

  el.videoResultCard.classList.remove("hidden");
}

// Direct Download Process via WebSocket
function startDownload(type = "video", height = null, format_id = null, audio_quality = "320", triggerRow = null) {
  if (!state.currentVideo) return;
  if (state.isDownloading) {
    return;
  }

  state.isDownloading = true;
  state.activeRow = triggerRow;

  // Set row loading state
  if (triggerRow) {
    triggerRow.classList.add("downloading");
    const sizeEl = triggerRow.querySelector(".format-size");
    if (sizeEl) {
      sizeEl.innerHTML = `<span class="btn-spinner-sm"></span> <span>Starting...</span>`;
    }
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/download`;

  const ws = new WebSocket(wsUrl);
  state.socket = ws;

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        action: "start",
        url: state.currentVideo.url,
        type: type,
        height: height,
        format_id: format_id,
        audio_quality: audio_quality,
      })
    );
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleProgressEvent(data);
    } catch (e) {
      console.error("WS Parse error:", e);
    }
  };

  ws.onerror = (err) => {
    console.error("WS Error:", err);
    showToast("Connection error during download.", "error");
    resetActiveRow();
    state.isDownloading = false;
  };

  ws.onclose = () => {
    state.isDownloading = false;
  };
}

function handleProgressEvent(data) {
  if (data.status === "starting") {
    if (state.activeRow) {
      const sizeEl = state.activeRow.querySelector(".format-size");
      if (sizeEl) {
        sizeEl.innerHTML = `<span class="btn-spinner-sm"></span> <span>Connecting...</span>`;
      }
    }
  } else if (data.status === "downloading") {
    if (state.activeRow) {
      const pct = Math.min(Math.max(Math.round(data.percent || 0), 0), 99);
      const sizeEl = state.activeRow.querySelector(".format-size");
      if (sizeEl) {
        sizeEl.innerHTML = `<span class="btn-spinner-sm"></span> <span>${pct}%</span>`;
      }
    }
  } else if (data.status === "processing") {
    if (state.activeRow) {
      const sizeEl = state.activeRow.querySelector(".format-size");
      if (sizeEl) {
        sizeEl.innerHTML = `<span class="btn-spinner-sm"></span> <span>Muxing...</span>`;
      }
    }
  } else if (data.status === "completed") {
    state.isDownloading = false;

    // DIRECTLY INITIATE BROWSER FILE DOWNLOAD TO SYSTEM
    triggerSystemDownload(data.download_url, data.filename);

    if (state.activeRow) {
      const row = state.activeRow;
      row.classList.remove("downloading");
      row.classList.add("downloaded");
      const sizeEl = row.querySelector(".format-size");
      if (sizeEl) {
        sizeEl.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> <span>Downloaded!</span>`;
      }

      setTimeout(() => {
        if (row) {
          row.classList.remove("downloaded");
          const s = row.querySelector(".format-size");
          if (s) {
            s.textContent = s.dataset.orig || "";
          }
        }
      }, 2500);
      state.activeRow = null;
    }
  } else if (data.status === "error") {
    state.isDownloading = false;
    resetActiveRow();
    showToast(data.message || "Download failed", "error");
  }
}

function resetActiveRow() {
  if (state.activeRow) {
    state.activeRow.classList.remove("downloading", "downloaded");
    const sizeEl = state.activeRow.querySelector(".format-size");
    if (sizeEl) {
      sizeEl.textContent = sizeEl.dataset.orig || "";
    }
    state.activeRow = null;
  }
}

// Programmatically trigger native file download to user's system
function triggerSystemDownload(downloadUrl, filename) {
  try {
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.setAttribute("download", filename);
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    setTimeout(() => {
      link.remove();
    }, 200);
  } catch (err) {
    console.error("Auto-download trigger failed:", err);
  }
}

// Toast Notifications - ONLY for errors (Success/Info alerts suppressed per user requirement)
function showToast(message, type = "error") {
  if (type !== "error") return;

  const toast = document.createElement("div");
  toast.className = `toast error`;
  const iconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;

  toast.innerHTML = `${iconSvg}<span>${message}</span>`;
  el.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.25s ease";
    setTimeout(() => toast.remove(), 250);
  }, 3800);
}
