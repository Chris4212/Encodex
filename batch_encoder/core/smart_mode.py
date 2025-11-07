"""
smart_mode.py
-------------
Smart Mode 4.x — Intent-aware adaptive encoding.

Analyzes media characteristics (resolution, bitrate, FPS, codec) and applies
goal-specific policy adjustments defined in config.ENCODING_GOALS.

Thread-safe and UI-friendly.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional

from .. import config
from .ffmpeg_utils import ffprobe_media_info
from batch_encoder.core.system_utils import is_windows, is_linux, is_macos


class SmartOptimizer:
    """
    Computes optimal encoder settings based on:
    - File metrics (from ffprobe)
    - Encoding goal (user intent)
    - Hardware preference (CPU/GPU)
    """

    # ---------------- PUBLIC API ----------------

    def analyze(self, src: Path, goal: str = "balanced", use_gpu: Optional[bool] = None) -> Dict[str, Any]:
        """Directly analyze a file path. Prefer analyze_info() when ffprobe data is preloaded."""
        try:
            info = ffprobe_media_info(src)
        except Exception as e:
            return {
                "vcodec": "libx265",
                "crf": "26",
                "preset": "medium",
                "pix_fmt": "yuv420p",
                "intent": goal,
                "reasoning": f"ffprobe failed: {e}",
                "metrics": {},
            }
        return self.analyze_info(info, goal, use_gpu=use_gpu)

    def analyze_info(self, info: Dict[str, Any], goal: str = "balanced", use_gpu: Optional[bool] = None) -> Dict[str, Any]:
        """
        Takes pre-probed ffprobe JSON dict + selected goal key (+ optional GPU hint).
        Returns encoding settings + extracted metrics for UI display.
        """
        try:
            meta = self._extract_metrics(info)
            decision = self._decide(meta, goal, use_gpu=use_gpu)

            result = {
                "vcodec": decision.get("vcodec"),
                "crf": str(decision.get("crf")),  # keep string for UI consistency
                "preset": decision.get("preset"),
                "pix_fmt": decision.get("pix_fmt"),
                "scale_height": decision.get("scale_height"),
                "intent": decision.get("intent", goal),
                "reasoning": decision.get("reasoning", ""),
                "metrics": {
                    "width": meta.get("width", 0),
                    "height": meta.get("height", 0),
                    "fps": meta.get("fps", 0.0),
                    "duration_s": meta.get("duration_s", 0.0),
                    "bitrate_mbps": meta.get("bitrate_mbps", 0.0),
                    "resolution": meta.get("resolution", "unknown"),
                    "codec_in": meta.get("codec", ""),
                },
            }
            return result

        except Exception as e:
            # Always return a safe structure even if something fails
            return {
                "vcodec": "libx265",
                "crf": "26",
                "preset": "medium",
                "pix_fmt": "yuv420p",
                "intent": goal if goal in getattr(config, "ENCODING_GOALS", {}) else "balanced",
                "reasoning": f"Analysis failed: {e}",
                "metrics": {
                    "width": 0, "height": 0, "fps": 0.0,
                    "duration_s": 0.0, "bitrate_mbps": 0.0,
                    "resolution": "unknown", "codec_in": "",
                },
            }

    # ---------------- INTERNALS ----------------

    @staticmethod
    def _extract_metrics(info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract normalized metrics we care about from ffprobe data."""
        fmt = info.get("format", {}) or {}
        streams = info.get("streams", []) or []
        v = next((s for s in streams if s.get("codec_type") == "video"), {})

        width = int(v.get("width") or 0)
        height = int(v.get("height") or 0)
        codec = (v.get("codec_name") or "").lower()

        # Frame rate parsing
        afr = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
        try:
            num, den = (float(x) for x in afr.split("/"))
            fps = num / den if den else 0.0
        except Exception:
            fps = 0.0

        # Duration and bitrate
        try:
            duration = float(fmt.get("duration") or 0.0)
        except Exception:
            duration = 0.0
        try:
            br = float(fmt.get("bit_rate") or 0.0) / 1_000_000.0
        except Exception:
            br = 0.0

        # Resolution class
        if height >= 2160:
            res_class = "4k"
        elif height >= 1440:
            res_class = "1440p"
        elif height >= 1080:
            res_class = "1080p"
        elif height >= 720:
            res_class = "720p"
        elif height > 0:
            res_class = "sd"
        else:
            res_class = "unknown"

        return {
            "width": width, "height": height, "fps": fps,
            "codec": codec, "duration_s": duration,
            "bitrate_mbps": br, "resolution": res_class,
        }

    # ---- helpers ---------------------------------------------------------

    def _resolve_codec(self, use_gpu: bool, prefer_family: str) -> str:
        """
        Map a 'family' preference (h264/hevc/av1) + GPU flag to a concrete encoder.
        Tries config.resolve_codec if present; otherwise uses safe fallbacks.
        """
        try:
            if hasattr(config, "resolve_codec") and callable(config.resolve_codec):
                return config.resolve_codec(use_gpu, prefer_family)
        except Exception:
            pass

        fam = (prefer_family or "hevc").lower()
        if use_gpu:
            if fam == "h264":
                return "h264_nvenc"
            if fam == "av1":
                return "av1_nvenc"
            return "hevc_nvenc"
        else:
            if fam == "h264":
                return "libx264"
            if fam == "av1":
                return "libaom-av1"
            return "libx265"

    @staticmethod
    def _nvenc_preset_for(x264_preset: str) -> str:
        """Map x264-style presets to NVENC tiers."""
        p = (x264_preset or "medium").lower()
        table = {
            "ultrafast": "p1", "superfast": "p2", "veryfast": "p3",
            "faster": "p4", "fast": "p5",
            "medium": "p6", "slow": "p7", "slower": "p7", "veryslow": "p7",
        }
        return table.get(p, "p6")

    @staticmethod
    def _pixfmt_is_supported(vcodec: str, pix_fmt: str) -> bool:
        """Minimal guard for common cases."""
        v = (vcodec or "").lower()
        pf = (pix_fmt or "").lower()
        if "h264" in v and "10" in pf:
            return False  # h264_nvenc/libx264 don't do 10-bit yuv420p10le
        return True

    # ---- core decision ---------------------------------------------------

    def _decide(self, m: Dict[str, Any], goal_key: str, use_gpu: Optional[bool] = None) -> Dict[str, Any]:
        """
        Decide encoder settings based on file metrics + chosen goal.
        """
        height = m.get("height", 0)
        width = m.get("width", 0)
        fps = float(m.get("fps") or 0.0)
        br = float(m.get("bitrate_mbps") or 0.0)
        res = m.get("resolution") or "unknown"

        # 1) Load goal policy (fallback to balanced)
        goals = getattr(config, "ENCODING_GOALS", {})
        goal_key = goal_key if goal_key in goals else "balanced"
        goal = goals[goal_key]
        policy = goal.get("policy", {}) or {}

        # 2) Decide GPU
        if use_gpu is None:
            use_gpu = bool(getattr(config, "USE_GPU", False))

        # 3) Bitrate density
        try:
            density = (br * 1_000_000) / max(width * height * fps, 1)
        except Exception:
            density = 0.0002

        # 4) Resolution baseline
        if res == "4k":
            scale_h, base_crf = 2160, 24
        elif res == "1440p":
            scale_h, base_crf = 1440, 24
        elif res == "1080p":
            scale_h, base_crf = 1080, 26
        elif res == "720p":
            scale_h, base_crf = 720, 27
        else:
            scale_h, base_crf = None, 28

        # 5) Codec family
        prefer_family = policy.get("prefer_family") or "hevc"
        vcodec = self._resolve_codec(use_gpu, prefer_family)
        crf = min(max(base_crf + int(policy.get("crf_delta", 0)), 16), 32)
        preset = policy.get("preset") or "medium"
        pix_fmt = policy.get("force_pix_fmt") or "yuv420p"

        # 6) Adjust based on intent/density/fps
        target = policy.get("target", "balanced")
        if target in ("speed", "mobile"):
            if fps >= 60:
                preset = "superfast"
                crf = min(crf + 1, 32)
        elif target in ("quality", "archive", "lossless"):
            if density < 0.00015:
                crf = max(crf - 2, 16)
                preset = "slow"
        elif target in ("size", "compat", "neutral"):
            if density > 0.00025:
                crf = min(crf + 2, 32)
                if preset in ("medium", "slow"):
                    preset = "faster"

        # 7) Downscale if allowed
        if policy.get("allow_downscale", True):
            if density < 0.00008 and height > 1080:
                scale_h = 1080
            elif density < 0.00005 and height > 720:
                scale_h = 720

        # 8) Very high FPS handling
        if fps >= 100:
            preset = "fast"
            crf = min(crf + 1, 32)

        # 9) NVENC preset mapping
        if "_nvenc" in (vcodec or ""):
            preset = self._nvenc_preset_for(preset)

        # 10) Pixel format check
        if not self._pixfmt_is_supported(vcodec, pix_fmt):
            pix_fmt = "yuv420p"

        # 11) Reasoning
        reasoning = (
            f"{goal.get('label', goal_key)} goal → {vcodec}, CRF {crf}, preset {preset}, "
            f"{'GPU' if use_gpu else 'CPU'} encode; "
            f"{'downscaled' if scale_h and scale_h < height else 'original res'}; "
            f"density={density:.5f}"
        )

        return {
            "scale_height": scale_h,
            "vcodec": vcodec,
            "crf": crf,
            "preset": preset,
            "pix_fmt": pix_fmt,
            "intent": goal_key,
            "reasoning": reasoning,
        }
