"""
Entry point for Batch Video Encoder.
Double-click this file to start the GUI.
"""

import sys, os
from pathlib import Path

# ---------------------------------------------------------------------
# Support both direct run (source) and frozen (PyInstaller) execution
# ---------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    # If running from a subfolder, go up one level (the project root)
    BASE_DIR = Path(__file__).resolve().parent
    if (BASE_DIR / "batch_encoder").exists():
        BASE_DIR = BASE_DIR
    elif (BASE_DIR.parent / "batch_encoder").exists():
        BASE_DIR = BASE_DIR.parent

# Ensure Python can import the main package
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "batch_encoder"))

# Debug print (optional)
# print("Import path:", sys.path)

# ---------------------------------------------------------------------
# Launch the app
# ---------------------------------------------------------------------
from batch_encoder.gui.app_gui import EncoderGUI

if __name__ == "__main__":
    app = EncoderGUI()
    app.mainloop()
