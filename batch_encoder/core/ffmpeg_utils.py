"""
ffmpeg_utils.py
---------------
Helpers for building ffmpeg command lines and probing media information.
All ffprobe results are normalized for consistent reuse across the app.
"""

from __future__ import annotations
import subprocess, json, os, sys
from pathlib import Path
from typing import Dict, List, Any
from batch_encoder.config import RESOLUTION_OPTIONS

# ----------------------------------------------------------
# FFPROBE / FFMPEG PATH RESOLVER
# ----------------------------------------------------------

def get_ffmpeg_path(tool: str = "ffmpeg") -> str:
    """
    Resolve ffmpeg/ffprobe path in both:
      - Development mode (system PATH)
      - PyInstaller builds (inside _MEIPASS/bin/ffmpeg)
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidate = base / "bin" / "ffmpeg" / (f"{tool}.exe" if os.name == "nt" else tool)
    if candidate.exists():
        return str(candidate)
    return tool  # fallback to system PATH


# ----------------------------------------------------------
# FFPROBE WRAPPER
# ----------------------------------------------------------

def ffprobe_media_info(src: Path) -> Dict[str, Any]:
    """
    Probe a media file once and return normalized JSON info.

    Always returns a dict with at least:
      {
        "format": {"duration": float, "bit_rate": str, ...},
        "streams": [ { "codec_type": "video", "width": int, "height": int, ... } ]
      }

    Never raises: returns minimal safe fallback if ffprobe fails.
    """
    if not src or not Path(src).exists():
        return {"format": {"duration": 0.0}, "streams": []}

    # Resolved ffprobe path
    ffprobe_bin = get_ffmpeg_path("ffprobe")

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-show_entries",
        "format=duration,bit_rate:stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate",
        "-of", "json",
        str(src),
    ]

    # --- Suppress command windows on Windows ---
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    try:
        result = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags
        )
        info = json.loads(result)
    except subprocess.CalledProcessError as e:
        try:
            info = json.loads(e.output or "{}")
        except Exception:
            info = {}
    except Exception:
        info = {}

    # Normalize structure
    fmt = info.get("format", {}) or {}
    streams = info.get("streams", []) or []

    # ensure duration numeric
    try:
        fmt["duration"] = float(fmt.get("duration") or 0.0)
    except Exception:
        fmt["duration"] = 0.0

    # ensure bit_rate string (ffprobe can return int)
    try:
        br = fmt.get("bit_rate")
        if br is not None:
            fmt["bit_rate"] = str(br)
    except Exception:
        fmt["bit_rate"] = "0"

    # normalize streams
    norm_streams = []
    for s in streams:
        if s.get("codec_type") not in ("video", "audio"):
            continue
        norm = dict(s)
        for key in ("width", "height"):
            try:
                norm[key] = int(norm.get(key) or 0)
            except Exception:
                norm[key] = 0
        for key in ("avg_frame_rate", "r_frame_rate"):
            norm[key] = str(norm.get(key) or "0/1")
        norm_streams.append(norm)

    if not norm_streams:
        norm_streams = [{"codec_type": "video", "width": 0, "height": 0, "avg_frame_rate": "0/1"}]

    return {"format": fmt, "streams": norm_streams}


# ----------------------------------------------------------
# FFMPEG COMMAND BUILDER
# ----------------------------------------------------------

def build_ffmpeg_cmd(src: Path, dst: Path, settings: Dict[str, Any]) -> List[str]:
    """
    Build a clean ffmpeg command line using Job.settings.
    Handles both numeric `scale_height` and string `resolution`
    (e.g. "1080p", "4k", "source").
    """

    scale_h = settings.get("scale_height")
    resolution = settings.get("resolution")
    vcodec = settings.get("vcodec", settings.get("codec", "libx265"))
    crf = str(settings.get("crf", "26"))
    preset = settings.get("preset", "medium")
    pix_fmt = settings.get("pix_fmt", "yuv420p")
    threads = int(settings.get("CPU_CORES") or 2)
    extension = settings.get("extension", ".mp4")

    # Resolved ffmpeg binary
    ffmpeg_bin = get_ffmpeg_path("ffmpeg")

    # --- Ensure valid extension on output path ---
    if extension and not str(dst).lower().endswith(extension.lower()):
        dst = dst.with_suffix(extension)

    # --- Build filter ---
    vf = []
    if isinstance(resolution, str) and resolution.lower() != "source":
        flt = RESOLUTION_OPTIONS.get(resolution.lower(), "")
        if flt:
            vf.append(flt)
    elif scale_h:
        vf.append(f"scale=-2:{scale_h}")

    vf_filter = ",".join(vf) if vf else None

    # --- Assemble ffmpeg command ---
    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel", "error",  # controller may override later
        "-i", str(src),
    ]

    cmd += ["-threads", str(threads)]

    if vf_filter:
        cmd += ["-vf", vf_filter]

    cmd += [
        "-c:v", vcodec,
        "-crf", crf,
        "-preset", preset,
        "-pix_fmt", pix_fmt,
        "-c:a", "aac",
        "-b:a", "192k",
        str(dst),
    ]

    return cmd
