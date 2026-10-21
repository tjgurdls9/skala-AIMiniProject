"""Memory guard for comparisons that run a local model and containers together on a 16GB machine (macOS).

A breach is free memory under 15% or swap over 4GB; two consecutive breaches stop ONLY the ollama process this run started and
the `lifecycle-` containers, and the run is recorded as stopped for resources. A run may start only with at least 40% free memory
and under 2GB of swap. Usage as a plain sampler: python memory_guard.py <out.jsonl> [interval_seconds]"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request

FREE_MIN_PCT, SWAP_MAX_MB, CONSECUTIVE = 15, 4096, 2
START_FREE_PCT, START_SWAP_MB = 40, 2048
GRACE_SECONDS = 3


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=20).stdout


def sample():
    swap = re.search(r"used = ([\d.]+)M", run("sysctl", "-n", "vm.swapusage"))
    free = re.search(r"free percentage: (\d+)%", run("memory_pressure"))
    try:
        loaded = json.load(urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3))["models"]
    except Exception:  # noqa: BLE001 - the server may be between requests or down
        loaded = []
    stats = [line for line in run("docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}").splitlines() if line.startswith("lifecycle-")]
    return dict(t=round(time.time(), 1), swap_used_mb=float(swap.group(1)) if swap else None, system_free_pct=int(free.group(1)) if free else None,
                model_resident_mb=round(sum(m.get("size", 0) for m in loaded) / 1048576), containers=len(stats), container_mem=stats[:4])


def breaches(value):
    """Reasons this sample is unsafe; a figure that could not be read counts as unsafe, never as healthy."""
    reasons = []
    free, swap = value.get("system_free_pct"), value.get("swap_used_mb")
    if free is None or swap is None:
        reasons.append("메모리 측정값을 읽을 수 없습니다.")
        return reasons
    if free < FREE_MIN_PCT:
        reasons.append(f"여유 메모리 {free}% < {FREE_MIN_PCT}%")
    if swap > SWAP_MAX_MB:
        reasons.append(f"스왑 사용 {swap:.0f}MB > {SWAP_MAX_MB}MB")
    return reasons


def ready_to_start(value):
    free, swap = value.get("system_free_pct"), value.get("swap_used_mb")
    if free is None or swap is None:
        return False, "메모리 측정값을 읽을 수 없어 시작하지 않습니다."
    if free < START_FREE_PCT or swap >= START_SWAP_MB:
        return False, f"시작 조건 미충족: 여유 {free}%(필요 {START_FREE_PCT}% 이상), 스왑 {swap:.0f}MB(필요 {START_SWAP_MB}MB 미만)"
    return True, f"시작 가능: 여유 {free}%, 스왑 {swap:.0f}MB"


def stop_own_processes(ollama_pid, kill=os.kill, run=subprocess.run, alive=None, wait=time.sleep):
    """End the ollama process this run started (TERM, then KILL if it stays) and remove only containers named `lifecycle-*`."""
    alive = alive or (lambda pid: subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode == 0)
    if isinstance(ollama_pid, int) and ollama_pid > 1 and ollama_pid != os.getpid():
        try:
            kill(ollama_pid, signal.SIGTERM)
            wait(GRACE_SECONDS)
            if alive(ollama_pid):
                kill(ollama_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass   # already ended (the cleanup may run twice); the containers below are still removed
    listing = run(["docker", "ps", "-a", "--filter", "name=lifecycle-", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=30)
    for name in listing.stdout.split():
        if name.startswith("lifecycle-"):
            run(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=60)


class Guard:
    def __init__(self, sample_fn, stop_fn):
        self.sample_fn, self.stop_fn = sample_fn, stop_fn
        self.consecutive, self.tripped = 0, None
        self.min_free_pct = self.max_swap_mb = self.max_resident_mb = None

    def step(self):
        if self.tripped:
            return True
        value = self.sample_fn()
        free, swap, resident = value.get("system_free_pct"), value.get("swap_used_mb"), value.get("model_resident_mb") or 0
        self.min_free_pct = free if self.min_free_pct is None or (free is not None and free < self.min_free_pct) else self.min_free_pct
        self.max_swap_mb = swap if self.max_swap_mb is None or (swap is not None and swap > self.max_swap_mb) else self.max_swap_mb
        self.max_resident_mb = max(self.max_resident_mb or 0, resident)
        reasons = breaches(value)
        self.consecutive = self.consecutive + 1 if reasons else 0
        if self.consecutive >= CONSECUTIVE:
            self.tripped = dict(reasons=reasons, consecutive=self.consecutive, sample=value)
            self.stop_fn()
            return True
        return False


if __name__ == "__main__":
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 4
    with open(sys.argv[1], "a") as out:
        while True:
            out.write(json.dumps(sample()) + "\n")
            out.flush()
            time.sleep(interval)
