"""
encode_tab.py
-------------
Encoding dashboard with per-worker progress bars and duration-weighted overall progress.
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import psutil, time, queue, threading
from batch_encoder.core.system_utils import is_windows, is_linux, is_macos
from .localization import _


class EncodeTab(ttk.Frame):
    """Main encoding dashboard with controls, monitor, progress, and logs."""

    def __init__(self, master, main_app):
        super().__init__(master)
        self.main_app = main_app
        self.settings = main_app.settings
        self.controller = main_app.controller
        self.print_q: queue.Queue = main_app.print_q
        self.running = False
        self._build_ui()
        self._start_system_monitor()

    # -------------------- UI --------------------

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self._build_controls_section()
        self._build_monitor_section()
        self._build_progress_section()
        self._build_log_section()

    def _build_controls_section(self):
        box = ttk.LabelFrame(self, text=_("encode_controls"))
        box.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self.btn_start = ttk.Button(box, text=_("encode_start"), command=self._on_start)
        self.btn_start.grid(row=0, column=0, padx=8, pady=8)
        self.btn_pause = ttk.Button(box, text=_("encode_pause"), command=self._on_pause)
        self.btn_pause.grid(row=0, column=1, padx=8, pady=8)
        self.btn_stop = ttk.Button(box, text=_("encode_stop"), command=self._on_stop)
        self.btn_stop.grid(row=0, column=2, padx=8, pady=8)

    def _build_monitor_section(self):
        box = ttk.LabelFrame(self, text=_("encode_monitor"))
        box.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        box.columnconfigure(3, weight=1)

        self.var_cpu = tk.StringVar(value=_("encode_cpu").format(val="--"))
        self.var_ram = tk.StringVar(value=_("encode_ram").format(val="--"))
        self.var_disk = tk.StringVar(value=_("encode_disk").format(val="--"))

        ttk.Label(box, textvariable=self.var_cpu).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Label(box, textvariable=self.var_ram).grid(row=0, column=1, sticky="w", padx=8, pady=6)
        ttk.Label(box, textvariable=self.var_disk).grid(row=0, column=2, sticky="w", padx=8, pady=6)
        self.pb_cpu = ttk.Progressbar(box, mode="determinate", length=300,
                                      style="Dark.Horizontal.TProgressbar")
        self.pb_cpu.grid(row=0, column=3, sticky="e", padx=8, pady=6)

    def _build_progress_section(self):
        box = ttk.LabelFrame(self, text=_("encode_progress"))
        box.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text=_("encode_worker_progress")).grid(
            row=0, column=0, sticky="w", padx=8, pady=(4, 2)
        )
        self.worker_bars = {}
        self._progress_box = box

        ttk.Label(box, text=_("encode_overall_progress")).grid(
            row=999, column=0, sticky="w", padx=8, pady=(10, 4)
        )
        self.pb_overall = ttk.Progressbar(
            box, mode="determinate", length=600,
            style="Dark.Horizontal.TProgressbar", maximum=100,
        )
        self.pb_overall.grid(row=1000, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 8))
        self.var_overall = tk.StringVar(value="0%")
        ttk.Label(box, textvariable=self.var_overall).grid(row=1000, column=3, sticky="e", padx=(0, 8))

    def _build_log_section(self):
        box = ttk.LabelFrame(self, text=_("encode_log"))
        box.grid(row=3, column=0, sticky="nsew", padx=12, pady=(6, 12))
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)

        self.txt = tk.Text(
            box, wrap="none", height=18,
            background="#141414", foreground="#d0d0d0",
            insertbackground="#ffffff", borderwidth=0
        )
        self.txt.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(box, orient="vertical", command=self.txt.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.txt.configure(yscrollcommand=yscroll.set)

        for tag, color in {
            "info": "#d0d0d0", "success": "#4caf50", "warn": "#ffb74d",
            "error": "#e57373", "title": "#00a884", "debug": "#9e9e9e"
        }.items():
            self.txt.tag_configure(tag, foreground=color)

        self._log_line(_("encode_ready"), "title")

    # -------------------- Logic --------------------

    def _on_start(self):
        if self.running:
            messagebox.showinfo("Info", _("encode_already_running"))
            return
        jobs = [j for j in self.main_app.tab_config.jobs if getattr(j, "included", True)]
        if not jobs:
            messagebox.showerror("Error", _("error_no_jobs"))
            return

        self.reset_all_bars()
        for j in jobs:
            j.dst.parent.mkdir(parents=True, exist_ok=True)
        defaults_perf = self.settings.get_performance_settings()
        self.running = True
        self.controller.start_encoding(jobs, defaults_perf)
        self._log_line(_("encode_started").format(count=len(jobs)), "title")

    def _on_pause(self):
        if not self.running:
            messagebox.showinfo("Info", _("encode_not_running"))
            return
        paused = self.controller.toggle_pause()
        self._log_line(_("encode_paused") if paused else _("encode_resumed"),
                       "warn" if paused else "info")

    def _on_stop(self):
        if not self.running:
            self._log_line(_("encode_nothing_to_stop"), "warn")
            return
        self.controller.stop_all_processes()

    # -------------------- Progress --------------------

    def update_worker_bar(self, widx: int, pct: float):
        """Thread-safe update of worker bar."""
        self.after(0, lambda: self._update_worker_bar_ui(widx, pct))

    def _update_worker_bar_ui(self, widx: int, pct: float):
        box = self._progress_box
        if widx not in self.worker_bars:
            row = len(self.worker_bars) + 1
            lbl = ttk.Label(box, text=f"W{widx + 1}")
            pb = ttk.Progressbar(
                box, mode="determinate", length=500,
                style="Dark.Horizontal.TProgressbar", maximum=100,
            )
            pct_lbl = ttk.Label(box, text="0%")
            lbl.grid(row=row, column=0, sticky="w", padx=8, pady=2)
            pb.grid(row=row, column=1, sticky="ew", padx=8, pady=2)
            pct_lbl.grid(row=row, column=2, sticky="e", padx=8, pady=2)
            self.worker_bars[widx] = (lbl, pb, pct_lbl)

        lbl, pb, pct_lbl = self.worker_bars[widx]
        try:
            pct = max(0.0, min(float(pct), 100.0))
        except Exception:
            pct = 0.0
        pb["value"] = pct
        pct_lbl.config(text=f"{pct:.0f}%")

    def set_overall_progress(self, pct: float):
        """Thread-safe overall bar update."""
        self.after(0, lambda: self._set_overall_ui(pct))

    def _set_overall_ui(self, pct: float):
        try:
            pct = max(0.0, min(float(pct), 100.0))
        except Exception:
            pct = 0.0
        self.pb_overall["value"] = pct
        self.var_overall.set(f"{pct:.0f}%")

    def reset_worker_bar(self, widx: int, job_name: str):
        """Called when a worker begins a new job — ensures a fresh visible bar."""
        self.after(0, lambda: self._reset_worker_bar_ui(widx, job_name))

    def _reset_worker_bar_ui(self, widx, job_name):
        box = self._progress_box
        if widx not in self.worker_bars:
            row = len(self.worker_bars) + 1
            lbl = ttk.Label(box, text=f"W{widx + 1}: {job_name}")
            pb = ttk.Progressbar(box, mode="determinate", length=500,
                                 style="Dark.Horizontal.TProgressbar", maximum=100)
            pct_lbl = ttk.Label(box, text="0%")
            lbl.grid(row=row, column=0, sticky="w", padx=8, pady=2)
            pb.grid(row=row, column=1, sticky="ew", padx=8, pady=2)
            pct_lbl.grid(row=row, column=2, sticky="e", padx=8, pady=2)
            self.worker_bars[widx] = (lbl, pb, pct_lbl)
        else:
            lbl, pb, pct_lbl = self.worker_bars[widx]
            lbl.config(text=f"W{widx + 1}: {job_name}")
            pb["value"] = 0
            pct_lbl.config(text="0%")

    def mark_worker_done(self, widx: int):
        self.after(0, lambda: self._mark_worker_done_ui(widx))

    def _mark_worker_done_ui(self, widx):
        if widx in self.worker_bars:
            lbl, pb, pct = self.worker_bars[widx]
            pb["value"] = 100
            pct.config(text="Done")

    def reset_all_bars(self):
        for _, (lbl, pb, pct_lbl) in self.worker_bars.items():
            lbl.grid_remove()
            pb.grid_remove()
            pct_lbl.grid_remove()
        self.worker_bars.clear()
        self.pb_overall["value"] = 0
        self.var_overall.set("0%")

    # -------------------- Logging --------------------

    def _log_line(self, text, level="info"):
        """Thread-safe log appending."""
        def append():
            ts = time.strftime("[%H:%M:%S] ")
            self.txt.insert("end", ts + str(text) + "\n", (level,))
            self.txt.see("end")
        if threading.current_thread() is threading.main_thread():
            append()
        else:
            self.after(0, append)

    # -------------------- System Monitor --------------------

    def _start_system_monitor(self):
        try:
            self._last_disk = psutil.disk_io_counters()
        except Exception:
            self._last_disk = None
        self._last_time = time.time()
        self._update_sysmon()

    def _update_sysmon(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            mbps = 0.0
            now = time.time()

            if self._last_disk:
                cur = psutil.disk_io_counters()
                delta_w = max(0, cur.write_bytes - self._last_disk.write_bytes)
                sec = max(0.1, now - self._last_time)
                mbps = (delta_w / 1e6) / sec
                self._last_disk = cur
            self._last_time = now

            self.var_cpu.set(_("encode_cpu").format(val=f"{cpu:.0f}"))
            self.var_ram.set(_("encode_ram").format(val=f"{ram:.0f}"))
            self.var_disk.set(_("encode_disk").format(val=f"{mbps:.1f}"))
            self.pb_cpu["value"] = cpu
        except Exception:
            pass
        self.after(1000, self._update_sysmon)
