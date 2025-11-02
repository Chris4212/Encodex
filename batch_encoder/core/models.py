"""
Dataclasses and helper functions for encoding jobs.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

@dataclass
class Job:
    def __init__(self, src: Path, dst: Path, rel: str, size: float):
        self.src = Path(src)
        self.dst = Path(dst)
        self.rel = rel
        self.size = float(size)
        # runtime/config fields
        self.settings: Dict[str, Any] = {}     # populated in prepare_session(); may be overridden by GUI
        self.stats: Dict[str, Any] = {}        # runtime or post-encode metrics
        self.use_smart = True                  # GUI toggle per file
        self.custom_target = ""                # optional new filename (without path); GUI sets and updates dst
        self.included = True                   # included in encode batch (table checkbox)
        self.media_info: Dict[str, Any] = {}   # full ffprobe info, cached once


    def __repr__(self):
        return f"<Job {self.src.name} → {self.dst.name} ({self.size:.1f} MB)>"

def job_key(j: Job) -> str:
    st = j.src.stat()
    return f"{j.rel}|{st.st_size}|{int(st.st_mtime)}"
