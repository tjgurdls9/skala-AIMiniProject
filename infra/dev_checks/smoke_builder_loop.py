"""Development check, not acceptance: does the local model follow the builder-loop action format?

Runs ONE generic micro task through BuilderLoop with the real Ollama model and real Docker containers, in a temporary
workspace and database. No prompt hint or answer is added. Limits: 40 model calls or 20 minutes, whichever comes first.
Usage: backend/.venv/bin/python infra/dev_checks/smoke_builder_loop.py <python@sha256:...> <node@sha256:...> <model>"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator  # noqa: E402

from backend.contracts import DomainError  # noqa: E402
from backend.store import Store  # noqa: E402
from runner.builder_loop import ACTION_SCHEMA, BuilderLoop  # noqa: E402
from runner.commands import DockerExecutor  # noqa: E402
from runner.model import Ollama  # noqa: E402
from runner.tdd_gate import progress  # noqa: E402
from runner.tools import ToolBox  # noqa: E402
from runner.worker import POLICY  # noqa: E402
from runner.workspace import Workspace  # noqa: E402

MAX_CALLS, MAX_SECONDS = 40, 20 * 60


class Stop(Exception):
    pass


class Metered:
    """Counts and times every model call, validates the raw action, enforces the limits, keeps the raw answers."""
    def __init__(self, model):
        self.model, self.started, self.steps = model, time.monotonic(), []

    async def infer(self, job, call, schema):
        if len(self.steps) >= MAX_CALLS or time.monotonic() - self.started > MAX_SECONDS:
            raise Stop("limit")
        begun = time.monotonic()
        previous = call["last_observation"]
        try:
            action = await self.model.generate(call, schema)
        except Exception as error:  # noqa: BLE001 - a model failure is a result to record
            self.steps.append(dict(error=type(error).__name__, seconds=round(time.monotonic() - begun, 1), observation_of_previous=previous))
            raise
        valid = not list(Draft202012Validator(ACTION_SCHEMA).iter_errors(action))
        self.steps.append(dict(action=action, schema_valid=valid, seconds=round(time.monotonic() - begun, 1), observation_of_previous=previous,
                               packet_bytes=len(json.dumps(call, ensure_ascii=False).encode()), gate=call["gate"]["phase"]))
        return action


async def main(python_image, node_image, model_name):
    work = Path(tempfile.mkdtemp(prefix="lc-smoke-"))
    (work / "ws").mkdir()
    store = Store(work / "state.sqlite3")
    project = store.project(dict(title="smoke", request="smoke"))
    run_id = store.create_run(project["project_id"], dict(mode="live"), template_id="blank-v1")["run_id"]
    spec = dict(spec_version_id="0" * 32, goal="두 정수를 더하는 함수 add(a, b)를 제공한다", features=["add(a, b)는 두 정수의 합을 반환한다"], non_goals=[],
                constraints=["무료 도구만 사용한다"], acceptance=[dict(id="AC1", title="덧셈", description="add(2, 3)이 5를 반환한다")],
                verification=[], dependencies=dict(pip=[], npm=[]))
    job = dict(run_id=run_id, id="smoke", packet=dict(latest_spec=spec, prior_draft=None, mandatory_policy=POLICY, unresolved_failures=[],
               options=dict(task_id="t1", task_kind="backend", task_title="덧셈 함수", acceptance_ids=["AC1"], write_scope=["**"])))
    who = dict(role="builder", run_id=run_id, job_id="smoke", attempt_id="smoke", task_id="t1", task_kind="backend")
    toolbox = ToolBox(lambda: who, store, Workspace(work / "ws"), DockerExecutor(dict(python=python_image, node=node_image)), deps_dir=work / "deps")
    metered, outcome, began = Metered(Ollama(model_name)), "unknown", time.monotonic()
    try:
        result = await BuilderLoop(store).run(job, metered, toolbox)
        outcome = "finished: " + result["summary"][:200]
    except Stop:
        outcome = "stopped by the call/time limit"
    except DomainError as error:
        outcome = f"stopped for the user: {error.code} {error.message[:300]}"
    except Exception as error:  # noqa: BLE001
        outcome = f"model/runtime failure: {type(error).__name__} {str(error)[:200]}"
    entries = store.tool_calls(run_id, "t1")
    phases = [progress(entries[: i + 1], "backend").phase for i in range(len(entries))]
    observations = [s["observation_of_previous"] for s in metered.steps[1:] if s.get("observation_of_previous")]
    summary = dict(model=model_name, outcome=outcome, seconds=round(time.monotonic() - began, 1), model_calls=len(metered.steps),
                   schema_valid=sum(1 for s in metered.steps if s.get("schema_valid")), model_errors=sum(1 for s in metered.steps if "error" in s),
                   observations_ok=sum(1 for o in observations if o.get("ok")), observations_error=sum(1 for o in observations if not o.get("ok")),
                   tool_calls=len(entries), tool_denied=sum(1 for e in entries if not e["ok"]),
                   reached_red="impl" in phases or "done" in phases, reached_green="done" in phases,
                   files=sorted(p.relative_to(work / "ws").as_posix() for p in (work / "ws").rglob("*") if p.is_file()),
                   error_samples=[o.get("error") for o in observations if not o.get("ok")][:8],
                   steps=[{k: v for k, v in s.items() if k != "observation_of_previous"} for s in metered.steps],
                   ledger=[dict(seq=e["seq"], tool=e["tool"], args={k: v for k, v in e["args"].items() if k != "content_digest"}, ok=e["ok"],
                                error=e["error_code"], exit_code=e["exit_code"], stderr=(e["stderr_excerpt"] or "")[:200], stdout=(e["stdout_excerpt"] or "")[:200])
                           for e in entries])
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:4]))
