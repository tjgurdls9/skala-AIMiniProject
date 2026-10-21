"""Model-driven builder loop: the model picks one tool call per step; the server executes, records and judges.

The model sees only its task, the approved criteria/checks for that task, a short ledger-derived history and the gate
state. Completion is accepted only when the ledger shows the required RED -> GREEN evidence."""
from collections import deque

from jsonschema import Draft202012Validator, ValidationError

from backend.contracts import DomainError, canonical, digest
from runner.commands import redact
from runner.context import BUDGET, bounded, mandatory
from runner.tdd_gate import can_finish, progress
from runner.tools import ToolBox

TOOLS = ("list_files", "read_file", "write_file", "delete_file", "move_file", "run_command", "run_tests", "install_dependencies")
ACTION_SCHEMA = dict(type="object", additionalProperties=False, required=["tool"], properties=dict(
    tool=dict(enum=[*TOOLS, "finish"]), args=dict(type="object"), summary=dict(type="string", maxLength=2000)))
STREAK_LIMIT = 3
WINDOW = 8   # recent steps without a recorded change in which the same action and outcome may appear STREAK_LIMIT times
CHANGING = frozenset({"write_file", "delete_file", "move_file", "run_command", "run_tests", "install_dependencies"})
HISTORY = 8
FILES_SHOWN = 60
CONTENT_CAP, OUTPUT_CAP = 3000, 800
INSTRUCTIONS = (
    "You are the builder. Each step return exactly one JSON action: {\"tool\": <name>, \"args\": {...}} or {\"tool\": \"finish\", \"summary\": \"...\"}. "
    "Tools: list_files(), read_file(path), write_file(path, content, expected_digest), delete_file(path, expected_digest), "
    "move_file(source, target, expected_digest), run_command(argv, cwd, timeout), run_tests(argv, cwd, timeout), "
    "install_dependencies(manager, packages). argv is a list, never a shell string. Pass expected_digest (from read_file/list_files) when "
    "changing an existing file. Write only inside write_scope. Follow gate.next: write failing tests first, run them, then implement until they pass. "
    "The server decides RED, GREEN and completion from recorded exit codes; stating that something passed has no effect. "
    "Environment facts: commands run in a container without network; the python image has only the standard library (no pytest) and the node image "
    "has the built-in test runner (node --test) unless dependencies were installed. "
    "Test files must also live inside write_scope and use conventional names (test_*.py, *_test.py, *.test.js, tests/). "
    "Implement only the acceptance criteria shown. Do not add dependencies outside the approved list.")


def describe_check(check):
    if check["kind"] == "http":
        what = "; ".join(f"{s['method']} {s['path']} -> {s['expect']['status']}" for s in check["steps"])
    elif check["kind"] == "command":
        what = " ".join(check["argv"]) + f" -> exit {check['expect']['exit']}"
    else:
        what = f"{check['path']} exists={check['expect']['exists']}"
    return dict(id=check["id"], kind=check["kind"], expect=what[:300])


def tail(text, cap):
    data = text.encode()
    return text if len(data) <= cap else "…" + data[-cap:].decode(errors="ignore")


def summarize_args(tool, args):
    if tool == "write_file":
        return dict(path=args.get("path"), bytes=len(str(args.get("content", "")).encode()))
    return {k: v for k, v in args.items() if k != "content"}


def history_entry(entry):
    return dict(tool=entry["tool"], args=summarize_args(entry["tool"], entry["args"]), ok=entry["ok"], error=entry["error_code"], exit_code=entry["exit_code"])


class BuilderLoop:
    def __init__(self, store):
        self.store = store

    def context(self, job, toolbox, last):
        packet, options = job["packet"], job["packet"]["options"]
        spec, kind, task_id = packet["latest_spec"], options.get("task_kind"), options["task_id"]
        entries = self.store.tool_calls(job["run_id"], task_id)
        ac_ids = set(options.get("acceptance_ids", []))
        gate = progress(entries, kind)
        files = [dict(path=f["path"], size=f["size"], digest=f["content_digest"]) for f in toolbox.workspace.list_files()]
        return entries, dict(
            role="builder", step="act", **mandatory(packet),
            task=dict(id=task_id, kind=kind, title=options.get("task_title"), write_scope=options.get("write_scope", [])),
            acceptance=[a for a in spec["acceptance"] if a["id"] in ac_ids] or spec["acceptance"],
            checks=[describe_check(c) for c in spec.get("verification", []) if ac_ids & set(c["ac_ids"])],
            dependencies=spec.get("dependencies", {}), files=files[:FILES_SHOWN], history=[history_entry(e) for e in entries[-HISTORY:]],
            last_observation=last, gate=dict(phase=gate.phase, next=gate.message), instructions=INSTRUCTIONS)

    @staticmethod
    def fit(call):
        """Drop the oldest history first, then file names, then shorten the last observation; mandatory parts are never cut."""
        while len(canonical(call).encode()) > BUDGET:
            if call["history"]:
                call["history"] = call["history"][1:]
            elif len(call["files"]) > 5:
                call["files"] = call["files"][: len(call["files"]) // 2]
            elif call["last_observation"] and call["last_observation"].get("content"):
                call["last_observation"] = dict(call["last_observation"], content=call["last_observation"]["content"][: len(call["last_observation"]["content"]) // 2])
            else:
                break
        return bounded(call)

    @staticmethod
    def unchanged(toolbox, args):
        try:
            return toolbox.workspace.read(args["path"])["content_digest"] == digest(args["content"])
        except (DomainError, KeyError, TypeError):
            return False

    def execute(self, toolbox, tool, args):
        method = getattr(toolbox, tool)
        same = tool == "write_file" and isinstance(args, dict) and self.unchanged(toolbox, args)
        try:
            result = method(**args)
        except TypeError as error:
            return dict(ok=False, error="인자 형식 오류: " + str(error)[:200]), "bad-args"
        except DomainError as error:
            if getattr(error, "needs_input", False):
                raise
            return dict(ok=False, error=f"{error.code}: {error.message}"), f"{error.code}:{error.message}"
        observation = dict(ok=True)
        if tool == "read_file":
            observation.update(path=result["path"], content=tail(result["content"], CONTENT_CAP), digest=result["content_digest"])
        elif tool in ("run_command", "run_tests", "install_dependencies"):
            observation.update(exit_code=result["exit_code"], timed_out=result["timed_out"], stdout=tail(result["stdout"], OUTPUT_CAP),
                               stderr=tail(result["stderr"], OUTPUT_CAP))
        else:
            observation.update({k: v for k, v in result.items() if k != "content"})
            if same:
                observation.update(unchanged=True, note="파일 내용이 이미 같아 변경이 없습니다.")
        return observation, digest(result)

    def record_format_error(self, job, error):
        options = job["packet"]["options"]
        self.store.record_tool_call(dict(
            run_id=job["run_id"], job_id=job.get("id"), attempt_id=job.get("attempt_id"), task_id=options["task_id"], role="builder",
            tool="model_output_error", args=dict(error=str(error)[:200], raw_head=redact(str(getattr(error, "doc", ""))[:300])),
            ok=False, error_code="MODEL_FORMAT"))

    async def run(self, job, worker, toolbox):
        options, last, recent, steps = job["packet"]["options"], None, deque(maxlen=WINDOW), 0
        while True:
            entries, call = self.context(job, toolbox, last)
            steps += 1
            action = None
            try:
                action = await worker.infer(job, self.fit(call), ACTION_SCHEMA)
                Draft202012Validator(ACTION_SCHEMA).validate(action)
            except ValueError as error:   # the answer was not decodable JSON; keep the raw head as evidence, never crash the run
                self.record_format_error(job, error)
                last, signature = dict(ok=False, error="출력이 올바른 JSON이 아닙니다: " + str(error)[:120]), "decode:" + str(error)[:80]
            except ValidationError as error:
                last, signature = dict(ok=False, error="형식 오류: " + error.message[:200]), "format:" + error.message[:200]
            else:
                if action["tool"] == "finish":
                    done, reason = can_finish(entries, options.get("task_kind"))
                    if done:
                        return dict(summary=action.get("summary", ""), steps=steps)
                    last, signature = dict(ok=False, error="아직 끝낼 수 없습니다: " + reason), "finish:" + reason
                else:
                    last, signature = self.execute(toolbox, action["tool"], action.get("args", {}))
                    signature = digest([action["tool"], action.get("args", {}), signature])
            if last.get("ok") and isinstance(action, dict) and action.get("tool") in CHANGING and not last.get("unchanged"):
                recent.clear()                  # a recorded change is progress; earlier repetition no longer counts
            recent.append(signature)
            if recent.count(signature) >= STREAK_LIMIT:
                raise DomainError("INVALID_COMMAND", f"같은 동작과 결과가 {STREAK_LIMIT}번 반복돼 사람의 입력이 필요합니다: "
                                  f"{(last or {}).get('error', '진전 없음')[:200]}", 422)
