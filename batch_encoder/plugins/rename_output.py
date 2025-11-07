"""
rename_output.py — example plugin
---------------------------------
Renames successfully encoded outputs by appending a suffix to the stem.

Behavior:
- On successful encode (status == "ok"): dst -> dst_with_suffix
- If the target name exists, auto-add numeric suffix (_1, _2, ...) to avoid collisions.
- Logs actions via api.log().
"""

import shutil
from pathlib import Path


SUFFIX = "_encoded"  # configurable suffix


def register_plugin(api):
    """Register the plugin for the after_encode hook."""
    api.on_encode_finished(lambda job, result: _rename_on_success(job, result, api))


def _rename_on_success(job, result, api):
    """Rename encoded output safely across all OSes."""
    try:
        if not result or result.get("status") != "ok":
            return

        dst: Path = job.dst
        if not dst.exists():
            return

        target = dst.with_stem(dst.stem + SUFFIX)
        if target == dst:
            return  # already renamed somehow

        # Avoid collisions (e.g. if file already exists)
        i = 1
        cur = target
        while cur.exists():
            cur = target.with_stem(f"{target.stem}_{i}")
            i += 1

        # Try rename first; fallback to move for cross-device operations
        try:
            dst.rename(cur)
        except OSError:
            shutil.move(str(dst), str(cur))

        api.log(f"[rename_output] {dst.name} → {cur.name}", level="success")

    except Exception as e:
        api.log(f"[rename_output] rename failed: {e}", level="error")
