"""
controller.py
--------------
Handles encoding orchestration, pause/resume/stop, plugin hooks, and
REAL progress tracking:
- Per-worker % from parsed ffmpeg time / job.duration_s
- Overall % = sum(all jobs' encoded seconds) / sum(all jobs' durations)
"""

from __future__ import annotations
import threading, subprocess, time, os, queue, ctypes
from typing import List, Dict, Optional
import psutil

from .models import Job
from batch_encoder.gui.localization import _
from batch_encoder import config
from .plugin_api import load_plugins
from .ffmpeg_utils import build_ffmpeg_cmd
from .system_utils import (
    suspend_process,
    resume_process,
    terminate_process_tree,
    safe_creation_flags,
    is_windows,
)


class EncoderController:
    """Manages encoding threads, progress, plugins, and runtime communication."""

    def __init__(self, gui=None):
        self.gui = gui
        self.settings = gui.settings if gui else None

        # Jobs / workers
        self.jobs: List[Job] = []
        self.workers: List[threading.Thread] = []

        # Runtime flags
        self.running = False
        self.paused = False
        self._stop_event = threading.Event()

        # Concurrency primitives
        self._lock = threading.Lock()
        self._pause_cond = threading.Condition(self._lock)
        self._spawn_gate = threading.Lock()

        # pid -> Popen
        self._processes: Dict[int, subprocess.Popen] = {}

        # Outgoing messages to GUI
        self._print_q: queue.Queue = gui.print_q if gui else queue.Queue()

        # Plugins
        self.plugin_api = load_plugins(
            package_root="batch_encoder",
            logger=lambda msg, line, level: self._print_q.put(("log", None, msg, level))
        )

        self._manager_thread: Optional[threading.Thread] = None

        # ---- Session-wide progress accounting (duration-weighted) ----
        self._session_total_secs: float = 0.0
        self._progress_secs: Dict[str, float] = {}  # key: job key -> encoded seconds
        self._progress_lock = threading.Lock()

    # ---------------- Public integration points ----------------

    def set_plugin_api(self, api) -> None:
        if api:
            with self._lock:
                self.plugin_api = api

    # ---------------- Start / Stop / Pause ----------------

    def start_encoding(self, jobs: List[Job], perf_defaults: dict):
        if self.running:
            self._log(_("ctrl_already_running"), "warn")
            return

        self.jobs = jobs
        self.workers = []
        self.running = True
        self.paused = False
        self._stop_event.clear()

        # Compute total session duration ONCE (single source of truth)
        with self._progress_lock:
            self._progress_secs = {}
            self._session_total_secs = 0.0
            for j in self.jobs:
                dur = float(j.stats.get("duration_s") or 0.0)
                self._session_total_secs += max(0.0, dur)
                self._progress_secs[self._job_key(j)] = 0.0

        max_workers = perf_defaults.get("max_workers", 2)
        self._log(_("ctrl_starting").format(count=len(jobs), workers=max_workers), "title")
        self._log(f"[DEBUG] Session total duration: {self._session_total_secs:.2f}s", "debug")

        self._manager_thread = threading.Thread(
            target=self._manager_thread_func,
            args=(perf_defaults,),
            daemon=True,
        )
        self._manager_thread.start()

    def toggle_pause(self) -> bool:
        do_suspend = do_resume = False
        with self._pause_cond:
            if not self.paused:
                self.paused = True
                do_suspend = True
                self._log(_("ctrl_paused"), "warn")
            else:
                self.paused = False
                do_resume = True
                self._pause_cond.notify_all()
                self._log(_("ctrl_resumed"), "info")

        if do_suspend:
            self._async(self._suspend_all_processes)
        elif do_resume:
            self._async(self._resume_all_processes)
        return self.paused

    def stop_all_processes(self):
        self._log("Stopping workers... Please wait...", "warn")
        self._stop_event.set()
        with self._pause_cond:
            was_paused = self.paused
            self.running = False
            self.paused = False
            self._pause_cond.notify_all()
        if was_paused:
            self._resume_all_processes()
        self._async(self._graceful_stop_loop)

    # ---------------- Graceful Stop Loop ----------------

    def _graceful_stop_loop(self):
        """Repeatedly attempt cleanup until all processes and threads are dead."""
        for attempt in range(10):
            self._log(f"[STOP] Cleanup pass {attempt + 1} — initiating termination cycle...", "warn")
            with self._spawn_gate:
                for pid in list(self._processes.keys()):
                    terminate_process_tree(pid, grace_seconds=2.0)
            self._join_all_threads(timeout=1.0)

            leftovers = self._count_leftovers()
            if leftovers == 0:
                self._log("Stopped all workers.", "warn")
                return

            self._log(f"[STOP] {leftovers} leftover(s) detected. Retrying in 5 seconds...", "warn")
            time.sleep(5)
        self._log("[STOP] Force stop timed out — some processes may still be alive.", "error")

    def _count_leftovers(self) -> int:
        active_pids = []
        with self._lock:
            for pid in list(self._processes.keys()):
                try:
                    p = psutil.Process(pid)
                    if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                        active_pids.append(pid)
                except Exception:
                    continue
        alive_threads = sum(1 for t in self.workers if t.is_alive())
        total = len(active_pids) + alive_threads
        self._log(f"[DEBUG] Leftover check → {len(active_pids)} ffmpeg, {alive_threads} threads.", "info")
        return total

    def _join_all_threads(self, timeout: float = 1.0):
        with self._lock:
            threads = list(self.workers)
        for t in threads:
            try:
                if t.is_alive():
                    t.join(timeout=timeout)
            except Exception:
                pass

    # ---------------- Main Manager Thread ----------------

    def _manager_thread_func(self, perf_defaults: dict):
        total_cores = perf_defaults.get("cpu_cores", psutil.cpu_count(logical=True))
        max_workers = perf_defaults.get("max_workers", 2)
        state = {"jobs": {}, "active": 0}
        sem = threading.Semaphore(max_workers)

        def worker_func(widx: int, job: Job):
            with sem:
                try:
                    if not self.running or self._stop_event.is_set():
                        return
                    self._encode_job(widx, job, total_cores, state)
                finally:
                    self._print_q.put(("done", widx, job, None))
                    state["active"] -= 1

        for i, job in enumerate(self.jobs):
            if not self.running or self._stop_event.is_set():
                break
            self._wait_if_paused()
            if not self.running or self._stop_event.is_set():
                break
            t = threading.Thread(target=worker_func, args=(i % max_workers, job), daemon=True)
            state["active"] += 1
            t.start()
            self.workers.append(t)

        while any(t.is_alive() for t in self.workers):
            self._wait_if_paused()
            if not self.running or self._stop_event.is_set():
                break
            time.sleep(0.2)

        for t in self.workers:
            t.join(timeout=1.0)
        self.running = False
        self._log(_("ctrl_all_done"), "success")

    # ---------------- Job Encoding ----------------

    def _encode_job(self, widx: int, job: Job, total_cores: int, state: dict, attempt: int = 1):
        if not job or not self.running or self._stop_event.is_set():
            return

        self._print_q.put(("worker_start", widx, job.src.name, None))
        self._log(_("ctrl_encoding_start").format(name=job.src.name), "info")
        rec = state["jobs"].setdefault(job.src.name, {"status": "pending", "settings": job.settings})

        duration = max(0.0, float(job.stats.get("duration_s") or 0.0))
        settings = job.settings.copy()
        cmd = build_ffmpeg_cmd(job.src, job.dst, settings)

        if "-loglevel" in cmd and "-stats" not in cmd:
            cmd.insert(cmd.index("-loglevel"), "-stats")

        self._log(_("ctrl_cmd").format(cmd=" ".join(cmd)), "info")

        proc = None
        try:
            creation = safe_creation_flags()
            with self._spawn_gate:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    creationflags=creation,
                )
                self._processes[proc.pid] = proc
                self._log(f"[DEBUG] Spawned PID={proc.pid} for {job.src.name}", "info")
                self._set_process_affinity(proc, widx, total_cores)

            if self.paused:
                self._async(self._suspend_process, proc.pid)

            last_emit = 0.0
            for line in iter(proc.stdout.readline, ''):
                if not self.running or self._stop_event.is_set():
                    break
                self._wait_if_paused(runtime_pid=proc.pid)
                if "time=" not in line:
                    continue

                current_s = self._parse_seconds(line)
                if current_s is None:
                    continue

                pct_worker = (current_s / duration) * 100 if duration > 0 else 0.0
                pct_worker = max(0.0, min(pct_worker, 100.0))

                with self._progress_lock:
                    key = self._job_key(job)
                    prev = self._progress_secs.get(key, 0.0)
                    self._progress_secs[key] = max(prev, min(current_s, duration))
                    overall_pct = self._compute_overall_pct_locked()

                now = time.time()
                if now - last_emit > 0.5:
                    self._print_q.put(("progress", widx, job.src.name, pct_worker))
                    self._print_q.put(("overall", None, None, overall_pct))
                    last_emit = now

            try:
                proc.wait(timeout=2.0)
            except Exception:
                pass

            ret = proc.returncode if proc.returncode is not None else -1
            with self._progress_lock:
                key = self._job_key(job)
                if duration > 0:
                    self._progress_secs[key] = duration
                overall_pct = self._compute_overall_pct_locked()
            self._print_q.put(("overall", None, None, overall_pct))

            if not self.running or self._stop_event.is_set():
                terminate_process_tree(proc.pid, grace_seconds=0.8)

            result = {"returncode": ret, "dst": job.dst}
            if ret == 0:
                rec["status"] = "done"
                result["status"] = "ok"
                self._log(_("ctrl_job_done").format(name=job.src.name), "success")
            else:
                rec["status"] = "error"
                result["status"] = "fail"
                self._log(_("ctrl_job_fail").format(name=job.src.name, code=ret), "error")

        except Exception as e:
            self._log(_("ctrl_job_exception").format(name=job.src.name, err=e), "error")
        finally:
            if proc:
                self._processes.pop(proc.pid, None)
                self._log(f"[DEBUG] PID {proc.pid} removed from process list.", "info")

    # ---------------- Progress helpers ----------------

    @staticmethod
    def _parse_seconds(line: str) -> Optional[float]:
        import re
        try:
            m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
            if not m:
                return None
            h, m_, s = map(float, m.groups())
            return h * 3600 + m_ * 60 + s
        except Exception:
            return None

    def _compute_overall_pct_locked(self) -> float:
        total = self._session_total_secs
        if total <= 0:
            return 0.0
        done = sum(self._progress_secs.values())
        return max(0.0, min((done / total) * 100.0, 100.0))

    # ---------------- Process control helpers ----------------

    def _set_process_affinity(self, proc: subprocess.Popen, widx: int, total_cores: int):
        """Platform-safe CPU affinity — fully preserved from original."""
        try:
            total = total_cores or os.cpu_count() or 1
            n_workers = max(1, len(self.workers))
            per_worker = max(1, total // n_workers)

            start = widx * per_worker
            end = min(start + per_worker, total)
            if start >= total:
                start = widx % total
                end = start + 1

            allowed_cores = list(range(start, end))
            if is_windows():
                mask = sum(1 << c for c in allowed_cores)
                PROCESS_SET_INFORMATION = 0x0200
                PROCESS_QUERY_INFORMATION = 0x0400
                handle = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION, False, proc.pid
                )
                if handle:
                    ctypes.windll.kernel32.SetProcessAffinityMask(handle, mask)
                    ctypes.windll.kernel32.CloseHandle(handle)
                    self._log(f"[DEBUG] Set Win32 affinity PID={proc.pid} -> {allowed_cores}", "debug")
            else:
                psutil.Process(proc.pid).cpu_affinity(allowed_cores)
                self._log(f"[DEBUG] Set affinity PID={proc.pid} -> cores {allowed_cores}", "debug")
        except Exception as e:
            self._log(f"[WARN] Affinity set failed: {e}", "warning")

    def _suspend_all_processes(self):
        with self._lock:
            for pid in list(self._processes.keys()):
                suspend_process(pid)

    def _resume_all_processes(self):
        with self._lock:
            for pid in list(self._processes.keys()):
                resume_process(pid)

    # ---------------- Helpers ----------------

    def _wait_if_paused(self, runtime_pid: int | None = None):
        with self._pause_cond:
            while self.paused:
                if runtime_pid:
                    suspend_process(runtime_pid)
                self._pause_cond.wait()
            if runtime_pid:
                resume_process(runtime_pid)

    def _job_key(self, job: Job) -> str:
        return str(job.src.resolve())

    def _log(self, msg: str, level: str = "info"):
        self._print_q.put(("log", None, msg, level))

    @staticmethod
    def _async(fn, *args, **kwargs):
        try:
            threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()
        except Exception:
            try:
                fn(*args, **kwargs)
            except Exception:
                pass
