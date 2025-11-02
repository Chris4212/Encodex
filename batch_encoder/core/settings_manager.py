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
import json
from typing import Any, Dict

from batch_encoder import config


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
        self._settings_file = Path(config.STATE_FILE_DIR) / "user_settings.json"
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

            # Encoding defaults (what GUI shows initially)
            "mode": config.MODE_DEFAULT,
            "codec": config.CODEC_DEFAULT,
            "crf": config.CRF_DEFAULT,
            "preset": config.PRESET_DEFAULT,
            "pix_fmt": config.PIX_FMT_DEFAULT,
            "resolution": config.RESOLUTION_DEFAULT,   # key like "source", "1080p"
            "goal": "balanced",
            "extension": ".mp4",

            # Performance
            "cpu_cores": config.CPU_CORES,
            "max_workers": config.MAX_WORKERS,
            "recursive": getattr(config, "RECURSIVE_SEARCH", True),
            "use_gpu": config.USE_GPU,

            # Smart Mode toggle (per-session global default)
            "smart_mode_enabled": False,
        }

    # -------------------- Persistence --------------------

    def _load_user_file(self):
        try:
            if self._settings_file.exists():
                data = json.loads(self._settings_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Only update keys we recognize (ignore unknown keys)
                    for k, v in data.items():
                        if k in self._settings:
                            self._settings[k] = v
        except Exception:
            # Corrupt settings are ignored; we continue with defaults
            pass

    def save_user_file(self):
        if not self._persist:
            return
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            self._settings_file.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")
        except Exception:
            # Non-fatal; just skip persistence errors
            pass

    # -------------------- Public API --------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if value == "as-is":
            return  # skip writing, user left it unchanged
        self._settings[key] = value

    def as_dict(self) -> Dict[str, Any]:
        """Return a shallow copy of all current settings."""
        return dict(self._settings)

    # Convenient views used by prepare_session/controller
    def get_job_settings(self) -> Dict[str, Any]:
        """Return only the encoding-related settings used for job defaults."""
        return {
            "codec": self._settings["codec"],
            "crf": int(self._settings["crf"]),
            "preset": self._settings["preset"],
            "pix_fmt": self._settings["pix_fmt"],
            "resolution": self._settings["resolution"],  # still the *key* (e.g., "source")
        }

    def get_performance_settings(self) -> Dict[str, Any]:
        """Return only performance settings used by the controller."""
        return {
            "cpu_cores": int(self._settings["cpu_cores"]),
            "max_workers": int(self._settings["max_workers"]),
            "recursive": bool(self._settings["recursive"]),
        }
