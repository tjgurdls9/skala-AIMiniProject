"""Operator check of the real isolation the model tools rely on. No model is called.

Usage: backend/.venv/bin/python infra/verify_isolation.py <python@sha256:...> <node@sha256:...> [--network]
Without --network the registry proxy checks (one real PyPI install and one real npm install) are skipped.
Prints one JSON object with every check, its result and the evidence. Exit code 1 if any check fails."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.contracts import DomainError  # noqa: E402
from backend.store import Store  # noqa: E402
from runner.commands import DockerExecutor  # noqa: E402
from runner.tools import ToolBox  # noqa: E402
from runner.workspace import Workspace  # noqa: E402

PROXY_NAME, INTERNAL = "lifecycle-verify-proxy", "lifecycle-verify-internal"
PROXY_FILES = ("__init__.py", "registry_hosts.py", "registry_proxy.py")
results = []


def check(name, ok, evidence):
    results.append(dict(check=name, ok=bool(ok), evidence=evidence))


def docker(*args, timeout=120):
    done = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def start_proxy(python_image):
    docker("network", "create", "--internal", INTERNAL)
    mounts = [x for name in PROXY_FILES for x in ("--mount", f"type=bind,src={ROOT / 'runner' / name},dst=/proxy/runner/{name},readonly")]
    code, out, err = docker("run", "-d", "--name", PROXY_NAME, "--network", INTERNAL, "--user", "65534:65534", "--read-only",
                            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "128m", "--pids-limit", "64",
                            "--workdir", "/proxy", "--env", "PROXY_BIND=0.0.0.0", *mounts, python_image, "python", "-m", "runner.registry_proxy")
    if code:
        raise RuntimeError("proxy did not start: " + err)
    docker("network", "connect", "bridge", PROXY_NAME)  # the proxy alone has an outbound path; tool containers never do


def stop_proxy():
    docker("rm", "-f", PROXY_NAME)
    docker("network", "rm", INTERNAL)


def main(python_image, node_image, with_network):
    work = Path(tempfile.mkdtemp(prefix="lc-verify-"))
    workspace = work / "ws"
    workspace.mkdir()
    executor = DockerExecutor(dict(python=python_image, node=node_image))
    store = Store(work / "state.sqlite3")
    project = store.project(dict(title="isolation check", request="isolation check"))
    run_id = store.create_run(project["project_id"], dict(mode="live"), template_id="blank-v1")["run_id"]
    who = dict(role="builder", run_id=run_id, job_id="verify", attempt_id="verify", task_id="verify")
    deps = work / "deps"
    deps.mkdir()
    toolbox = ToolBox(lambda: who, store, Workspace(workspace), executor, deps_dir=deps, allowed_dependencies={"pip": {"six"}, "npm": {"is-number"}},
                      registry_network=INTERNAL if with_network else None,
                      registry_env={"HTTPS_PROXY": f"http://{PROXY_NAME}:3128"} if with_network else None)

    run = lambda argv, timeout=30: toolbox.run_command(argv, ".", timeout)  # noqa: E731
    out = run(["python", "-c", "print(6*7)"])
    check("python_runs_allowed_command", out["exit_code"] == 0 and out["stdout"].strip() == "42", out["stdout"].strip())
    out = run(["node", "-e", "console.log(6*7)"])
    check("node_runs_allowed_command", out["exit_code"] == 0 and out["stdout"].strip() == "42", out["stdout"].strip())
    try:
        run(["sh", "-c", "id"])
        check("policy_refuses_shell", False, "sh was accepted")
    except DomainError as error:
        check("policy_refuses_shell", error.code == "FORBIDDEN", error.message)
    out = run(["python", "-c", "import socket\ntry:\n socket.create_connection(('1.1.1.1', 53), timeout=3); print('connected')\n"
                               "except OSError as e:\n print('blocked', e.errno)"])
    check("network_none_blocks_egress", "blocked" in out["stdout"], out["stdout"].strip())
    out = run(["python", "-c", "import os\nst = open('/proc/self/status').read()\nprint(os.getuid(), st.split('CapEff:')[1].split()[0], "
                               "[l.split()[1] for l in st.splitlines() if l.startswith('NoNewPrivs')][0])"])
    uid, cap, nnp = out["stdout"].split()
    check("runs_as_nobody_without_capabilities", (uid, cap, nnp) == ("65534", "0000000000000000", "1"), dict(uid=uid, cap_eff=cap, no_new_privs=nnp))
    out = run(["python", "-c", "import errno\nres = {}\nfor p in ('/etc/lc-x', '/usr/lc-x', '/tmp/lc-x', '/work/lc-x'):\n try:\n  open(p, 'w').write('x'); res[p] = 'ok'\n"
                               " except OSError as e:\n  res[p] = errno.errorcode[e.errno]\nprint(res)"])
    root_ro = "EROFS" in out["stdout"] and "'/tmp/lc-x': 'ok'" in out["stdout"] and "'/work/lc-x': 'ok'" in out["stdout"]
    check("root_filesystem_read_only_work_and_tmp_writable", root_ro, out["stdout"].strip())
    out = run(["python", "-c", "x = bytearray(900 * 1024 * 1024)\nfor i in range(0, len(x), 4096): x[i] = 1\nprint('allocated')"], timeout=60)
    check("memory_limit_kills_overuse", out["exit_code"] not in (0, None), dict(exit_code=out["exit_code"]))
    out = run(["python", "-c", "import time; time.sleep(60)"], timeout=3)
    _, names, _ = docker("ps", "-a", "--filter", "name=lifecycle-", "--format", "{{.Names}}")
    leftover = [n for n in names.splitlines() if n != PROXY_NAME]
    check("timeout_kills_the_container", out["timed_out"] and not leftover, dict(timed_out=out["timed_out"], leftover=leftover))

    if with_network:
        try:
            start_proxy(python_image)
            out = run(["python", "-c", "import urllib.request\ntry:\n urllib.request.urlopen('https://pypi.org', timeout=5); print('reached')\n"
                                       "except Exception as e:\n print('blocked')"])
            check("plain_tool_container_has_no_route_out", "blocked" in out["stdout"], out["stdout"].strip())
            installed = toolbox.install_dependencies("pip", ["six"])
            check("pip_install_through_allowlist_proxy", installed["exit_code"] == 0 and (workspace / "requirements.lock").exists(),
                  dict(exit_code=installed["exit_code"], lock=(workspace / "requirements.lock").read_text().strip() if (workspace / "requirements.lock").exists() else None,
                       stderr=installed["stderr"][-300:]))
            out = run(["python", "-c", "import six; print(six.__version__)"])
            check("installed_python_package_importable_offline", out["exit_code"] == 0, out["stdout"].strip())
            installed = toolbox.install_dependencies("npm", ["is-number"])
            check("npm_install_through_allowlist_proxy", installed["exit_code"] == 0 and (workspace / "package-lock.json").exists(),
                  dict(exit_code=installed["exit_code"], stderr=installed["stderr"][-300:]))
            out = run(["node", "-e", "console.log(require('is-number')(5))"])
            check("installed_node_package_loadable_offline", out["exit_code"] == 0 and out["stdout"].strip() == "true", out["stdout"].strip())
            probe = ("import urllib.request as u\n"
                     f"opener = u.build_opener(u.ProxyHandler({{'https': 'http://{PROXY_NAME}:3128'}}))\n"
                     "try:\n"
                     " opener.open('https://example.com', timeout=8)\n"
                     " print('reached')\n"
                     "except Exception as e:\n"
                     " print('refused', type(e).__name__)\n")
            refused = subprocess.run(["docker", "run", "--rm", "--network", INTERNAL, python_image, "python", "-c", probe],
                                     capture_output=True, text=True, timeout=60)
            _, logs, _ = docker("logs", PROXY_NAME)
            check("proxy_refuses_a_non_registry_host", "refused" in refused.stdout and '"event": "refused"' in logs,
                  dict(client=refused.stdout.strip() or refused.stderr.strip()[-200:], proxy_log=[json.loads(l) for l in logs.splitlines()][-3:]))
        finally:
            stop_proxy()
    calls = store.tool_calls(run_id)
    check("every_call_is_in_the_ledger", len(calls) >= len(results) - 3 and any(not c["ok"] for c in calls),
          dict(entries=len(calls), denied=sum(not c["ok"] for c in calls)))
    print(json.dumps(dict(python_image=python_image, node_image=node_image, network_checks=with_network, results=results), ensure_ascii=False, indent=1))
    return all(r["ok"] for r in results)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(0 if len(args) == 2 and main(args[0], args[1], "--network" in sys.argv) else 1)
