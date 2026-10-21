"""Development check: hold a model resident while one container uses memory, to measure them together (run under compare_models.py's guard).
Usage: python concurrent_load.py <model> <python@sha256:...>   Prints one JSON object."""
import json
import subprocess
import sys
import time
import urllib.request
import uuid

HOLD_SCRIPT = "b = bytearray(400 * 1024 * 1024)\nfor i in range(0, len(b), 4096):\n b[i] = 1\nimport time\ntime.sleep(15)\nprint('held 400MB')"


def chat_payload(model):
    return dict(model=model, stream=False, keep_alive="2m", think=False, messages=[dict(role="user", content="ok")],
                options=dict(num_ctx=16384, num_predict=8, temperature=0))


def container_args(name, image):
    return ["docker", "run", "--rm", "--name", name, "--network", "none", "--user", "65534:65534", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", "512m", "--memory-swap", "512m", "--cpus", "1",
            image, "python", "-c", HOLD_SCRIPT]


def main(model, image):
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat", json.dumps(chat_payload(model)).encode(), {"Content-Type": "application/json"})
    began = time.monotonic()
    urllib.request.urlopen(request, timeout=300).read()
    loaded = round(time.monotonic() - began, 1)
    done = subprocess.run(container_args("lifecycle-memcheck-" + uuid.uuid4().hex[:8], image), capture_output=True, text=True, timeout=120)
    print(json.dumps(dict(model=model, load_seconds=loaded, container_exit=done.returncode, container_output=done.stdout.strip(), outcome="measured")))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
