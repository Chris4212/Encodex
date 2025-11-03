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
- **Modern dark UI** with ttkbootstrap themes  

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

## Current State

- Core functions work, you can test smart mode, encoding, impact preview, cpu throttle.

## Planned updates

- Cleaning up the code and implementing some settings that are currently unused
- Audio config
- Subtitles config
- Linux support
- ... let me know what you'd like

- ## If you want to support me, please consider buying me a coffee --> https://buymeacoffee.com/chris4212
