"""
gui_style.py
------------
Applies modern dark theme styling across all platforms.

Uses ttkbootstrap's dark theme when available.
Falls back to plain tkinter dark styling if ttkbootstrap is missing
or if running in a minimal/no-display Linux environment.
"""

import os

def apply_dark_theme(style=None):
    """
    Apply dark theme globally across Windows, Linux, and macOS.
    - Uses ttkbootstrap 'cyborg' if available.
    - Falls back to manual dark theme for pure ttk.
    """

    try:
        import ttkbootstrap as ttk
        # Prefer 'cyborg' or 'darkly' themes (both good dark options)
        theme = "cyborg"
        style = ttk.Style(theme=theme)
        return style

    except Exception as e:
        # --- Fallback: native ttk style dark mode ---
        try:
            from tkinter import ttk

            if style is None:
                style = ttk.Style()

            # Apply basic dark styling
            style.theme_use("clam")
            dark_bg = "#1e1e1e"
            dark_fg = "#e0e0e0"
            accent = "#00a884"

            style.configure(".", background=dark_bg, foreground=dark_fg, fieldbackground=dark_bg)
            style.configure("TLabel", background=dark_bg, foreground=dark_fg)
            style.configure("TFrame", background=dark_bg)
            style.configure("TButton", background="#2b2b2b", foreground=dark_fg, relief="flat")
            style.map("TButton", background=[("active", "#3a3a3a")])
            style.configure("TCheckbutton", background=dark_bg, foreground=dark_fg)
            style.configure("TRadiobutton", background=dark_bg, foreground=dark_fg)
            style.configure("TNotebook", background=dark_bg, foreground=dark_fg)
            style.configure("TNotebook.Tab", background="#2b2b2b", foreground=dark_fg)
            style.configure("TProgressbar", background=accent, troughcolor="#121212")

            print(f"[gui_style] Fallback dark theme applied (ttkbootstrap missing: {e})")
            return style

        except Exception as e2:
            print(f"[gui_style] Failed to apply any theme: {e2}")
            return None
