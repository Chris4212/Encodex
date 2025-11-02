"""
impact_estimator.py
-------------------
Smart-aware estimator for Batch Encoder.

Estimates output size, percentage change, quality impact, and reasoning
based on both Smart Mode policy (intent/goal) and manual settings.
"""

from __future__ import annotations
from typing import Dict, Any
from .. import config


class ImpactEstimator:
    """Evaluates how chosen encoding settings will affect output."""

    # ------------------------------------------------------------------
    def estimate(self, info: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        try:
            meta = self._extract_metrics(info)
            width = meta.get("width", 0)
            height = meta.get("height", 0)
            fps = float(meta.get("fps", 0.0))
            src_bitrate = float(meta.get("bitrate_mbps", 0.0))
            duration = float(meta.get("duration_s", 0.0))
            codec_in = (meta.get("codec") or "").lower()

            codec_out = (settings.get("vcodec") or settings.get("codec") or "").lower()
            crf = float(settings.get("crf", 26))
            preset = (settings.get("preset") or "").lower()
            goal_key = settings.get("goal", "balanced")
            print("goal_key in estimate: ", goal_key)
            use_gpu = "nvenc" in codec_out or settings.get("use_gpu", False)

            # ------------------------------------------------------------------
            # Compute bitrate density (source)
            # ------------------------------------------------------------------
            density = (src_bitrate * 1_000_000) / max(width * height * fps, 1)

            # ------------------------------------------------------------------
            # Efficiency table
            # ------------------------------------------------------------------
            codec_eff = {
                "libx265": 0.55, "hevc": 0.55, "h265": 0.55,
                "libx264": 0.90, "h264": 0.90,
                "av1": 0.40, "vp9": 0.60,
                "av1_nvenc": 0.45, "hevc_nvenc": 0.60, "h264_nvenc": 1.00,
            }
            factor = codec_eff.get(codec_out, 0.75)
            if use_gpu:
                # GPU encoders often sacrifice ~5–10% compression efficiency
                factor *= 1.05

            # ------------------------------------------------------------------
            # CRF and goal bias
            # ------------------------------------------------------------------
            crf_scale = 26.0 / crf if crf > 0 else 1.0
            goal_bias = self._goal_bias(goal_key)

            # ------------------------------------------------------------------
            # Estimate output bitrate (Mbps)
            # ------------------------------------------------------------------
            out_bitrate = src_bitrate * factor * crf_scale * goal_bias
            out_bitrate = max(0.3, min(out_bitrate, src_bitrate * 1.2))

            # ------------------------------------------------------------------
            # Estimate output size & reduction %
            # ------------------------------------------------------------------
            out_size_mb = (out_bitrate * duration) / 8.0
            src_size_mb = (src_bitrate * duration) / 8.0 if src_bitrate > 0 else out_size_mb
            reduction_pct = ((out_size_mb - src_size_mb) / src_size_mb * 100.0) if src_size_mb > 0 else 0.0

            # ------------------------------------------------------------------
            # Impact classification (goal-aware)
            # ------------------------------------------------------------------
            if goal_key in ("archive", "lossless"):
                # Treat all results as visually identical unless extreme
                if reduction_pct > -5:
                    impact, quality = "balanced", "≈ same"
                elif reduction_pct < -30:
                    impact, quality = "efficient", "≈ same"
                else:
                    impact, quality = "efficient", "≈ same"
            else:
                # dynamic thresholds: stricter for archival, looser for mobile
                if goal_key in ("speed", "mobile", "size"):
                    t_eff, t_bal = -20, -5
                else:
                    t_eff, t_bal = -35, -12

                if reduction_pct < t_eff:
                    impact, quality = "efficient", "≈ same"
                elif reduction_pct < t_bal:
                    impact, quality = "balanced", "slightly lower"
                else:
                    impact, quality = "aggressive", "noticeable loss"

            # ------------------------------------------------------------------
            # Compose reasoning and friendly info
            # ------------------------------------------------------------------
            reason = self._derive_reason(meta, settings, impact, quality)
            info = self._info_text(impact, quality, goal_key, use_gpu, density, reduction_pct)

            return {
                "expected_size_mb": round(out_size_mb, 1),
                "reduction_pct": round(reduction_pct, 1),
                "quality": quality,
                "impact": impact,
                "reason": reason,
                "info": info,
            }

        except Exception as e:
            return {
                "expected_size_mb": 0.0,
                "reduction_pct": 0.0,
                "quality": "unknown",
                "impact": "unknown",
                "reason": f"Estimation failed: {e}",
                "info": f"Estimation failed: {e}",
            }

    # ------------------------------------------------------------------
    def _goal_bias(self, goal: str) -> float:
        """Returns a bitrate adjustment multiplier per encoding goal."""
        g = (goal or "balanced").lower()
        bias_map = {
            "speed": 1.05,
            "mobile": 1.10,
            "balanced": 1.00,
            "quality": 0.95,
            "archive": 0.90,
            "lossless": 0.85,
            "size": 1.08,
            "web": 1.02,
            "neutral": 1.00,
        }
        return bias_map.get(g, 1.0)

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_metrics(info: Dict[str, Any]) -> Dict[str, Any]:
        fmt = info.get("format", {}) or {}
        streams = info.get("streams", []) or []
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        width = int(v.get("width") or 0)
        height = int(v.get("height") or 0)
        codec = (v.get("codec_name") or "").lower()
        afr = v.get("avg_frame_rate") or "0/1"
        try:
            n, d = [float(x) for x in afr.split("/")]
            fps = n / d if d else 0.0
        except Exception:
            fps = 0.0
        try:
            duration = float(fmt.get("duration") or 0.0)
            bitrate = float(fmt.get("bit_rate") or 0.0) / 1_000_000.0
        except Exception:
            duration, bitrate = 0.0, 0.0
        return {"width": width, "height": height, "codec": codec,
                "fps": fps, "duration_s": duration, "bitrate_mbps": bitrate}

    # ------------------------------------------------------------------
    def _derive_reason(self, meta: Dict[str, Any], settings: Dict[str, Any],
                       impact: str, quality: str) -> str:
        """Generate technical reasoning summary for advanced view."""
        codec_in = (meta.get("codec") or "").lower()
        codec_out = (settings.get("vcodec") or settings.get("codec") or "").lower()
        crf = float(settings.get("crf", 26))
        preset = (settings.get("preset") or "").lower()
        height = meta.get("height", 0)
        fps = float(meta.get("fps", 0.0))
        br = float(meta.get("bitrate_mbps", 0.0))

        parts = []

        # Codec context
        if codec_in != codec_out:
            if "av1" in codec_out:
                parts.append("AV1 chosen for next-gen compression.")
            elif "hevc" in codec_out or "265" in codec_out:
                parts.append("HEVC (H.265) provides higher compression efficiency.")
            elif "h264" in codec_out:
                parts.append("H.264 selected for compatibility.")
            else:
                parts.append("Custom codec choice.")
        else:
            parts.append("Re-encoding with same codec (near-lossless).")

        # Quality context
        if crf <= 20:
            parts.append("Very high quality setting.")
        elif crf <= 26:
            parts.append("Balanced visual quality.")
        elif crf <= 30:
            parts.append("Moderate compression — minor detail loss.")
        else:
            parts.append("Heavy compression may affect fine detail.")

        # Preset context
        if "slow" in preset:
            parts.append("Preset favors quality over speed.")
        elif "fast" in preset:
            parts.append("Preset prioritizes speed over efficiency.")

        # Resolution and bitrate
        if height >= 2160 and br < 8:
            parts.append("4K source with limited bitrate — fine detail constrained.")
        elif height <= 720 and impact == "efficient":
            parts.append("Low-res content allows high compression gains.")
        elif 1080 <= height < 2160 and br > 20:
            parts.append("High-bitrate HD source — safe for compression.")

        if fps > 90:
            parts.append("High frame rate — motion-heavy content harder to compress.")

        # Impact summary
        if impact == "efficient":
            parts.append("Excellent compression ratio with minimal visual loss.")
        elif impact == "balanced":
            parts.append("Reasonable size reduction with minimal degradation.")
        elif impact == "aggressive":
            parts.append("Marginal space savings versus quality impact.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    def _info_text(self, impact: str, quality: str, goal: str,
                   use_gpu: bool, density: float, reduction: float) -> str:
        """Human-friendly summary for UI display."""
        g = (goal or "").lower()
        print("Goal in _info_text: ", goal)

        # Goal-based prefixes (intent context)
        prefix_map = {
            "archive": "Archival intent — ",
            "lossless": "Archival intent — ",
            "mobile": "Optimized for portability — ",
            "size": "Optimized for storage — ",
            "speed": "Performance-focused — ",
            "quality": "Quality-focused — ",
            "web": "Streaming-ready — ",
        }
        prefix = prefix_map.get(g, "")

        # Goal-aware hard overrides (always take precedence)
        if g in ("archive", "lossless"):
            base = "Lossless or near-lossless encoding; no quality degradation expected."
        else:
            # Combine impact + quality context
            if impact == "efficient":
                if "≈" in quality or "same" in quality.lower():
                    base = "Efficient compression — no visible loss expected."
                else:
                    base = "Efficient compression with excellent visual fidelity."
            elif impact == "balanced":
                if "slightly" in quality.lower():
                    base = "Balanced compression — mild reduction in fine detail."
                else:
                    base = "Balanced encoding — minor differences in complex scenes."
            elif impact == "aggressive":
                if "noticeable" in quality.lower():
                    base = "Aggressive compression — visible artifacts or color banding likely."
                else:
                    base = "Strong compression applied — visible degradation possible."
            else:
                base = "Visual impact uncertain."

        # GPU note (optional)
        gpu_note = " (hardware encode may slightly reduce compression efficiency)" if use_gpu else ""

        # Density and reduction details
        density_note = f" Density={density:.5f}, size change={reduction:+.0f}%."

        return f"{prefix}{base}{gpu_note}{density_note}"

