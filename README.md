# Batch Video Encoder (Python + FFmpeg)

A modern GUI tool for bulk video re-encoding using **FFmpeg**, built in Python with a focus on automation, Smart Mode analysis, and clean design.

---

## Features

- **Smart Mode** – automatically analyzes files and picks the best settings  
- **Encoding Goals (Intent)** – choose between *Speed, Balanced, Quality, Lossless*, etc.  
- **Advanced Overrides** – customize codec, CRF, preset, resolution, and pixel format  
- **Impact Preview** – estimates file size, quality change, and efficiency before encoding  
- **Plugin-ready** – extend behavior via plugin API  
- **CPU throttle** – choose the number of CPU cores and workers to be used to keep your system running smoothly during encoding  
- **GPU / CPU Support** - Seamlessly uses NVIDIA NVENC or CPU-based encoders. 

---

## Requirements

- Windows 10/11 (64-bit)
- FFmpeg (must be in PATH)
- Python 3.10+ (for source version)

Install dependencies manually if needed:

```bash
pip install -r requirements.txt
```

---

Encodex is 100% open source.
You can inspect the full code here on GitHub — the EXE is built directly from this code using PyInstaller.
The binary is unsigned, so Windows may show an “Unknown Publisher” warning.
You can verify safety by building your own EXE from source.

---

## Current State

- Core functions work, you can test smart mode, encoding, impact preview, cpu throttle.

## Planned updates

- Cleaning up the code and implementing some settings that are currently unused
- Audio config
- Subtitles config
- Linux support
- ... let me know what you'd like

---

## ☕ Support the Project

If you find Encodex helpful, please consider supporting continued development --> https://buymeacoffee.com/chris4212
