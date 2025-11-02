"""
plugin_api.py
-------------
Handles discovery and registration of user plugins.
Provides hooks for extending the encoder pipeline.
All logging text is localized.
"""

from __future__ import annotations
from importlib import import_module
from pathlib import Path
from typing import Callable
from batch_encoder.gui.localization import _


class PluginAPI:
    """Interface exposed to plugins for registration."""

    def __init__(self, log_fn: Callable[[str, int | None, str], None]):
        self.log_fn = log_fn
        self.hooks = {
            "before_encode": [],
            "after_encode": [],
            "modify_settings": [],
        }

        # ------------------------------------------------------------------
        # Backward-compatible helper methods for older plugins
        # ------------------------------------------------------------------
        self.on_before_encode = lambda func: self.register("before_encode", func)
        self.on_encode_finished = lambda func: self.register("after_encode", func)
        self.on_modify_settings = lambda func: self.register("modify_settings", func)

    # -------------------------------------------------------

    def log(self, message: str, level: str = "info"):
        """
        Simple logger method exposed to plugins (for backward compatibility).
        Plugins may call api.log("text", level="success"/"warn"/"error").
        """
        try:
            self.log_fn(message, None, level)
        except Exception:
            pass

    # -------------------------------------------------------

    def register(self, hook_name: str, func: Callable):
        """Register a plugin hook."""
        if hook_name not in self.hooks:
            self.log_fn(_("plugin_invalid_hook").format(hook=hook_name), None, "warn")
            return
        self.hooks[hook_name].append(func)
        # Show the function name if available, otherwise repr
        name = getattr(func, "__name__", repr(func))
        self.log_fn(_("plugin_registered").format(hook=hook_name, name=name), None, "info")

    # -------------------------------------------------------

    def trigger(self, hook_name: str, *args, **kwargs):
        """Trigger a registered hook."""
        funcs = self.hooks.get(hook_name, [])
        for f in funcs:
            try:
                f(*args, **kwargs)
            except Exception as e:
                self.log_fn(_("plugin_hook_error").format(hook=hook_name, err=e), None, "error")


# -------------------------------------------------------
# Plugin discovery
# -------------------------------------------------------

def load_plugins(package_root: str, logger: Callable[[str, int | None, str], None]):
    """
    Discover and load all plugins in f"{package_root}.plugins".
    Returns a PluginAPI instance with hooks wired.
    """
    api = PluginAPI(log_fn=logger)
    pkg = package_root + ".plugins"

    try:
        base = Path(import_module(package_root).__file__).parent / "plugins"
    except Exception:
        logger(_("plugin_dir_resolve_error"), None, "warn")
        return api

    if not base.exists():
        logger(_("plugin_no_dir"), None, "info")
        return api

    for file in sorted(base.glob("*.py")):
        if file.name == "__init__.py":
            continue
        mod_name = f"{pkg}.{file.stem}"
        try:
            mod = import_module(mod_name)
            if hasattr(mod, "register_plugin"):
                mod.register_plugin(api)
                logger(_("plugin_loaded").format(name=file.stem), None, "info")
            else:
                logger(_("plugin_skipped").format(name=file.stem), None, "warn")
        except Exception as e:
            logger(_("plugin_failed").format(name=file.stem, err=e), None, "error")
    return api
