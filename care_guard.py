"""User Care's protection list: while one of these holds, User Care never shuts the PC down (a forced
break comes instead). Breaks and reminders don't care about it.

Rules (each with its own switch and limits in config.json, user_care.protect):
- programs: a process with one of these names is running (Claude Code is claude.exe).
- gpu: the GPU has been busy past `percent` for `minutes`, and the load comes from a process using the
  GPU's compute/cuda engine (training), not 3d (a game). Zyraena's own voice workers don't count.
- terminal_jobs: something started from a terminal (PowerShell, cmd, VS Code's terminal...) has used CPU
  for `minutes`. An idle open terminal doesn't count.
- training: a Python process whose command line contains one of `patterns` (training projects).
- zyraena_runs: a script Zyraena runs in the background (run_python) hasn't finished.
- busy_cpu: a background process (not the window in front, not Windows) has used more than `percent` of
  the whole CPU for `minutes`.
- downloads: a browser download is growing in the Downloads folder, or the PC has been receiving more
  than `mb_per_second` for `minutes`.

The "for N minutes" rules need history, so Guard.sample() runs about once a minute (user_care's loop).
"""
import ctypes
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import psutil

SHELLS = {"powershell.exe", "pwsh.exe", "cmd.exe", "bash.exe", "wsl.exe", "openconsole.exe",
          "windowsterminal.exe", "wt.exe"}
NOT_A_JOB = SHELLS | {"conhost.exe", "git.exe", "claude.exe"}  # claude.exe has its own rule
OWN_WORKERS = ("speech_worker", "tts_worker", "voice_worker", "claude_comm")
PARTIAL_DOWNLOADS = (".crdownload", ".opdownload", ".part", ".partial", ".download")
DOWNLOAD_FRESH_SECONDS = 120
GPU_COUNTER_TIMEOUT = 60
COMPUTE_ENGINES = ("compute", "cuda")


def _nvidia_utilization():
    """Total GPU utilization in percent (the busiest GPU), or None without nvidia-smi."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        values = [float(v) for v in out.split() if v.strip()]
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return max(values) if values else None


def _gpu_engines_by_pid():
    """{pid: {engine type: percent}} from Windows' GPU counters (takes a few seconds). Engine types are
    e.g. 3d, compute_0, cuda, copy, video decode."""
    script = ("(Get-Counter '\\GPU Engine(*)\\Utilization Percentage').CounterSamples | "
              "Where-Object CookedValue -gt 0 | ForEach-Object { $_.InstanceName + '=' + $_.CookedValue }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                             timeout=GPU_COUNTER_TIMEOUT, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    usage = {}
    for line in out.splitlines():
        match = re.match(r"pid_(\d+)_.*engtype_(.+?)=([\d.,]+)$", line.strip())
        if match:
            engines = usage.setdefault(int(match.group(1)), {})
            engine = match.group(2).lower()
            engines[engine] = engines.get(engine, 0) + float(match.group(3).replace(",", "."))
    return usage


def _foreground_pid():
    user32 = ctypes.windll.user32
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


def _cmdline(proc):
    try:
        return " ".join(proc.cmdline()).lower()
    except psutil.Error:
        return ""


class Guard:
    def __init__(self, own_pid=None, runs=None):
        """runs() -> how many of Zyraena's background scripts are still running (system_tools)."""
        self.own_pid = own_pid or os.getpid()
        self.runs = runs or (lambda: 0)
        self.since = {}       # rule -> time it started holding (the "for N minutes" rules)
        self.detail = {}      # rule -> what it saw, for the reason text
        self._cpu_seen = {}   # pid -> psutil.Process, so cpu_percent() measures since the last sample
        self._net = None      # (time, bytes received)
        self._lock = threading.Lock()

    # --- sampling (about once a minute) ------------------------------------------------------------

    def sample(self, cfg):
        """Measures the "for N minutes" rules. cfg: user_care.protect."""
        now = time.time()
        with self._lock:
            cpu = self._cpu_by_pid()
            self._hold("terminal_jobs", now, self._terminal_job(cpu, cfg["terminal_jobs"]))
            self._hold("busy_cpu", now, self._busy(cpu, cfg["busy_cpu"]))
            self._hold("downloads_net", now, self._receiving(now, cfg["downloads"]))
            self._hold("gpu", now, self._gpu_compute(cfg["gpu"]) if cfg["gpu"]["enabled"] else None)

    def _hold(self, rule, now, seen):
        if seen:
            self.since.setdefault(rule, now)
            self.detail[rule] = seen
        else:
            self.since.pop(rule, None)
            self.detail.pop(rule, None)

    def _held(self, rule, minutes):
        started = self.since.get(rule)
        return started is not None and time.time() - started >= minutes * 60

    def _own_tree(self):
        try:
            me = psutil.Process(self.own_pid)
            return {me.pid} | {c.pid for c in me.children(recursive=True)}
        except psutil.Error:
            return {self.own_pid}

    def _cpu_by_pid(self):
        """{pid: (process, percent of one core since the last sample)}; a new process reads 0 the first time."""
        usage, seen = {}, {}
        for proc in psutil.process_iter(["name"]):
            old = self._cpu_seen.get(proc.pid)
            proc = old if old is not None and old.is_running() else proc
            try:
                usage[proc.pid] = (proc, proc.cpu_percent(None))
                seen[proc.pid] = proc
            except psutil.Error:
                continue
        self._cpu_seen = seen
        return usage

    def _terminal_job(self, cpu, cfg):
        if not cfg["enabled"]:
            return None
        own = self._own_tree()
        for pid, (proc, percent) in cpu.items():
            if percent < cfg["cpu_percent"] or pid in own:
                continue
            try:
                if proc.name().lower() in NOT_A_JOB:
                    continue
                parents = [p.name().lower() for p in proc.parents()]
            except psutil.Error:
                continue
            if any(name in SHELLS for name in parents):
                return f"{proc.name()} (PID {pid})"
        return None

    def _busy(self, cpu, cfg):
        if not cfg["enabled"]:
            return None
        import system_tools

        own, user, front = self._own_tree(), psutil.Process().username(), _foreground_pid()
        cores = psutil.cpu_count() or 1
        for pid, (proc, percent) in sorted(cpu.items(), key=lambda item: -item[1][1]):
            if percent / cores < cfg["percent"]:
                break
            if pid in own or pid == front or system_tools._protected_reason(proc, own, user):
                continue
            return f"{proc.name()} (PID {pid}, {percent / cores:.0f}%)"
        return None

    def _receiving(self, now, cfg):
        if not cfg["enabled"]:
            return None
        received = psutil.net_io_counters().bytes_recv
        last, self._net = self._net, (now, received)
        if last is None or now <= last[0]:
            return None
        rate = (received - last[1]) / (now - last[0]) / 2**20
        return f"{rate:.1f} MB/s" if rate >= cfg["mb_per_second"] else None

    def _gpu_compute(self, cfg):
        total = _nvidia_utilization()
        if total is None or total < cfg["percent"]:
            return None
        own = self._own_tree()
        best = None
        for pid, engines in _gpu_engines_by_pid().items():
            compute = sum(v for k, v in engines.items() if k.startswith(COMPUTE_ENGINES))
            if compute < cfg["compute_percent"]:
                continue
            try:
                proc = psutil.Process(pid)
                if pid in own or any(w in _cmdline(proc) for w in OWN_WORKERS):
                    continue
                name = proc.name()
            except psutil.Error:
                continue
            if best is None or compute > best[1]:
                best = (f"{name} (PID {pid})", compute)
        return f"GPU {total:.0f}%, compute: {best[0]}" if best else None

    # --- the check ----------------------------------------------------------------------------------

    def reasons(self, cfg):
        """Why the PC must not be shut down now (empty list: it may). cfg: user_care.protect."""
        found = []
        wanted = {p.lower() for p in cfg["programs"]}
        names = set()
        training = cfg["training"]
        patterns = [p.lower().replace("/", "\\") for p in training["patterns"]] if training["enabled"] else []
        for proc in psutil.process_iter(["name"]):
            name = (proc.info["name"] or "").lower()
            if name in wanted:
                names.add(proc.info["name"])
            if patterns and name.startswith("python"):
                line = _cmdline(proc).replace("/", "\\")
                if not any(w in line for w in OWN_WORKERS):
                    hit = next((p for p in patterns if p in line), None)
                    if hit:
                        found.append(("training", f"{hit} (PID {proc.pid})"))
        found = [("program", n) for n in sorted(names)] + found
        if cfg["zyraena_runs"]["enabled"] and self.runs():
            found.append(("zyraena_runs", str(self.runs())))
        with self._lock:
            for rule, minutes, key in (("gpu", cfg["gpu"]["minutes"], "gpu"),
                                       ("terminal_jobs", cfg["terminal_jobs"]["minutes"], "terminal_jobs"),
                                       ("busy_cpu", cfg["busy_cpu"]["minutes"], "busy_cpu"),
                                       ("downloads_net", cfg["downloads"]["minutes"], "downloads")):
                if cfg[key]["enabled"] and self._held(rule, minutes):
                    found.append((rule, self.detail[rule]))
        if cfg["downloads"]["enabled"]:
            growing = _growing_download(cfg["downloads"]["folder"])
            if growing:
                found.append(("downloads", growing))
        return found


def _growing_download(folder):
    path = Path(os.path.expandvars(os.path.expanduser(folder)))
    try:
        entries = list(path.iterdir())
    except OSError:
        return None
    now = time.time()
    for entry in entries:
        try:
            if entry.suffix.lower() in PARTIAL_DOWNLOADS and now - entry.stat().st_mtime < DOWNLOAD_FRESH_SECONDS:
                return entry.name
        except OSError:
            continue
    return None
