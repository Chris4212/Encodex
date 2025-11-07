"""
models.py
----------
Dataclasses and helper functions for encoding jobs.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class Job:
    """Represents a single encoding job with full metadata and runtime state."""

    def __init__(self, src: Path, dst: Path, rel: str, size: float):
        # Core file info
        self.src = Path(src)
        self.dst = Path(dst)
        self.rel = rel
        self.size = float(size)

        # Runtime/config fields
        self.settings: Dict[str, Any] = {}     # populated in prepare_session(); may be overridden by GUI
        self.stats: Dict[str, Any] = {}        # runtime or post-encode metrics
        self.use_smart: bool = True            # GUI toggle per file
        self.custom_target: str = ""           # optional new filename; GUI updates dst accordingly
        self.included: bool = True             # include in encode batch (checkbox)
        self.media_info: Dict[str, Any] = {}   # cached ffprobe info (single source of truth)

    def __repr__(self) -> str:
        try:
            return f"<Job {self.src.name} → {self.dst.name} ({self.size:.1f} MB)>"
        except Exception:
            # Fallback safe repr for logging if attributes are missing
            return f"<Job {getattr(self, 'src', '?')} → {getattr(self, 'dst', '?')}>"

    def key(self) -> str:
        """Stable job identity key across OS platforms."""
        try:
            st = self.src.stat()
            # Use absolute path to avoid issues with different relative paths
            abs_path = str(self.src.resolve())
            return f"{abs_path}|{int(st.st_size)}|{int(st.st_mtime)}"
        except Exception:
            return str(self.src)


# ----------------------------------------------------------------------
# Utility function (kept for backward compatibility)
# ----------------------------------------------------------------------

def job_key(j: Job) -> str:
    """
    Returns a unique key for a job, based on file path + size + modification time.
    Used internally for progress tracking and deduplication.
    """
    try:
        st = j.src.stat()
        return f"{j.rel}|{int(st.st_size)}|{int(st.st_mtime)}"
    except Exception:
        return j.rel
