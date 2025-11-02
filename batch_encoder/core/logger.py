"""
Optional logger abstraction for GUI + file output.
"""

import datetime

def log_to_file(message: str, path="encoder.log"):
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
