"""
Allows the package to be executed with: python -m batch_encoder
"""
from batch_encoder.gui.app_gui import EncoderGUI

def main():
    app = EncoderGUI()
    app.mainloop()

if __name__ == "__main__":
    main()
