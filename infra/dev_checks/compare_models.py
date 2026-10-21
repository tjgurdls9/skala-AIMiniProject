"""Run the same micro tasks against several local models, one model and one task at a time, under the memory guard.

Usage: python infra/dev_checks/compare_models.py <out.json> <python@sha256:...> <node@sha256:...> <model[,model...]> <task[,task...]>
The run starts only on a ready machine, starts and ends its own `ollama serve`, checks that the previous model is unloaded before the next
one is used, and stops everything it started when memory runs short. Development check, not acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memory_guard as mg  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:11434"


def run_comparison(models, tasks, api, interval=4):
    report = dict(status="completed", reason="", runs=[])
    ok, why = mg.ready_to_start(api.sample())
    if not ok:
        return dict(report, status="not_started", reason=why)
    pid = api.start_server()
    try:
        for model in models:
            api.unload_all()
            if api.loaded_models():
                return dict(report, status="aborted", reason="이전 모델이 언로드되지 않았습니다. 한 번에 한 모델만 올립니다.")
            for task in tasks:
                ok, why = mg.ready_to_start(api.sample())
                if not ok:
                    return dict(report, status="stopped_before_run", reason=why)
                guard = mg.Guard(api.sample, lambda: api.stop_own(pid))
                handle = api.start_task(model, task)
                while handle.poll() is None:
                    if guard.step():
                        handle.terminate()
                        break
                    api.sleep(interval)
                peaks = dict(min_free_pct=guard.min_free_pct, max_swap_mb=guard.max_swap_mb, max_model_resident_mb=guard.max_resident_mb)
                if guard.tripped:
                    report["runs"].append(dict(model=model, task=task, outcome="자원 초과로 중단", guard=guard.tripped["reasons"], **peaks))
                    return dict(report, status="aborted_for_resources", reason="; ".join(guard.tripped["reasons"]))
                report["runs"].append(dict(model=model, task=task, outcome="finished", result=handle.result(), **peaks))
        return report
    finally:
        api.stop_own(pid)


class RealApi:
    def __init__(self, python_image, node_image, workdir):
        self.images, self.workdir, self.server = (python_image, node_image), Path(workdir), None

    sample = staticmethod(mg.sample)
    sleep = staticmethod(time.sleep)

    def start_server(self):
        env = dict(os.environ, OLLAMA_MODELS=str(ROOT / "runtime-data/models"), OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_NO_CLOUD="1")
        self.server = subprocess.Popen(["ollama", "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            try:
                urllib.request.urlopen(BASE + "/api/tags", timeout=2)
                return self.server.pid
            except OSError:
                time.sleep(1)
        raise RuntimeError("ollama serve did not become ready")

    def stop_own(self, pid):
        mg.stop_own_processes(pid)

    def loaded_models(self):
        return json.load(urllib.request.urlopen(BASE + "/api/ps", timeout=5))["models"]

    def unload_all(self):
        for model in self.loaded_models():
            request = urllib.request.Request(BASE + "/api/generate", json.dumps(dict(model=model["name"], keep_alive=0)).encode(), {"Content-Type": "application/json"})
            urllib.request.urlopen(request, timeout=60).read()
        for _ in range(20):
            if not self.loaded_models():
                return
            time.sleep(1)

    def start_task(self, model, task):
        out = self.workdir / f"{model.replace(':', '-')}-{task}.json"
        script = ["infra/dev_checks/concurrent_load.py", model, self.images[0]] if task == "concurrent-load" else \
                 ["infra/dev_checks/smoke_builder_loop.py", *self.images, model, task]
        process = subprocess.Popen([sys.executable, str(ROOT / script[0]), *script[1:]], stdout=out.open("w"), stderr=subprocess.DEVNULL)

        class Handle:
            def poll(self):
                return process.poll()

            def terminate(self):
                process.terminate()

            def result(self):
                return json.loads(out.read_text())
        return Handle()


if __name__ == "__main__":
    out_path, python_image, node_image, models, tasks = sys.argv[1:6]
    workdir = Path(out_path).parent
    report = run_comparison(models.split(","), tasks.split(","), RealApi(python_image, node_image, workdir))
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: report[k] for k in ("status", "reason")}, ensure_ascii=False))
