"""
app_gui.pyw
-----------
Main application entry point for Encodex GUI.

Integrates:
 - HomeTab     (workspace setup and system configuration)
 - ConfigTab   (global presets and per-file controls)
 - EncodeTab   (encoding dashboard and live monitor)

All visible text is localized via the central localization system.
"""

from __future__ import annotations
import os, sys, queue
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

from .gui_style import apply_dark_theme
from batch_encoder.core.controller import EncoderController
from batch_encoder.core.plugin_api import load_plugins
from batch_encoder.core.settings_manager import SettingsManager
from batch_encoder.core.system_utils import is_windows, is_linux, is_macos
from .localization import _

# Tabs
from .home_tab import HomeTab
from .config_tab import ConfigTab
from .encode_tab import EncodeTab


class EncoderGUI(tk.Tk):
    """Main window for the Encodex application."""

    def __init__(self):
        super().__init__()
        self.title(_("app_title"))
        self.geometry("1380x900")
        self.configure(bg="#1e1e1e")
        self.minsize(1200, 800)

        # --- Style / Theme ---
        self.style = ttk.Style(self)
        apply_dark_theme(self.style)

        # --- Core State ---
        self.print_q: queue.Queue = queue.Queue()
        self.settings = SettingsManager(persist=True)
        self.controller = EncoderController(self)

        # --- Plugin logger (adapts to plugin_api signature) ---
        def plugin_logger(message: str, worker: int | None = None, level: str = "info"):
            prefix = f"[W{worker}] " if worker is not None else ""
            self._log_line(prefix + message, level)

        self.controller.set_plugin_api(load_plugins(self._package_root_name(), plugin_logger))

        # --- Build Tabs ---
        self._build_tabs()

        # --- Log startup ---
        self._log_line(_("app_initialized"), "title")

        # --- Queue polling loop ---
        self.after(150, self._drain_print_queue)

        # --- Handle Close ---
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Linux/Mac: ensure DPI scaling doesn't break layout ---
        try:
            if is_linux() or is_macos():
                self.tk.call('tk', 'scaling', 1.0)
        except Exception:
            pass

    # --------------------- UI Setup ---------------------

    def _build_tabs(self):
        """Create the main tab structure."""
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)

        self.tab_home = HomeTab(self.tabs, self)
        self.tabs.add(self.tab_home, text=_("tab_home"))

        self.tab_config = ConfigTab(self.tabs, self)
        self.tabs.add(self.tab_config, text=_("tab_config"))

        self.encode_tab = EncodeTab(self.tabs, self)
        self.tabs.add(self.encode_tab, text=_("tab_encode"))

        self.tabs.select(0)

    # --------------------- Logging ---------------------

    @staticmethod
    def _package_root_name() -> str:
        pkg = __package__ or ""
        return pkg.split(".")[0] if pkg else "batch_encoder"

    def _log_line(self, text: str, level="info"):
        """Central log output (redirected to Encode tab)."""
        if hasattr(self, "encode_tab"):
            self.encode_tab._log_line(text, level)
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
                    self.encode_tab.update_worker_bar(widx, pct)

                elif kind == "overall":
                    _, _, _, pct = item[:4]
                    self.encode_tab.set_overall_progress(pct)

                elif kind == "worker_start":
                    try:
                        _, widx, job_name, _ = item
                    except Exception:
                        widx, job_name = None, "?"
                    if widx is not None:
                        self.encode_tab.reset_worker_bar(widx, job_name)

                elif kind == "done":
                    _, widx, job_name, _ = item
                    self.encode_tab.mark_worker_done(widx)

        except queue.Empty:
            pass

        # Continue polling
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

            # Refresh localized content if supported by tab
            if hasattr(self.tab_home, "refresh_texts"):
                self.tab_home.refresh_texts()
            if hasattr(self.tab_config, "refresh_texts"):
                self.tab_config.refresh_texts()
            if hasattr(self.encode_tab, "refresh_texts"):
                self.encode_tab.refresh_texts()

            self._log_line(_("app_lang_reload").format(lang=lang_code.upper()), "info")
        except Exception as e:
            print(f"[Localization] Failed to refresh UI: {e}")


# --------------------- Main Entry ---------------------

if __name__ == "__main__":
    # --- Ensure proper base path for imports ---
    base = Path(os.path.abspath(os.path.dirname(__file__)))
    root = base.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # --- Handle PyInstaller _MEIPASS path ---
    if hasattr(sys, "_MEIPASS"):
        os.chdir(sys._MEIPASS)

    # --- Launch GUI ---
    try:
        app = EncoderGUI()
        app.mainloop()
    except Exception as e:
        import traceback
        print("[FATAL] Application crashed:\n", traceback.format_exc())
