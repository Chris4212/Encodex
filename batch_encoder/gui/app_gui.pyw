"""
app_gui.pyw
-----------
Main application entry point for Batch Video Encoder GUI.

Integrates:
 - HomeTab     (workspace setup and system configuration)
 - ConfigTab   (global presets and per-file controls)
 - EncodeTab   (encoding dashboard and live monitor)

All visible text is now loaded from the central localization system.
"""

from __future__ import annotations
import os, sys, queue
import tkinter as tk
from tkinter import ttk, messagebox

from .gui_style import apply_dark_theme
from batch_encoder.core.controller import EncoderController
from batch_encoder.core.plugin_api import load_plugins
from batch_encoder.core.settings_manager import SettingsManager
from .localization import _

# Tabs
from .home_tab import HomeTab
from .config_tab import ConfigTab
from .encode_tab import EncodeTab


class EncoderGUI(tk.Tk):
    """Main window for the Batch Video Encoder application."""

    def __init__(self):
        super().__init__()
        self.title(_("app_title"))
        self.geometry("1380x900")
        self.configure(bg="#1e1e1e")
        self.minsize(1200, 800)

        # Style / theme
        self.style = ttk.Style(self)
        apply_dark_theme(self.style)

        # Core state
        self.print_q: queue.Queue = queue.Queue()
        self.settings = SettingsManager(persist=True)
        self.controller = EncoderController(self)

        # Plugin logger wrapper (adapts to plugin_api signature)
        def plugin_logger(message: str, worker: int | None = None, level: str = "info"):
            prefix = f"[W{worker}] " if worker is not None else ""
            self._log_line(prefix + message, level)

        self.controller.set_plugin_api(load_plugins(self._package_root_name(), plugin_logger))

        # Build tabs
        self._build_tabs()

        # Log initialization
        self._log_line(_("app_initialized"), "title")

        # Queue drain loop
        self.after(150, self._drain_print_queue)

        # Close event
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # --------------------- UI Setup ---------------------

    def _build_tabs(self):
        """Create the main tab structure."""
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)

        self.tab_home = HomeTab(self.tabs, self)
        self.tabs.add(self.tab_home, text=_("tab_home"))

        self.tab_config = ConfigTab(self.tabs, self)
        self.tabs.add(self.tab_config, text=_("tab_config"))

        self.tab_encode = EncodeTab(self.tabs, self)
        self.tabs.add(self.tab_encode, text=_("tab_encode"))

        self.tabs.select(0)

    # --------------------- Helper Methods ---------------------

    @staticmethod
    def _package_root_name() -> str:
        pkg = __package__ or ""
        return pkg.split(".")[0] if pkg else "batch_encoder"

    def _log_line(self, text: str, level="info"):
        """Central log output (redirected to Encode tab)."""
        if hasattr(self, "tab_encode"):
            self.tab_encode._log_line(text, level)
        else:
            print(text)

    # --------------------- Queue Drain ---------------------

    def _drain_print_queue(self):
        """Handle async messages from controller threads."""
        try:
            while True:
                item = self.print_q.get_nowait()
                kind = item[0]

                if kind == "log":
                    _, _, text, level = item
                    self._log_line(text, level)


                elif kind == "progress":
                    _, widx, name, pct = item[:4]
                    self._log_line(f"[DEBUG] Progress event W{widx}: {pct:.1f}% for {name}", "debug")
                    self.tab_encode.update_worker_bar(widx, pct)


                elif kind == "overall":
                    _, _, _, pct = item[:4]
                    self._log_line(f"[DEBUG] Overall progress: {pct:.1f}%", "debug")
                    self.tab_encode.set_overall_progress(pct)


                elif kind == "done":
                    _, widx = item
                    self.tab_encode.reset_worker_bar(widx)

        except queue.Empty:
            pass

        self.after(120, self._drain_print_queue)

    # --------------------- Event Handlers ---------------------

    def _on_close(self):
        """Graceful shutdown with safety checks."""
        if messagebox.askokcancel(_("confirm_exit_title"), _("confirm_exit")):
            try:
                self.controller.stop_all_processes()
            except Exception:
                pass
            self.destroy()

    # --------------------- Localization Reload ---------------------

    def reload_localized_texts(self, lang_code: str):
        """Reapply localized text across all tabs and window title."""
        try:
            self.title(_("app_title"))
            self.tabs.tab(0, text=_("tab_home"))
            self.tabs.tab(1, text=_("tab_config"))
            self.tabs.tab(2, text=_("tab_encode"))

            if hasattr(self, "tab_home"): self.tab_home.refresh_texts() if hasattr(self.tab_home, "refresh_texts") else None
            if hasattr(self, "tab_config"): self.tab_config.refresh_texts() if hasattr(self.tab_config, "refresh_texts") else None
            if hasattr(self, "tab_encode"): self.tab_encode.refresh_texts() if hasattr(self.tab_encode, "refresh_texts") else None

            self._log_line(_("app_lang_reload").format(lang=lang_code.upper()), "info")
        except Exception as e:
            print(f"[Localization] Failed to refresh UI: {e}")


# --------------------- Main Entry ---------------------

if __name__ == "__main__":
    base = os.path.abspath(os.path.dirname(__file__))
    sys.path.insert(0, base)
    app = EncoderGUI()
    app.mainloop()
