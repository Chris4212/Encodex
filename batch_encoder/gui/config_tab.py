"""
config_tab.py
-------------
Configuration tab for Batch Video Encoder GUI.

Responsibilities:
- Display and modify global encoding settings
- Show all fetched jobs in a sortable, editable list
- Run Smart Mode analysis preview ("Analyze All")
- Reload folder content safely (non-blocking)
- All text localized via localization system
"""

from __future__ import annotations
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
import threading
from pathlib import Path

from batch_encoder.core.models import Job
from batch_encoder.core.file_utils import prepare_session
from batch_encoder.core.smart_mode import SmartOptimizer
from batch_encoder.config import (
    ENCODING_GOALS, CODEC_CHOICES, PRESET_OPTIONS, PIX_FMT_CHOICES, RESOLUTION_OPTIONS, SUPPORTED_EXTENSIONS
)
from .localization import _
from .home_tab import ToolTip
from batch_encoder.core.impact_estimator import ImpactEstimator



class ConfigTab(ttk.Frame):
    """Handles presets, Smart Mode preview, and file-level settings."""

    def __init__(self, master, main_app):
        super().__init__(master)
        self.main_app = main_app
        self.settings = main_app.settings
        self.jobs: list[Job] = []
        self._build_ui()

    # -------------------- UI Construction --------------------

    # ---------------------------------------------------------------------
    # MAIN UI BUILD
    # ---------------------------------------------------------------------

    def _build_ui(self):
        """Construct all UI sections top-to-bottom."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)  # file list area

        # 🎯 Encoding Goal (Top)
        self._build_goal_section()

        # 🧠 Smart Mode
        self._build_smartmode_section()

        # ⚙️ Advanced Overrides
        self._build_advanced_section()

        # 📋 File Lists
        self._build_filelist_section()

    # ---------------------------------------------------------------------
    # 🎯 ENCODING GOAL SECTION
    # ---------------------------------------------------------------------
    def _migrate_goal_if_needed(self):
        val = self.settings.get("goal")
        if isinstance(val, dict) or val not in ENCODING_GOALS:
            self.settings.set("goal", "balanced")
            self.settings.save_user_file()

    def _build_goal_section(self):
        box = ttk.LabelFrame(self, text="🎯 Encoding Goal")
        box.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        box.columnconfigure(1, weight=1)

        raw_goal = self.settings.get("goal", "balanced")
        if isinstance(raw_goal, dict) or raw_goal not in ENCODING_GOALS:
            raw_goal = "balanced"

        self.var_goal = tk.StringVar(value=raw_goal)
        self.var_use_gpu = tk.BooleanVar(value=self.settings.get("use_gpu", False))

        ttk.Label(box, text="Encoding Goal:").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=6)
        self.cmb_goal = ttk.Combobox(
            box,
            textvariable=self.var_goal,
            values=list(ENCODING_GOALS.keys()),
            state="readonly",
            width=18,
        )
        self.cmb_goal.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=6)
        ToolTip(self.cmb_goal,
                "Select your encoding goal — determines how Smart Mode balances speed, compression, and quality.")
        self.cmb_goal.bind("<<ComboboxSelected>>", self._on_goal_changed)

        chk_gpu = ttk.Checkbutton(box, text="Use GPU (NVENC if available)", variable=self.var_use_gpu)
        chk_gpu.grid(row=0, column=2, sticky="w", padx=(4, 8), pady=6)
        ToolTip(chk_gpu,
                "Enable NVIDIA NVENC hardware acceleration if supported. Increases speed slightly at minor quality cost.")

        desc = ENCODING_GOALS.get(self.var_goal.get(), {}).get("desc", "")
        self.lbl_goal_desc = ttk.Label(
            box,
            text=desc,
            wraplength=650,
            justify="left",
        )
        self.lbl_goal_desc.grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))

        lbl_tip = ttk.Label(
            box,
            text="💡 Your selected goal determines how Smart Mode behaves for analysis, codec choice, compression strength, and scaling.",
            font=("TkDefaultFont", 9, "italic"),
            foreground="#8f8f8f",
            wraplength=700,
            justify="left",
        )
        lbl_tip.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))

    def _on_goal_changed(self, _):
        key = self.var_goal.get()
        self.lbl_goal_desc.config(text=ENCODING_GOALS[key]["desc"])
        self.settings.set("goal", key)
        self.settings.save_user_file()
        print("Goal changed to: " + key)

    # ---------------------------------------------------------------------
    # 🧠 SMART MODE ANALYSIS
    # ---------------------------------------------------------------------
    def _build_smartmode_section(self):
        box = ttk.LabelFrame(self, text="🧠 Smart Mode Analysis")
        box.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 6))
        box.columnconfigure(0, weight=1)

        btn_analyze = ttk.Button(box, text="Analyze Files", command=self._analyze_all)
        btn_analyze.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ToolTip(btn_analyze,
                "Analyze selected files to auto-detect optimal encoding settings based on your current goal.")

        lbl_hint = ttk.Label(
            box,
            text="Automatically assigns appropriate settings based on your goal and each file’s properties.",
            font=("TkDefaultFont", 9, "italic"),
            foreground="#8f8f8f",
            wraplength=700,
            justify="left",
        )
        lbl_hint.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))

        self.lbl_status = ttk.Label(box, text="ℹ️ Status: Ready – 0 files analyzed")
        self.lbl_status.grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))

    # ---------------------------------------------------------------------
    # ⚙️ ADVANCED OVERRIDES
    # ---------------------------------------------------------------------
    def _build_advanced_section(self):
        box = ttk.LabelFrame(self, text="⚙️ Advanced Overrides (optional)")
        box.grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 6))
        for i in range(8):
            box.columnconfigure(i, weight=1)

        # Variables
        self.var_codec = tk.StringVar(value="as-is")
        self.var_crf = tk.StringVar(value="as-is")
        self.var_preset = tk.StringVar(value="as-is")
        self.var_pixfmt = tk.StringVar(value="as-is")
        self.var_res = tk.StringVar(value="source")
        self.var_ext = tk.StringVar(value=".mp4")

        # --- Row 1 -----------------------------------------------------------
        ttk.Label(box, text="Codec:").grid(row=0, column=0, sticky="w", padx=(8, 2), pady=4)
        cmb_codec = ttk.Combobox(box, textvariable=self.var_codec,
                                 values=["as-is"] + [c[0] for c in CODEC_CHOICES],
                                 width=14, state="readonly")
        cmb_codec.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=4)
        ToolTip(cmb_codec, "Manually select encoder (H.264, HEVC, AV1). Leave ‘as-is’ for Smart Mode.")

        ttk.Label(box, text="CRF:").grid(row=0, column=2, sticky="w", padx=(4, 2), pady=4)
        cmb_crf = ttk.Combobox(box, textvariable=self.var_crf,
                               values=["as-is"] + [str(i) for i in range(0, 52)],
                               width=6, state="readonly")
        cmb_crf.grid(row=0, column=3, sticky="w", padx=(0, 8), pady=4)
        ToolTip(cmb_crf, "Constant Rate Factor — lower = higher quality. Leave ‘as-is’ for Smart Mode default.")

        ttk.Label(box, text="Preset:").grid(row=0, column=4, sticky="w", padx=(4, 2), pady=4)
        cmb_preset = ttk.Combobox(box, textvariable=self.var_preset,
                                  values=["as-is"] + PRESET_OPTIONS,
                                  width=10, state="readonly")
        cmb_preset.grid(row=0, column=5, sticky="w", padx=(0, 8), pady=4)
        ToolTip(cmb_preset, "Encoding speed vs compression. Slower = smaller output.")

        # --- Row 2 -----------------------------------------------------------
        ttk.Label(box, text="Pixel Format:").grid(row=1, column=0, sticky="w", padx=(8, 2), pady=4)
        cmb_pix = ttk.Combobox(box, textvariable=self.var_pixfmt,
                               values=["as-is"] + [p[0] for p in PIX_FMT_CHOICES],
                               width=12, state="readonly")
        cmb_pix.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=4)
        ToolTip(cmb_pix, "Choose color format and bit depth. ‘yuv420p’ is most compatible.")

        ttk.Label(box, text="Resolution:").grid(row=1, column=2, sticky="w", padx=(4, 2), pady=4)
        cmb_res = ttk.Combobox(box, textvariable=self.var_res,
                               values=list(RESOLUTION_OPTIONS.keys()),
                               width=10, state="readonly")
        cmb_res.grid(row=1, column=3, sticky="w", padx=(0, 8), pady=4)
        ToolTip(cmb_res, "Downscale or keep original resolution.")

        ttk.Label(box, text="Extension:").grid(row=1, column=4, sticky="w", padx=(4, 2), pady=4)
        cmb_ext = ttk.Combobox(box, textvariable=self.var_ext,
                               values=sorted(list(SUPPORTED_EXTENSIONS)),
                               width=8, state="readonly")
        cmb_ext.grid(row=1, column=5, sticky="w", padx=(0, 8), pady=4)
        ToolTip(cmb_ext, "Select desired output container format (e.g. MP4, MKV).")

        # --- Buttons ---------------------------------------------------------
        btn_apply_sel = ttk.Button(box, text="Apply to Selected", command=self._apply_to_selected)
        btn_apply_all = ttk.Button(box, text="Apply to All", command=self._apply_to_all)
        btn_apply_sel.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 6))
        btn_apply_all.grid(row=2, column=2, columnspan=2, sticky="w", padx=8, pady=(6, 6))
        ToolTip(btn_apply_sel, "Apply selected overrides only to highlighted files.")
        ToolTip(btn_apply_all, "Apply selected overrides to all listed files.")

        # --- Tip -------------------------------------------------------------
        lbl_tip = ttk.Label(
            box,
            text="⚠️ These overrides replace Smart Mode decisions. Choose ‘as-is’ to leave them untouched.",
            font=("TkDefaultFont", 9, "italic"),
            foreground="#8f8f8f",
            wraplength=700,
            justify="left",
        )
        lbl_tip.grid(row=3, column=0, columnspan=8, sticky="w", padx=8, pady=(0, 6))

    def _build_filelist_section(self):
        box = ttk.LabelFrame(self, text=_("config_filelist"))
        box.grid(row=3, column=0, sticky="nsew", padx=12, pady=(6, 6))
        box.rowconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        box.columnconfigure(0, weight=1)

        # ---------------- TOP: FILE LIST ----------------
        cols = ("sel", "name", "size", "dur", "res", "codec", "crf", "preset", "smart", "edit")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", selectmode="extended")
        headings = ["✔", "File Name", "Size", "Duration", "Resolution", "Codec",
                    "CRF", "Preset", "Smart", "Edit"]
        widths = [40, 260, 80, 80, 100, 90, 60, 90, 70, 70]

        for c, t, w in zip(cols, headings, widths):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("odd", background="#1a1a1a")
        self.tree.tag_configure("even", background="#232323")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.insert("", "end", values=("","– Files will appear here once ready –",))

        # ---------------- BOTTOM: ENCODE IMPACT PREVIEW ----------------
        self.tree_impact = ttk.Treeview(
            box,
            columns=("name", "est_size", "delta", "quality", "info"),
            show="headings",
            height=6
        )

        headings_impact = ["File", "Est. Size", "Change", "Quality", "Info"]

        # Adjusted widths: File smaller, Quality & Info wider
        widths_impact = [140, 110, 90, 180, 520]

        for c, t, w in zip(self.tree_impact["columns"], headings_impact, widths_impact):
            self.tree_impact.heading(c, text=t)
            self.tree_impact.column(c, width=w, anchor="w", stretch=(c == "info"))

        # Tag colors
        self.tree_impact.tag_configure("good", background="#1e2e1e")
        self.tree_impact.tag_configure("warn", background="#2e2e1e")
        self.tree_impact.tag_configure("bad", background="#2e1e1e")

        self.tree_impact.grid(row=1, column=0, sticky="nsew")

        # Initially empty — filled after analysis
        self.tree_impact.insert("", "end", values=("", "", "", "", ""))
        self.tree_impact.insert("", "end", values=("– Encoding impact preview will appear here after analysis –",))

        # Force perfect 50:50 split between main list and impact list
        box.update_idletasks()
        total_h = box.winfo_height()
        half = max(total_h // 2, 1)
        box.rowconfigure(0, minsize=half)
        box.rowconfigure(1, minsize=half)

        # ---------------- SHARED SCROLLBAR ----------------
        self._syncing_scroll = False

        def _scrollbar_cmd(*args):
            """Scroll both trees together."""
            self.tree.yview(*args)
            self.tree_impact.yview(*args)

        yscroll = ttk.Scrollbar(box, orient="vertical", command=_scrollbar_cmd)
        yscroll.grid(row=0, column=1, rowspan=2, sticky="ns")

        def _on_top_y(first, last):
            if not self._syncing_scroll:
                self._syncing_scroll = True
                try:
                    self.tree_impact.yview_moveto(first)
                    yscroll.set(first, last)
                finally:
                    self._syncing_scroll = False
            else:
                yscroll.set(first, last)

        def _on_bottom_y(first, last):
            if not self._syncing_scroll:
                self._syncing_scroll = True
                try:
                    self.tree.yview_moveto(first)
                    yscroll.set(first, last)
                finally:
                    self._syncing_scroll = False
            else:
                yscroll.set(first, last)

        self.tree.configure(yscrollcommand=_on_top_y)
        self.tree_impact.configure(yscrollcommand=_on_bottom_y)

        # ---------------- MOUSE WHEEL SYNC ----------------
        def _mw(event, direction):
            self.tree.yview_scroll(direction, "units")
            self.tree_impact.yview_scroll(direction, "units")
            return "break"

        self.tree.bind("<MouseWheel>", lambda e: _mw(e, -1 if e.delta > 0 else 1))
        self.tree_impact.bind("<MouseWheel>", lambda e: _mw(e, -1 if e.delta > 0 else 1))
        # Linux
        self.tree.bind("<Button-4>", lambda e: _mw(e, -1))
        self.tree.bind("<Button-5>", lambda e: _mw(e, +1))
        self.tree_impact.bind("<Button-4>", lambda e: _mw(e, -1))
        self.tree_impact.bind("<Button-5>", lambda e: _mw(e, +1))

        # Prevent scroll snap when selection hits edge
        def _pre_scroll(_):
            self.tree.focus("")
            self.tree_impact.focus("")
            return None

        self.tree.bind("<ButtonPress-1>", _pre_scroll, add="+")
        self.tree_impact.bind("<ButtonPress-1>", _pre_scroll, add="+")

        # ---------------- SELECTION SYNC (by file name) ----------------
        self._syncing_selection = False
        self._active_tree = None  # <-- track which tree was clicked last

        def _sync_select_by_name(src_tree, dst_tree):
            """Sync selection between trees by 'name' column."""
            if self._syncing_selection:
                return
            self._syncing_selection = True
            try:
                selected_names = {src_tree.set(i, "name") for i in src_tree.selection()}
                if not selected_names:
                    dst_tree.selection_remove(*dst_tree.selection())
                    return
                name_to_iid = {dst_tree.set(i, "name"): i for i in dst_tree.get_children("")}
                matched = [name_to_iid[n] for n in selected_names if n in name_to_iid]
                dst_tree.selection_set(matched)
            finally:
                self._syncing_selection = False

        # Track which tree the user actually clicked
        def _on_top_click(_):
            self._active_tree = "top"

        def _on_bottom_click(_):
            self._active_tree = "bottom"

        self.tree.bind("<ButtonPress-1>", _on_top_click, add="+")
        self.tree_impact.bind("<ButtonPress-1>", _on_bottom_click, add="+")

        def _on_top_select(_):
            if self._active_tree == "top":
                self.after(60, lambda: _sync_select_by_name(self.tree, self.tree_impact))

        def _on_bottom_select(_):
            if self._active_tree == "bottom":
                self.after(60, lambda: _sync_select_by_name(self.tree_impact, self.tree))

        self.tree.bind("<<TreeviewSelect>>", _on_top_select)
        self.tree_impact.bind("<<TreeviewSelect>>", _on_bottom_select)
        self._setup_linked_sorting()

    def _build_info_panel(self):
        self.info_panel = ttk.LabelFrame(self, text=_("config_info"))
        self.info_panel.grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 12))
        self.lbl_status = ttk.Label(self.info_panel, text=_("config_no_jobs"))
        self.lbl_status.grid(row=0, column=0, sticky="w", padx=8, pady=6)

    # -------------------- Data Handling --------------------

    def populate_jobs(self, jobs: list[Job]):
        self.jobs = jobs
        self.tree.delete(*self.tree.get_children())

        for idx, j in enumerate(jobs):
            smart = j.settings.get("smart_details", {})
            metrics = smart.get("metrics", {})

            duration = metrics.get("duration_s", 0.0)
            width = metrics.get("width", "?")
            height = metrics.get("height", "?")
            codec = j.settings.get("codec") or j.settings.get("vcodec", "")
            crf = j.settings.get("crf", "")
            preset = j.settings.get("preset", "")
            smart_flag = "✓" if getattr(j, "use_smart", True) else ""
            tag = "even" if idx % 2 == 0 else "odd"

            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    "✓",
                    j.src.name,
                    f"{j.size:.1f} MB",
                    f"{duration:.1f}s",
                    f"{width}x{height}",
                    codec,
                    crf,
                    preset,
                    smart_flag,
                    "Edit",
                ),
                tags=(tag,),
            )

        self.lbl_status.config(text=f"{len(jobs)} {_('config_info')}")

    def populate_impact_preview(self, jobs: list):
        """Display Smart Mode impact predictions for each job."""
        self.tree_impact.delete(*self.tree_impact.get_children())

        if not jobs:
            self.tree_impact.insert("", "end", values=("No data", "", "", "", ""))
            return

        for j in jobs:
            impact = j.settings.get("impact_preview", {})
            metrics = j.settings.get("smart_details", {}).get("metrics", {})

            # Fallback info
            name = j.src.name
            size_mb = impact.get("expected_size_mb", 0.0)
            delta = impact.get("reduction_pct", 0.0)
            quality = impact.get("quality", "unknown")
            reason = impact.get("reason", "")
            tag = "good"

            # Format text nicely
            size_text = f"{size_mb:.1f} MB" if size_mb else "-"
            delta_text = f"{delta:+.0f}%" if delta else "-"
            qual_text = quality.title() if quality else "-"

            impact = j.settings.get("impact_preview", {})
            info = impact.get("info", "")
            self.tree_impact.insert(
                "",
                "end",
                values=(name, size_text, delta_text, qual_text, info),
                tags=(tag,),
            )


        # Auto-resize columns (optional)
        for col in self.tree_impact["columns"]:
            font = tkfont.Font()
            max_width = max(
                (font.measure(str(self.tree_impact.set(child, col))) for child in self.tree_impact.get_children()),
                default=100,
            )
            # add a little padding
            self.tree_impact.column(col, width=max(100, max_width + 20))

    def _refresh_impact_preview(self, jobs: list | None = None):
        estimator = ImpactEstimator()
        jobs = jobs or self.jobs
        for j in jobs:
            try:
                print(j.settings)
                j.settings["impact_preview"] = estimator.estimate(j.media_info, j.settings)
            except Exception:
                print("Exception while estimating impact preview")
                j.settings["impact_preview"] = {}
        self.populate_impact_preview(jobs)

    def _autosize_tree_columns(self, tree: ttk.Treeview, exclude_last: bool = True):
        """Auto-size all columns to fit content, optionally skipping the last column."""
        import tkinter.font as tkfont

        font = tkfont.Font()  # default treeview font
        columns = tree["columns"]
        if exclude_last:
            columns = columns[:-1]

        for col in columns:
            # Find widest cell content (including header)
            header_width = font.measure(tree.heading(col, "text"))
            cell_widths = [
                font.measure(str(tree.set(item, col))) for item in tree.get_children("")
            ]
            max_width = max([header_width, *cell_widths], default=80) + 20
            tree.column(col, width=max_width, minwidth=60, stretch=False)

        # Keep last column (like "Info") flexible
        if exclude_last and tree["columns"]:
            last = tree["columns"][-1]
            tree.column(last, stretch=True)

    def _setup_linked_sorting(self):
        """Enable sorting for both trees; the other list follows by filename."""
        for col in self.tree["columns"]:
            self.tree.heading(col, command=lambda c=col: self._sort_and_link(self.tree, self.tree_impact, c, False))
        for col in self.tree_impact["columns"]:
            self.tree_impact.heading(col,
                                     command=lambda c=col: self._sort_and_link(self.tree_impact, self.tree, c, False))

    def _sort_and_link(self, src_tree: ttk.Treeview, dst_tree: ttk.Treeview, col: str, descending: bool):
        """Sort the source tree by column; reorder the destination by the same file-name order."""
        rows = [(src_tree.set(i, col), src_tree.set(i, "name"), i)
                for i in src_tree.get_children("")]
        if not rows:
            return

        # smart numeric sort
        def _num(s):
            s = str(s).replace("MB", "").replace("%", "").strip()
            try:
                return float(s)
            except Exception:
                return s.lower()

        rows.sort(key=lambda t: _num(t[0]), reverse=descending)

        # move items in source tree
        for idx, (_, _, iid) in enumerate(rows):
            src_tree.move(iid, "", idx)

        # get sorted filename order
        sorted_names = [t[1] for t in rows]

        # move items in destination tree by name
        name_to_iid = {dst_tree.set(i, "name"): i for i in dst_tree.get_children("")}
        for idx, name in enumerate(sorted_names):
            if name in name_to_iid:
                dst_tree.move(name_to_iid[name], "", idx)

        # toggle next sort direction
        src_tree.heading(col, command=lambda c=col: self._sort_and_link(src_tree, dst_tree, c, not descending))

    def _on_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id:
            return
        idx = int(row_id)
        col_name = self.tree["columns"][int(col_id.strip('#'))-1]
        job = self.jobs[idx]
        if col_name == "sel":
            job.included = not getattr(job,"included",True)
            self.tree.set(row_id, "sel", "✓" if job.included else "")
        elif col_name == "edit":
            self._open_edit_for_row(job, idx)

    # -------------------- Actions --------------------


    def _apply_to_selected(self):
        """Apply overrides only to selected jobs."""
        if not self.jobs:
            return
        selected_jobs = [j for j in self.jobs if getattr(j, "included", True)]
        self._apply_common(selected_jobs)

    def _apply_to_all(self):
        """Apply overrides to all jobs."""
        self._apply_common(self.jobs)

    def _apply_common(self, targets: list[Job]):
        """Shared logic for Apply to Selected / Apply to All."""
        new_settings = {}
        for key, var in [
            ("codec", self.var_codec),
            ("crf", self.var_crf),
            ("preset", self.var_preset),
            ("pix_fmt", self.var_pixfmt),
            ("resolution", self.var_res),
            ("extension", self.var_ext)
        ]:
            val = var.get()
            if val != "as-is":
                new_settings[key] = val

        for job in targets:
            job.settings.update(new_settings)

        self.populate_jobs(self.jobs)
        self._refresh_impact_preview(self.jobs)
        messagebox.showinfo(_("info_applied"), _("config_applied"))

    def _analyze_all(self):
        if not self.jobs:
            messagebox.showinfo(_("error_no_jobs"), _("error_no_jobs"))
            return

        self.lbl_status.config(text="🧠 Analyzing files...")
        optimizer = SmartOptimizer()
        ui_defaults = self.settings.get_job_settings()
        goal = self.var_goal.get()
        use_gpu = self.var_use_gpu.get()

        def worker():
            updated = []
            for j in self.jobs:
                try:
                    analysis = optimizer.analyze_info(j.media_info, goal, use_gpu=use_gpu)
                    new = dict(ui_defaults)
                    new.update({
                        "vcodec": analysis.get("vcodec", new.get("codec", "libx265")),
                        "codec": analysis.get("codec", "libx265"),
                        "crf": str(analysis.get("crf", new.get("crf", "26"))),
                        "preset": analysis.get("preset", "medium"),
                        "pix_fmt": analysis.get("pix_fmt", "yuv420p"),
                        "scale_height": analysis.get("scale_height"),
                        "resolution": "source",
                        "goal": goal,
                        "extension": self.var_ext.get(),
                    })
                    j.settings.update(new)
                    #j.settings["smart_details"] = analysis
                    updated.append(j)
                except Exception:
                    pass

            self.after(0, lambda: self._on_analyze_complete(updated))

        threading.Thread(target=worker, daemon=True).start()

    def _on_analyze_complete(self, jobs):
        self.populate_jobs(self.jobs)
        self._refresh_impact_preview(self.jobs)
        self.lbl_status.config(text=f"✅ Ready – {len(jobs)} files analyzed")
        print("_on_analyze_complete - done")

    def _reload_folder(self):
        target = Path(self.settings.get("input_dir"))
        out = Path(self.settings.get("output_dir"))
        if not target.exists():
            messagebox.showerror(_("error_invalid_target"), _("error_invalid_target"))
            return
        self.lbl_status.config(text=_("config_reloading"))
        defaults_perf = self.settings.get_performance_settings()
        ui = self.settings.get_job_settings()
        smart = self.settings.get("smart_mode_enabled", True)

        def worker():
            try:
                jobs = prepare_session(target, out, defaults_perf, ui, smart_mode=smart)
                self.after(0, lambda: self.populate_jobs(jobs))
                self.after(0, lambda: self._refresh_impact_preview(self.jobs))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(_("config_reload"), str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _open_edit_for_row(self, job, idx):
        """Open per-file edit dialog and refresh previews after editing."""

        def on_apply(updated_jobs):
            # Re-populate the full job list (top)
            self.populate_jobs(self.jobs)
            # Refresh the entire impact list (bottom)
            self._refresh_impact_preview(self.jobs)

        JobEditDialog(self, [job], self.settings.get("output_dir"), on_apply)


# --------------------------------------------------------------
# JobEditDialog (localized)
# --------------------------------------------------------------

class JobEditDialog(tk.Toplevel):
    """Dialog for editing one or multiple job settings."""
    def __init__(self, master, jobs: list[Job], out_dir: Path, on_apply):
        super().__init__(master)
        self.title(_("config_edit_dialog_title"))
        self.configure(bg="#1e1e1e")
        self.jobs = jobs
        self.out_dir = Path(out_dir)
        self.on_apply = on_apply

        j0 = jobs[0]
        self.var_use_smart = tk.BooleanVar(value=getattr(j0, "use_smart", True))
        self.var_codec = tk.StringVar(value=j0.settings.get("codec", "libx265"))
        self.var_crf = tk.StringVar(value=str(j0.settings.get("crf", 23)))
        self.var_preset = tk.StringVar(value=j0.settings.get("preset", "medium"))
        self.var_pixfmt = tk.StringVar(value=j0.settings.get("pix_fmt", "yuv420p"))
        self.var_res = tk.StringVar(value=self._res_key_from_filter(j0.settings.get("resolution", "")))
        self.var_target = tk.StringVar(value=j0.custom_target or j0.dst.name)

        self._build_ui()
        self._refresh_enablement()
        self.grab_set()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Checkbutton(frm, text=_("config_use_smart_mode"),
                        variable=self.var_use_smart,
                        command=self._refresh_enablement).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0,8))

        def row(label, widget, r):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="e", padx=(0,8), pady=4)
            widget.grid(row=r, column=1, sticky="ew", pady=4)

        cmb_codec = ttk.Combobox(frm, textvariable=self.var_codec, values=[c[0] for c in CODEC_CHOICES],
                                 state="readonly", width=14)
        row(_("config_codec"), cmb_codec, 1)
        cmb_crf = ttk.Combobox(frm, textvariable=self.var_crf, values=[str(i) for i in range(0,52)],
                               state="readonly", width=5)
        row(_("config_crf"), cmb_crf, 2)
        cmb_preset = ttk.Combobox(frm, textvariable=self.var_preset, values=PRESET_OPTIONS,
                                  state="readonly", width=10)
        row(_("config_preset"), cmb_preset, 3)
        cmb_pix = ttk.Combobox(frm, textvariable=self.var_pixfmt, values=[p[0] for p in PIX_FMT_CHOICES],
                               state="readonly", width=10)
        row(_("config_pixfmt"), cmb_pix, 4)
        cmb_res = ttk.Combobox(frm, textvariable=self.var_res, values=list(RESOLUTION_OPTIONS.keys()),
                               state="readonly", width=10)
        row(_("config_resolution"), cmb_res, 5)

        ent_target = ttk.Entry(frm, textvariable=self.var_target, width=50)
        row(_("config_target_name"), ent_target, 6)

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=2, sticky="e", pady=(10,0))
        ttk.Button(btns, text=_("config_apply"), command=self._apply).pack(side="left", padx=6)
        ttk.Button(btns, text=_("config_cancel"), command=self.destroy).pack(side="left", padx=6)

        frm.columnconfigure(1, weight=1)

    def _res_key_from_filter(self, flt: str) -> str:
        if not flt:
            return "source"
        inverse = {v: k for k, v in RESOLUTION_OPTIONS.items()}
        return inverse.get(flt, "source")

    def _refresh_enablement(self):
        enable = not self.var_use_smart.get()
        frm = self.nametowidget(self.winfo_children()[0])
        for widget in frm.winfo_children():
            if isinstance(widget, ttk.Combobox):
                widget.configure(state=("readonly" if enable else "disabled"))
            elif isinstance(widget, ttk.Entry):
                widget.configure(state=("normal" if enable and len(self.jobs)==1 else "disabled"))

    def _apply(self):
        try:
            crf = int(self.var_crf.get())
            if not (0 <= crf <= 51):
                raise ValueError
        except Exception:
            messagebox.showerror(_("config_invalid_crf"), _("config_invalid_crf"))
            return

        for j in self.jobs:
            j.use_smart = self.var_use_smart.get()
            if not j.use_smart:
                res_key = self.var_res.get().lower()
                j.settings.update({
                    "codec": self.var_codec.get(),
                    "crf": crf,
                    "preset": self.var_preset.get(),
                    "pix_fmt": self.var_pixfmt.get(),
                    "resolution": res_key,
                })
            if len(self.jobs) == 1 and not j.use_smart:
                new_name = self.var_target.get().strip()
                if new_name:
                    ext = j.dst.suffix or ".mp4"
                    if "." not in new_name:
                        new_name += ext
                    new_path = self.out_dir / new_name
                    if new_path.exists() and new_path != j.dst:
                        base, ext = new_path.stem, new_path.suffix
                        n = 1
                        while new_path.exists():
                            new_path = self.out_dir / f"{base}_{n}{ext}"
                            n += 1
                    j.custom_target = new_path.name
                    j.dst = new_path

        self.on_apply(self.jobs)
        self.destroy()
