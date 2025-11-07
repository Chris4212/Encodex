"""
system_utils.py
---------------
Cross-platform system utilities used throughout Encodex.

Provides safe process management, FFmpeg path resolution, and
subprocess execution that behaves consistently on Windows, Linux, and macOS.
"""

from __future__ import annotations
import os, sys, subprocess, psutil
from pathlib import Path
from typing import List, Any


# ----------------------------------------------------------
# OS DETECTION
# ----------------------------------------------------------

def is_windows() -> bool:
    """Return True if running on Windows."""
    return os.name == "nt"


def is_linux() -> bool:
    """Return True if running on Linux."""
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    """Return True if running on macOS."""
    return sys.platform == "darwin"


# ----------------------------------------------------------
# FFmpeg PATH RESOLVER (works in PyInstaller too)
# ----------------------------------------------------------

def get_ffmpeg_path(tool: str = "ffmpeg") -> str:
    """
    Resolve ffmpeg/ffprobe path in both:
      - Dev mode (system PATH)
      - PyInstaller (inside _MEIPASS/bin/ffmpeg)
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidate = base / "bin" / "ffmpeg" / (f"{tool}.exe" if is_windows() else tool)
    if candidate.exists():
        return str(candidate)
    return tool  # fallback to system PATH


# ----------------------------------------------------------
# SAFE SUBPROCESS WRAPPERS
# ----------------------------------------------------------

def check_output_silent(cmd: List[str], **kwargs) -> str:
    """
    Wrapper for subprocess.check_output that suppresses Windows console flashing.
    Works transparently on Linux/macOS.
    """
    creationflags = safe_creation_flags()
    result = subprocess.check_output(
        cmd,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
        **kwargs,
    )
    return result


def safe_creation_flags() -> int:
    """
    Return subprocess creation flags that:
      - Hide console windows on Windows
      - Do nothing elsewhere
    """
    if is_windows():
        CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        return CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    return 0


# ----------------------------------------------------------
# PROCESS CONTROL HELPERS
# ----------------------------------------------------------

def suspend_process(pid: int) -> None:
    """Suspend a process (cross-platform via psutil)."""
    try:
        psutil.Process(pid).suspend()
    except Exception:
        pass


def resume_process(pid: int) -> None:
    """Resume a process (cross-platform via psutil)."""
    try:
        psutil.Process(pid).resume()
    except Exception:
        pass


def terminate_process_tree(pid: int, grace_seconds: float = 2.0) -> None:
    """
    Gracefully terminate a process and all its children.
    Works on Windows, Linux, and macOS using psutil.
    """
    try:
        parent = psutil.Process(pid)
    except Exception:
        return

    procs = [parent] + parent.children(recursive=True)
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass

    # Wait for graceful shutdown
    import time
    t_end = time.time() + grace_seconds
    while time.time() < t_end:
        if all(not p.is_running() for p in procs):
            return
        time.sleep(0.1)

    # Force kill leftovers
    for p in procs:
        try:
            if p.is_running():
                p.kill()
        except Exception:
            pass


# ----------------------------------------------------------
# 🔹 ADDITIONAL UTILITIES (for controller.py and diagnostics)
# ----------------------------------------------------------

def process_exists(pid: int) -> bool:
    """Return True if process is alive."""
    try:
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:
        return False


def ensure_executable_exists(tool: str) -> bool:
    """
    Quickly check if a given executable (ffmpeg, ffprobe, etc.)
    exists in PATH or PyInstaller bin directory.
    """
    from shutil import which
    path = get_ffmpeg_path(tool)
    if Path(path).exists():
        return True
    return which(tool) is not None


def current_platform() -> str:
    """Return normalized OS name string (Windows/Linux/macOS)."""
    if is_windows():
        return "Windows"
    if is_linux():
        return "Linux"
    if is_macos():
        return "macOS"
    return "Unknown"
