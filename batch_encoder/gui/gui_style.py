"""
gui_style.py — ttkbootstrap integration
Modern dark theme (darkly) for the Batch Video Encoder GUI.
"""

import ttkbootstrap as ttk

def apply_dark_theme(style=None):
    """
    Apply ttkbootstrap dark theme globally.
    If a ttk.Style() instance is passed, it is ignored since ttkbootstrap
    manages its own style system.
    """
    # Create the ttkbootstrap style using a dark theme
    # Options: darkly, cyborg, superhero, solar, vapor, morph
    bootstyle = ttk.Style(theme="cyborg")

    return bootstyle
