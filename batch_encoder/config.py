"""
config.py
----------
Global configuration, presets, dropdown options, and system defaults.
This file is the immutable source of truth for *baseline* values only.
Mutable/session settings are managed by settings_manager.py
"""

import os
from pathlib import Path

# ------------------- LOCALIZATION -------------------
LANGUAGE_DEFAULT = "en"   # Default UI language
SUPPORTED_LANGUAGES = ["en"]  # Extend with "es", "fr", etc. as available

# ------------------- ENCODING DEFAULTS -------------------
MODE_DEFAULT = "balanced_cpu"

# Default folders (cross-platform safe)
TARGET_FOLDER_DEFAULT = Path.home().expanduser().resolve()
OUTPUT_FOLDER_DEFAULT = (Path.home() / "Encoded").expanduser().resolve()

# Global default encoding parameters
CODEC_DEFAULT = "libx265"
CRF_DEFAULT = 23
PRESET_DEFAULT = "medium"
PIX_FMT_DEFAULT = "yuv420p"
RESOLUTION_DEFAULT = "source"       # key in RESOLUTION_OPTIONS
RECURSIVE_SEARCH = True

# ------------------- HARDWARE DEFAULTS -------------------
# CPU & GPU baseline defaults
CPU_CORES = os.cpu_count() or 8
MAX_WORKERS = 2
USE_GPU = False  # Default off; NVENC is optional and requires NVIDIA on Linux/Windows

# ------------------- SMART MODE THRESHOLDS -------------------
CRF_LOW = 20
CRF_HIGH = 28
# Bitrate density thresholds (bitrate per pixel per frame)
BITRATE_DENSITY_HIGH = 0.00035
BITRATE_DENSITY_LOW = 0.00012

# ------------------- DYNAMIC PARALLELIZATION -------------------
CPU_LIMIT = 85      # % CPU above which we pause spawning
RAM_LIMIT = 90      # % RAM above which we pause spawning
SAMPLE_INTERVAL = 2 # seconds between load samples
CPU_RESUME = 60     # below this CPU we can resume more workers
RAM_RESUME = 75     # below this RAM we can resume more workers

# ------------------- RECOVERY SYSTEM -------------------
RETRY_LIMIT = 3
DURATION_TOLERANCE = 0.9  # output duration must be ≥ 90% of source
BACKUP_STATE_COUNT = 5    # keep 5 last state backups

# ------------------- CORE PATHS / STATE -------------------
ROOT_DIR = Path(__file__).resolve().parent
STATE_FILE_DIR = ROOT_DIR / "state"
STATE_FILE = "encode_state.json"

# ------------------- SUPPORTED EXTENSIONS -------------------
SUPPORTED_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v",
    ".mpg", ".mpeg", ".ts", ".m2ts", ".wmv", ".3gp", ".vob", ".f4v", ".divx"
}

# -----------------------------------------------------------------
# ENCODING GOALS (INTENT)
# -----------------------------------------------------------------
ENCODING_GOALS = {
    "speed": {
        "label": "High Speed",
        "desc":  "Prioritize fast encodes. Larger output, slightly lower quality.",
        "policy": {
            "target": "speed",
            "allow_downscale": True,
            "prefer_family": "h264",
            "crf_delta": +2,
            "preset": "superfast",
            "force_pix_fmt": "yuv420p",
        },
    },
    "balanced": {
        "label": "Balanced",
        "desc":  "Good balance between quality, compression, and speed.",
        "policy": {
            "target": "balanced",
            "allow_downscale": True,
            "prefer_family": "hevc",
            "crf_delta": 0,
            "preset": "medium",
            "force_pix_fmt": None,
        },
    },
    "quality": {
        "label": "High Quality",
        "desc":  "Focus on visual detail; slower encoding, larger file.",
        "policy": {
            "target": "quality",
            "allow_downscale": False,
            "prefer_family": "hevc",
            "crf_delta": -2,
            "preset": "slow",
            "force_pix_fmt": None,
        },
    },
    "archive": {
        "label": "Archival Quality",
        "desc":  "Maximum preservation; slower encode; ideal for long-term storage.",
        "policy": {
            "target": "archive",
            "allow_downscale": False,
            "prefer_family": "av1",  # Try AV1 if available
            "crf_delta": -4,
            "preset": "slower",
            "force_pix_fmt": "yuv420p10le",
        },
    },
    "storage": {
        "label": "Storage Saver",
        "desc":  "Aggressively reduce file size; may visibly reduce quality.",
        "policy": {
            "target": "size",
            "allow_downscale": True,
            "prefer_family": "hevc",
            "crf_delta": +4,
            "preset": "fast",
            "force_pix_fmt": "yuv420p",
        },
    },
    "web": {
        "label": "Web/Streaming",
        "desc":  "H.264, yuv420p for maximum playback compatibility.",
        "policy": {
            "target": "compat",
            "allow_downscale": True,
            "prefer_family": "h264",
            "crf_delta": +1,
            "preset": "medium",
            "force_pix_fmt": "yuv420p",
        },
    },
    "mobile": {
        "label": "Mobile/Low Bandwidth",
        "desc":  "Compress and downscale for small screens and low speeds.",
        "policy": {
            "target": "mobile",
            "allow_downscale": True,
            "prefer_family": "hevc",
            "crf_delta": +5,
            "preset": "faster",
            "force_pix_fmt": "yuv420p",
        },
    },
    "lossless": {
        "label": "Near-Lossless",
        "desc":  "Preserve maximum detail; minimal compression; huge files.",
        "policy": {
            "target": "lossless",
            "allow_downscale": False,
            "prefer_family": "hevc",
            "crf_delta": -10,
            "preset": "slow",
            "force_pix_fmt": None,
        },
    },
    "transcode": {
        "label": "Re-encode Only",
        "desc":  "Normalize or repair file structure without re-tuning quality.",
        "policy": {
            "target": "neutral",
            "allow_downscale": False,
            "prefer_family": "hevc",
            "crf_delta": 0,
            "preset": "medium",
            "force_pix_fmt": None,
        },
    }
}

# ------------------- DROPDOWN OPTIONS -------------------
CODEC_CHOICES = [
    ("libx264", "Very compatible, CPU H.264"),
    ("libx265", "Better compression, CPU HEVC"),
    ("h264_nvenc", "NVIDIA GPU H.264"),
    ("hevc_nvenc", "NVIDIA GPU HEVC"),
    ("av1_nvenc", "NVIDIA GPU AV1 (Ampere+)"),
    ("libvpx-vp9", "Open-source VP9"),
    ("libaom-av1", "CPU AV1 (slow)"),
]

PIX_FMT_CHOICES = [
    ("yuv420p", "Default, most compatible"),
    ("yuv422p", "Higher color fidelity"),
    ("yuv444p", "Full chroma resolution"),
    ("yuv420p10le", "10-bit HDR workflows"),
]

PRESET_OPTIONS = [
    "ultrafast","superfast","veryfast","faster",
    "fast","medium","slow","slower","veryslow"
]

# NOTE: all keys lowercase and used as *keys* in UI/SettingsManager
RESOLUTION_OPTIONS = {
    "source": "",
    "480p": "scale=-2:480",
    "720p": "scale=-2:720",
    "1080p": "scale=-2:1080",
    "1440p": "scale=-2:1440",
    "4k": "scale=-2:2160",
    "8k": "scale=-2:4320",
}

# ------------------- WINDOWS POPUP SUPPRESSION -------------------
if os.name == "nt":
    # Hide cmd window when launching subprocesses
    CREATE_NO_WINDOW = 0x08000000
    CREATE_NEW_PROCESS_GROUP = 0x00000200
else:
    CREATE_NO_WINDOW = 0
    CREATE_NEW_PROCESS_GROUP = 0
