"""
Launcher for Batch Video Encoder.
Double-click this file to start the GUI.
"""
from batch_encoder.gui.app_gui import EncoderGUI

if __name__ == "__main__":
    app = EncoderGUI()
    app.mainloop()
