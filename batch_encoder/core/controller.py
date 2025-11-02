"""
controller.py
--------------
Handles encoding orchestration, pause/resume/stop, plugin hooks, and
REAL progress tracking:
- Per-worker % from parsed ffmpeg time / job.duration_s
- Overall % = sum(all jobs' encoded seconds) / sum(all jobs' durations)
"""

from __future__ import annotations
import threading, subprocess, time, os, queue
from typing import List, Dict, Optional

import psutil
from .models import Job
from batch_encoder.gui.localization import _
from batch_encoder import config
from .plugin_api import load_plugins
from .ffmpeg_utils import build_ffmpeg_cmd


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
                self._terminate_all_process_trees(grace_seconds=2.0)
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
                    self._print_q.put(("done", widx))
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

        self._log(_("ctrl_encoding_start").format(name=job.src.name), "info")
        rec = state["jobs"].setdefault(job.src.name, {"status": "pending", "settings": job.settings})

        # Use pre-probed duration for progress tracking
        duration = max(0.0, float(job.stats.get("duration_s") or 0.0))
        if duration > 0:
            self._log(f"[DEBUG] Using duration={duration:.2f}s for {job.src.name}", "debug")

        settings = job.settings.copy()
        try:
            self.plugin_api.trigger("modify_settings", job, settings)
        except Exception:
            pass

        cmd = build_ffmpeg_cmd(job.src, job.dst, settings)
        # Ensure -stats and -loglevel info
        if "-loglevel" in cmd:
            if "-stats" not in cmd:
                cmd.insert(cmd.index("-loglevel"), "-stats")
            idx = cmd.index("-loglevel") + 1
            cmd[idx] = "info"

        self._log(_("ctrl_cmd").format(cmd=" ".join(cmd)), "info")

        try:
            self.plugin_api.trigger("before_encode", job, settings)
        except Exception:
            pass

        proc = None
        try:
            self._wait_if_paused()
            if not self.running or self._stop_event.is_set():
                return

            creation = 0
            if os.name == "nt":
                creation = config.CREATE_NO_WINDOW | getattr(config, "CREATE_NEW_PROCESS_GROUP", 0)

            with self._spawn_gate:
                if not self.running or self._stop_event.is_set():
                    return
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    creationflags=creation,
                )
                self._processes[proc.pid] = proc
                self._log(f"[DEBUG] Spawned PID={proc.pid} for {job.src.name}", "info")

            if self.paused:
                self._async(self._suspend_process, proc.pid)

            # --- Read ffmpeg output and compute true % progress ---
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

                # clamp to job duration
                if duration > 0:
                    pct_worker = max(0.0, min((current_s / duration) * 100.0, 100.0))
                else:
                    pct_worker = 0.0

                # update per-job encoded seconds
                with self._progress_lock:
                    key = self._job_key(job)
                    prev = self._progress_secs.get(key, 0.0)
                    self._progress_secs[key] = max(prev, min(current_s, duration if duration > 0 else current_s))
                    overall_pct = self._compute_overall_pct_locked()

                now = time.time()
                if now - last_emit > 0.5:  # update UI ~2x per second
                    self._print_q.put(("progress", widx, job.src.name, pct_worker))
                    self._print_q.put(("overall", None, None, overall_pct))
                    last_emit = now

            try:
                proc.wait(timeout=2.0)
            except Exception:
                pass

            ret = proc.returncode if proc.returncode is not None else -1
            # on completion, finalize this job to its full duration
            with self._progress_lock:
                key = self._job_key(job)
                if duration > 0:
                    self._progress_secs[key] = duration
                overall_pct = self._compute_overall_pct_locked()
            # emit a final overall update
            self._print_q.put(("overall", None, None, overall_pct))

            if not self.running or self._stop_event.is_set():
                self._terminate_pid_tree(proc.pid, grace_seconds=0.8)

            result = {"returncode": ret, "dst": job.dst}
            if ret == 0:
                rec["status"] = "done"
                result["status"] = "ok"
                self._log(_("ctrl_job_done").format(name=job.src.name), "success")
            else:
                rec["status"] = "error"
                result["status"] = "fail"
                self._log(_("ctrl_job_fail").format(name=job.src.name, code=ret), "error")

            try:
                self.plugin_api.trigger("after_encode", job, result)
            except Exception:
                pass

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
        """Call with self._progress_lock held."""
        total = self._session_total_secs
        if total <= 0:
            return 0.0
        done = sum(self._progress_secs.values())
        pct = max(0.0, min((done / total) * 100.0, 100.0))
        return pct

    # ---------------- Process control helpers ----------------

    def _suspend_all_processes(self):
        with self._lock:
            pids = list(self._processes.keys())
        for pid in pids:
            self._suspend_process(pid)

    def _resume_all_processes(self):
        with self._lock:
            pids = list(self._processes.keys())
        for pid in pids:
            self._resume_process(pid)

    def _suspend_process(self, pid: int):
        try:
            psutil.Process(pid).suspend()
        except Exception:
            pass

    def _resume_process(self, pid: int):
        try:
            psutil.Process(pid).resume()
        except Exception:
            pass

    def _terminate_all_process_trees(self, grace_seconds: float = 3.0):
        with self._lock:
            pids = list(self._processes.keys())
        for pid in pids:
            self._terminate_pid_tree(pid, grace_seconds)
        with self._lock:
            self._processes.clear()

    def _terminate_pid_tree(self, pid: int, grace_seconds: float = 1.5):
        try:
            parent = psutil.Process(pid)
        except Exception:
            return
        procs = [parent] + parent.children(recursive=True)
        for p in procs:
            try:
                p.terminate()
                self._log(_("ctrl_terminated").format(pid=p.pid), "warn")
            except Exception:
                pass
        t_end = time.time() + grace_seconds
        while time.time() < t_end:
            if all(self._is_proc_dead(p) for p in procs):
                break
            time.sleep(0.1)
        for p in procs:
            try:
                if p.is_running():
                    p.kill()
                    self._log(f"[DEBUG] Force-killed PID={p.pid}", "error")
            except Exception:
                pass

    @staticmethod
    def _is_proc_dead(p: psutil.Process) -> bool:
        try:
            return (not p.is_running()) or (p.status() == psutil.STATUS_ZOMBIE)
        except Exception:
            return True

    # ---------------- Helpers ----------------

    def _wait_if_paused(self, runtime_pid: int | None = None):
        with self._pause_cond:
            while self.paused:
                if runtime_pid:
                    self._suspend_process(runtime_pid)
                self._pause_cond.wait()
            if runtime_pid:
                self._resume_process(runtime_pid)

    def _job_key(self, job: Job) -> str:
        # unique key for the session
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
