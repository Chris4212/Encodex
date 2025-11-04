"""
localization.py
Centralized localization manager for Batch Video Encoder.
Loads text resources based on current language setting.
Compatible with both source and PyInstaller-frozen builds.
"""

import sys
import importlib.util
from pathlib import Path
from ..core.settings_manager import SettingsManager
from .. import config


class Localizer:
    _instance = None

    def __new__(cls, lang: str | None = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lang = lang or cls._detect_language()
            cls._instance._texts = {}
            cls._instance.load_language(cls._instance._lang)
        return cls._instance

    @staticmethod
    def _detect_language() -> str:
        """Try to detect user language via SettingsManager; fallback to config default."""
        try:
            sm = SettingsManager()
            lang = sm.get("language")
            if lang:
                return lang
        except Exception:
            pass
        try:
            return getattr(config, "LANGUAGE_DEFAULT", "en")
        except Exception:
            return "en"

    def load_language(self, lang: str):
        """Load locale module dynamically (handles PyInstaller frozen builds)."""
        try:
            # Determine base path (normal or frozen exe)
            base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
            locale_file = base_dir / "locales" / f"{lang}.py"

            if locale_file.exists():
                spec = importlib.util.spec_from_file_location(lang, locale_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._texts = getattr(module, "TEXT", {})
                self._lang = lang
                return

            # Fallback: try regular import (dev environment)
            from importlib import import_module
            module = import_module(f".locales.{lang}", package="batch_encoder")
            self._texts = getattr(module, "TEXT", {})
            self._lang = lang

        except Exception as e:
            print(f"[Localization] Failed to load language '{lang}': {e}")
            self._texts = {}
            self._lang = "en"

    def reload(self):
        """Reload currently active language (useful after user changes it)."""
        self.load_language(self._lang)

    def get(self, key: str, **kwargs) -> str:
        """Return localized string with optional format substitutions."""
        text = self._texts.get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except Exception:
                pass
        return text


# Singleton accessor for global translations
_ = Localizer().get
