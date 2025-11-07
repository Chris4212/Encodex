"""
settings_manager.py
-------------------
Centralized, robust settings store.

Responsibilities:
- Load immutable defaults from config.py (system defaults)
- Maintain current session/user settings (codec, crf, preset, etc.)
- Provide a simple get/set API and full-dict exports for other modules
- (Optional) Persist user's last settings to JSON for the next run
"""

from __future__ import annotations
from pathlib import Path
import json, os, sys
from typing import Any, Dict

from batch_encoder import config
from batch_encoder.core.system_utils import is_windows, is_linux, is_macos


class SettingsManager:
    """
    Single source of truth for user/session settings.

    Layers:
      - System defaults (from config.py) -> immutable baseline
      - Session settings (mutable): what the GUI shows/edits
      - Optional persistence (user_settings.json) for next app launch
    """

    def __init__(self, persist: bool = True):
        self._persist = persist
        self._settings: Dict[str, Any] = self._load_defaults()
        self._settings_file = self._resolve_settings_path()
        if self._persist:
            self._load_user_file()

    # -------------------- Defaults --------------------

    def _load_defaults(self) -> Dict[str, Any]:
        """Load immutable defaults from config.py; form the baseline session settings."""
        return {
            # Language
            "language": getattr(config, "LANGUAGE_DEFAULT", "en"),

            # Paths
            "input_dir": str(config.TARGET_FOLDER_DEFAULT),
            "output_dir": str(config.OUTPUT_FOLDER_DEFAULT),

            # Encoding defaults
            "mode": config.MODE_DEFAULT,
            "codec": config.CODEC_DEFAULT,
            "crf": config.CRF_DEFAULT,
            "preset": config.PRESET_DEFAULT,
            "pix_fmt": config.PIX_FMT_DEFAULT,
            "resolution": config.RESOLUTION_DEFAULT,  # key like "source", "1080p"
            "goal": "balanced",
            "extension": ".mp4",

            # Performance
            "cpu_cores": config.CPU_CORES,
            "max_workers": config.MAX_WORKERS,
            "recursive": getattr(config, "RECURSIVE_SEARCH", True),
            "use_gpu": config.USE_GPU,

            # Smart Mode toggle
            "smart_mode_enabled": False,
        }

    # -------------------- Path Resolution --------------------

    def _resolve_settings_path(self) -> Path:
        """
        Determine where to store user_settings.json in a cross-platform way.
        - Windows: use config.STATE_FILE_DIR (AppData)
        - Linux/macOS: ~/.config/encodex or ~/.local/share/encodex
        - PyInstaller-safe
        """
        try:
            base = Path(config.STATE_FILE_DIR)
        except Exception:
            if is_windows():
                base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "Encodex"
            elif is_macos():
                base = Path.home() / "Library" / "Application Support" / "Encodex"
            else:
                base = Path.home() / ".config" / "Encodex"
        base.mkdir(parents=True, exist_ok=True)
        return base / "user_settings.json"

    # -------------------- Persistence --------------------

    def _load_user_file(self):
        """Load previously saved settings from JSON file (if it exists)."""
        try:
            if self._settings_file.exists():
                text = self._settings_file.read_text(encoding="utf-8", errors="ignore")
                data = json.loads(text)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if k in self._settings:
                            self._settings[k] = v
        except Exception:
            # Ignore corrupt or unreadable files
            pass

    def save_user_file(self):
        """Save current settings to disk, cross-platform safe."""
        if not self._persist:
            return
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            self._settings_file.write_text(
                json.dumps(self._settings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            # Non-fatal; just skip persistence errors
            pass

    # -------------------- Public API --------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._settings[key] = value

    def as_dict(self) -> Dict[str, Any]:
        """Return a shallow copy of all current settings."""
        return dict(self._settings)

    # -------------------- Convenience views --------------------

    def get_job_settings(self) -> Dict[str, Any]:
        """Return only the encoding-related settings used for job defaults."""
        return {
            "codec": self._settings["codec"],
            "crf": int(self._settings["crf"]),
            "preset": self._settings["preset"],
            "pix_fmt": self._settings["pix_fmt"],
            "resolution": self._settings["resolution"],  # still the *key*
        }

    def get_performance_settings(self) -> Dict[str, Any]:
        """Return only performance settings used by the controller."""
        return {
            "cpu_cores": int(self._settings["cpu_cores"]),
            "max_workers": int(self._settings["max_workers"]),
            "recursive": bool(self._settings["recursive"]),
        }
