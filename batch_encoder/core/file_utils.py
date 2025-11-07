"""
file_utils.py
-------------
Handles job discovery, file validation, and preparation before encoding.
All visible logs and error messages localized via the central locale system.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import List

from .models import Job
from .ffmpeg_utils import ffprobe_media_info
from .smart_mode import SmartOptimizer
from batch_encoder.gui.localization import _
from batch_encoder.config import SUPPORTED_EXTENSIONS
from batch_encoder.core.system_utils import is_windows, is_linux, is_macos


def _iter_media_files(in_dir: Path) -> List[Path]:
    """Recursively list all supported media files (case-insensitive)."""
    files: List[Path] = []
    exts = {e.lower() for e in SUPPORTED_EXTENSIONS}

    for root, _, names in os.walk(in_dir):
        for n in names:
            try:
                # Normalize Unicode filenames across OSes
                p = Path(root) / n
                if p.suffix.lower() in exts:
                    files.append(p)
            except Exception:
                continue

    return sorted(files, key=lambda x: str(x).lower())


def prepare_session(
    in_dir: Path,
    out_dir: Path,
    defaults_perf: dict,
    ui,  # UI object if you need defaults; may be ignored here
    smart_mode: bool = True,
) -> List[Job]:
    """
    Discover input files, PROBE EACH ONE ONCE, and prepare Job objects.

    Single source of truth:
      - `job.media_info` holds the full ffprobe dict
      - `job.stats["duration_s"]` and other normalized values live here
      - Smart Mode reads from that dict (analyze_info), no re-probe elsewhere
    """
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[WARN] Could not create output directory '{out_dir}': {e}")
        return []

    optimizer = SmartOptimizer()
    jobs: List[Job] = []

    files = _iter_media_files(in_dir)
    if not files:
        print(_("files_no_supported"))
        return jobs

    print(_("files_found").format(count=len(files)))

    for f in files:
        try:
            rel = f.relative_to(in_dir).as_posix()
            dst = (out_dir / rel).with_suffix(".mp4")

            # ---- PROBE ONCE ----
            info = ffprobe_media_info(f)

            duration_s = 0.0
            try:
                duration_s = float((info.get("format", {}) or {}).get("duration") or 0.0)
            except Exception:
                duration_s = 0.0

            try:
                size_mb = f.stat().st_size / (1024 * 1024)
            except Exception:
                size_mb = 0.0

            job = Job(src=f, dst=dst, rel=rel, size=size_mb)

            # Single source of truth attached to Job
            job.media_info = info
            job.stats["duration_s"] = duration_s

            # Baseline settings (can be overridden by Smart Mode)
            job.settings = {
                "scale_height": None,
                "vcodec": "libx265",
                "crf": "26",
                "preset": "medium",
                "pix_fmt": "yuv420p",
            }

            if smart_mode:
                # Consume pre-probed info
                analysis = optimizer.analyze_info(info)
                job.settings.update(analysis)
                job.settings["smart_details"] = analysis
                print(_("files_analyzed").format(name=f.name))
            else:
                # Even if Smart Mode is off, attach metrics for UI
                meta = optimizer._extract_metrics(info)
                job.settings["smart_details"] = {"metrics": {
                    "width": meta.get("width", 0),
                    "height": meta.get("height", 0),
                    "fps": meta.get("fps", 0.0),
                    "duration_s": meta.get("duration_s", 0.0),
                    "bitrate_mbps": meta.get("bitrate_mbps", 0.0),
                    "resolution": meta.get("resolution", "unknown"),
                }}

            jobs.append(job)

        except Exception as e:
            print(_("files_error_analyze").format(name=f.name, err=e))
            continue

    print(_("files_ready").format(count=len(jobs)))
    return jobs
