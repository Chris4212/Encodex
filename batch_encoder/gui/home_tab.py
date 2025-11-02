"""
home_tab.py
-----------
Home tab for Batch Video Encoder GUI.
Handles workspace setup, directory selection, system resources, and general settings.
All text is localized via the central locale system.
"""

from __future__ import annotations
import os, threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

try:
    import psutil
    PSUTIL_AVAILABLE = True
except Exception:
    PSUTIL_AVAILABLE = False

from batch_encoder.core.file_utils import prepare_session
from batch_encoder.core.models import Job
from .localization import _, Localizer
from .. import config


# ------------------- Tooltip -------------------

class ToolTip:
    """Lightweight tooltip utility; dark style, consistent across tabs."""
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#2a2a2a",
            foreground="#e0e0e0",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=6,
            wraplength=320,
        )
        lbl.pack()

    def _hide(self, _=None):
        if self.tip:
            try:
                self.tip.destroy()
            except Exception:
                pass
        self.tip = None


# ------------------- System Resources Dialog -------------------

class SystemResourcesDialog(tk.Toplevel):
    """Popup for advanced system resource configuration."""

    def __init__(self, master, settings):
        super().__init__(master)
        self.title(_("home_configure_system"))
        self.configure(bg="#1e1e1e")
        self.settings = settings
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        self.var_dynamic = tk.BooleanVar(value=self.settings.get("dynamic_allocation", True))
        self.var_cores = tk.IntVar(value=self.settings.get("cpu_cores", config.CPU_CORES))
        self.var_workers = tk.IntVar(value=self.settings.get("max_workers", config.MAX_WORKERS))
        self.var_io = tk.BooleanVar(value=self.settings.get("io_throttle", False))
        self.var_priority = tk.StringVar(value=self.settings.get("priority_mode", "normal"))
        self.var_ram = tk.IntVar(value=self.settings.get("ram_limit", 90))

        ttk.Checkbutton(frm, text=_("sys_dynamic"),
                        variable=self.var_dynamic, command=self._toggle_state).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0,8))
        ToolTip(frm, _("home_tool_system"))

        ttk.Label(frm, text=_("sys_cores")).grid(row=1, column=0, sticky="e", pady=4)
        cores = [i for i in range(1, (psutil.cpu_count(logical=True) if PSUTIL_AVAILABLE else 8) + 1)]
        self.cmb_cores = ttk.Combobox(frm, values=cores, textvariable=self.var_cores, state="readonly", width=6)
        self.cmb_cores.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(frm, text=_("sys_workers")).grid(row=2, column=0, sticky="e", pady=4)
        self.cmb_workers = ttk.Combobox(frm, values=[1,2,3,4,5,6,7,8], textvariable=self.var_workers,
                                        state="readonly", width=6)
        self.cmb_workers.grid(row=2, column=1, sticky="w", pady=4)

        ttk.Checkbutton(frm, text=_("sys_io_limit"), variable=self.var_io).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)

        ttk.Label(frm, text=_("sys_priority")).grid(row=4, column=0, sticky="e", pady=4)
        modes = [("Normal", "normal"), ("Background", "low"), ("High", "high")]
        sub = ttk.Frame(frm); sub.grid(row=4, column=1, sticky="w", pady=4)
        for txt, val in modes:
            ttk.Radiobutton(sub, text=txt, value=val, variable=self.var_priority).pack(side="left", padx=4)

        ttk.Label(frm, text=_("sys_ram_limit")).grid(row=5, column=0, sticky="e", pady=4)
        self.spin_ram = ttk.Spinbox(frm, from_=50, to=99, textvariable=self.var_ram, width=6)
        self.spin_ram.grid(row=5, column=1, sticky="w", pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, pady=(12,0))
        ttk.Button(btns, text=_("sys_restore"), command=self._restore_defaults).pack(side="left", padx=6)
        ttk.Button(btns, text=_("sys_apply"), command=self._apply).pack(side="left", padx=6)
        ttk.Button(btns, text=_("sys_cancel"), command=self.destroy).pack(side="left", padx=6)

        self._toggle_state()

    def _toggle_state(self):
        state = "disabled" if self.var_dynamic.get() else "readonly"
        for widget in (self.cmb_cores, self.cmb_workers, self.spin_ram):
            widget.configure(state=state)

    def _restore_defaults(self):
        self.var_dynamic.set(True)
        self.var_cores.set(config.CPU_CORES)
        self.var_workers.set(config.MAX_WORKERS)
        self.var_io.set(False)
        self.var_priority.set("normal")
        self.var_ram.set(90)

    def _apply(self):
        self.settings.set("dynamic_allocation", self.var_dynamic.get())
        self.settings.set("cpu_cores", self.var_cores.get())
        self.settings.set("max_workers", self.var_workers.get())
        self.settings.set("io_throttle", self.var_io.get())
        self.settings.set("priority_mode", self.var_priority.get())
        self.settings.set("ram_limit", self.var_ram.get())
        self.settings.save_user_file()
        self.destroy()


# ------------------- Home Tab -------------------

class HomeTab(ttk.Frame):
    """Main entry tab: workspace setup and system options."""

    def __init__(self, master, main_app):
        super().__init__(master)
        self.main_app = main_app
        self.settings = main_app.settings
        self.controller = main_app.controller
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        row = 0

        # --- Directories section ---
        box_dirs = ttk.LabelFrame(self, text=_("home_directories"))
        box_dirs.grid(row=row, column=0, sticky="ew", padx=12, pady=(12, 6))
        box_dirs.columnconfigure(1, weight=1)
        box_dirs.columnconfigure(4, weight=1)

        ttk.Label(box_dirs, text=_("home_target_dir")).grid(row=0, column=0, sticky="w", padx=(8,6), pady=6)
        self.var_target = tk.StringVar(value=self.settings.get("input_dir"))
        ent_target = ttk.Entry(box_dirs, textvariable=self.var_target)
        ent_target.grid(row=0, column=1, sticky="ew", padx=(0,6), pady=6)
        btn_target = ttk.Button(box_dirs, text=_("home_browse"), command=self._browse_target)
        btn_target.grid(row=0, column=2, padx=(0,8), pady=6)
        ToolTip(ent_target, _("home_tool_target"))
        ToolTip(btn_target, _("home_tool_target"))

        ttk.Label(box_dirs, text=_("home_output_dir")).grid(row=1, column=0, sticky="w", padx=(8,6), pady=6)
        self.var_output = tk.StringVar(value=self.settings.get("output_dir"))
        ent_output = ttk.Entry(box_dirs, textvariable=self.var_output)
        ent_output.grid(row=1, column=1, sticky="ew", padx=(0,6), pady=6)
        btn_output = ttk.Button(box_dirs, text=_("home_browse"), command=self._browse_output)
        btn_output.grid(row=1, column=2, padx=(0,8), pady=6)
        ToolTip(ent_output, _("home_tool_output"))
        ToolTip(btn_output, _("home_tool_output"))

        btn_refresh = ttk.Button(box_dirs, text=_("home_refresh"), command=self._manual_refresh)
        btn_refresh.grid(row=2, column=1, sticky="w", padx=(0,6), pady=(4,8))
        ToolTip(btn_refresh, _("home_tool_refresh"))
        btn_open = ttk.Button(box_dirs, text=_("home_open_output"), command=self._open_output)
        btn_open.grid(row=2, column=2, sticky="e", padx=(0,8), pady=(4,8))
        ToolTip(btn_open, _("home_tool_output_open"))

        # --- System Resources ---
        row += 1
        box_sys = ttk.LabelFrame(self, text=_("home_system"))
        box_sys.grid(row=row, column=0, sticky="ew", padx=12, pady=(6, 6))
        btn_sys = ttk.Button(box_sys, text=_("home_configure_system"), command=self._open_resource_config)
        btn_sys.grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ToolTip(btn_sys, _("home_tool_system"))

        # --- General Settings ---
        row += 1
        box_gen = ttk.LabelFrame(self, text=_("home_general"))
        box_gen.grid(row=row, column=0, sticky="ew", padx=12, pady=(6, 12))
        self.var_autofetch = tk.BooleanVar(value=self.settings.get("auto_fetch", True))
        self.var_keep_logs = tk.BooleanVar(value=self.settings.get("keep_logs", True))
        self.var_notify = tk.BooleanVar(value=self.settings.get("notify_on_complete", False))

        chk_autofetch = ttk.Checkbutton(box_gen, text=_("home_auto_fetch"),
                                        variable=self.var_autofetch,
                                        command=lambda: self._update_setting("auto_fetch", self.var_autofetch.get()))
        chk_autofetch.grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ToolTip(chk_autofetch, _("home_tool_auto_fetch"))

        chk_keep = ttk.Checkbutton(box_gen, text=_("home_keep_logs"),
                                   variable=self.var_keep_logs,
                                   command=lambda: self._update_setting("keep_logs", self.var_keep_logs.get()))
        chk_keep.grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ToolTip(chk_keep, _("home_tool_keep_logs"))

        chk_notify = ttk.Checkbutton(box_gen, text=_("home_notify"),
                                     variable=self.var_notify,
                                     command=lambda: self._update_setting("notify_on_complete", self.var_notify.get()))
        chk_notify.grid(row=2, column=0, sticky="w", padx=8, pady=4)
        ToolTip(chk_notify, _("home_tool_notify"))

        # Language selection
        langs = ["English"]
        self.var_lang = tk.StringVar(value=self.settings.get("language", "en"))
        ttk.Label(box_gen, text=_("home_language")).grid(row=3, column=0, sticky="w", padx=8, pady=(8,4))
        cmb_lang = ttk.Combobox(box_gen, textvariable=self.var_lang,
                                values=langs, state="readonly", width=20)
        cmb_lang.grid(row=3, column=1, sticky="w", padx=8, pady=(8,4))
        cmb_lang.bind("<<ComboboxSelected>>", self._on_language_change)
        ToolTip(cmb_lang, _("home_tool_language"))

    # ---------------- Logic ----------------

    def _update_setting(self, key, value):
        self.settings.set(key, value)
        self.settings.save_user_file()

    def _browse_target(self):
        d = filedialog.askdirectory(initialdir=self.var_target.get() or str(Path.home()))
        if d:
            self.var_target.set(d)
            self.settings.set("input_dir", d)
            self.settings.save_user_file()
            if self.var_autofetch.get():
                self._fetch_jobs_background(Path(d), Path(self.var_output.get()))

    def _browse_output(self):
        d = filedialog.askdirectory(initialdir=self.var_output.get() or str(Path.home()))
        if d:
            self.var_output.set(d)
            self.settings.set("output_dir", d)
            self.settings.save_user_file()

    def _manual_refresh(self):
        target = Path(self.var_target.get())
        out = Path(self.var_output.get())
        if not target.exists():
            messagebox.showerror(_("error_invalid_target"), _("error_invalid_target"))
            return
        self._fetch_jobs_background(target, out)

    def _open_output(self):
        out = Path(self.var_output.get())
        if not out.exists():
            messagebox.showerror(_("error_invalid_output"), _("error_invalid_output"))
            return
        try:
            os.startfile(out)
        except Exception:
            messagebox.showerror(_("error_invalid_output"), f"{out}")

    def _open_resource_config(self):
        SystemResourcesDialog(self, self.settings)

    # ----- Background Fetch -----

    def _fetch_jobs_background(self, in_dir: Path, out_dir: Path):
        defaults_perf = self.settings.get_performance_settings()
        ui = self.settings.get_job_settings()
        smart = self.settings.get("smart_mode_enabled", True)

        def worker():
            try:
                jobs = prepare_session(in_dir, out_dir, defaults_perf, ui, smart_mode=smart)
                self.after(0, self._on_fetch_complete, jobs)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Fetch Failed", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetch_complete(self, jobs: list[Job]):
        if not jobs:
            messagebox.showwarning(_("warn_no_jobs_found"), _("warn_no_jobs_found"))
            return

        if hasattr(self.main_app, "tab_config"):
            # Populate the upper file list
            self.main_app.tab_config.populate_jobs(jobs)

            # Refresh the Encode Impact Preview (bottom list)
            if hasattr(self.main_app.tab_config, "_refresh_impact_preview"):
                self.main_app.tab_config._refresh_impact_preview(jobs)

        else:
            messagebox.showinfo(_("config_info"), f"{len(jobs)} " + _("config_no_jobs"))

    # ----- Language -----

    def _on_language_change(self, event=None):
        selected = self.var_lang.get().lower().strip()
        lang_map = {"english": "en"}
        lang_code = lang_map.get(selected, "en")

        self.settings.set("language", lang_code)
        self.settings.save_user_file()

        try:
            loc = Localizer()
            loc.load_language(lang_code)
            self._notify_language_reload(lang_code)
        except Exception as e:
            messagebox.showerror("Language Error", f"Failed to load language '{lang_code}': {e}")

    def _notify_language_reload(self, lang_code: str):
        self.main_app._log_line(f"Language switched to {lang_code.upper()}", "info")
        if hasattr(self.main_app, "reload_localized_texts"):
            self.main_app.reload_localized_texts(lang_code)
