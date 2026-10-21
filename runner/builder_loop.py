"""Model-driven builder loop: the model picks one tool call per step; the server executes, records and judges.

The model sees only its task, the approved criteria/checks for that task, a short ledger-derived history and the gate
state. Completion is accepted only when the ledger shows the required RED -> GREEN evidence."""
from collections import deque

from jsonschema import Draft202012Validator, ValidationError

from backend.contracts import DomainError, canonical, digest
from runner.commands import redact
from runner.context import BUDGET, bounded, mandatory
from runner.tdd_gate import can_finish, progress

TOOLS = ("list_files", "read_file", "write_file", "delete_file", "move_file", "run_command", "run_tests", "install_dependencies")
TEXT = dict(type="string")


def obj(properties, required):
    return dict(type="object", additionalProperties=False, properties=properties, required=required)


COMMAND = dict(argv=dict(type="array", minItems=1, maxItems=32, items=TEXT), cwd=TEXT, timeout=dict(type="integer"))
TOOL_ARGS = dict(
    list_files=obj({}, []),
    read_file=obj(dict(path=TEXT), ["path"]),
    write_file=obj(dict(path=TEXT, content=TEXT, expected_digest=dict(type=["string", "null"])), ["path", "content"]),
    delete_file=obj(dict(path=TEXT, expected_digest=TEXT), ["path", "expected_digest"]),
    move_file=obj(dict(source=TEXT, target=TEXT, expected_digest=TEXT), ["source", "target", "expected_digest"]),
    run_command=obj(COMMAND, ["argv"]),
    run_tests=obj(COMMAND, ["argv"]),
    install_dependencies=obj(dict(manager=dict(enum=["pip", "npm"]), packages=dict(type="array", minItems=1, maxItems=20, items=TEXT)),
                             ["manager", "packages"]))


def action_schema(allow_finish):
    """One variant per tool with its own arguments; `finish` exists only while the ledger would accept it."""
    variants = [dict(type="object", additionalProperties=False, required=["tool", "args"], properties=dict(tool=dict(const=name), args=args))
                for name, args in TOOL_ARGS.items()]
    if allow_finish:
        variants.append(dict(type="object", additionalProperties=False, required=["tool", "summary"],
                             properties=dict(tool=dict(const="finish"), summary=dict(type="string", maxLength=2000))))
    return dict(anyOf=variants)


ACTION_SCHEMA = action_schema(True)
STREAK_LIMIT = 3
WINDOW = 8   # recent steps without a recorded change in which the same action and outcome may appear STREAK_LIMIT times
CHANGING = frozenset({"write_file", "delete_file", "move_file", "run_command", "run_tests", "install_dependencies"})
HISTORY = 8
FILES_SHOWN = 60
CONTENT_CAP, OUTPUT_CAP = 3000, 800
INSTRUCTIONS = (
    "You are the builder. Each step return exactly one JSON action. Shapes (placeholders only): "
    '{"tool":"list_files","args":{}} ; {"tool":"read_file","args":{"path":"<path>"}} ; '
    '{"tool":"write_file","args":{"path":"<path>","content":"<text>"}} ; {"tool":"run_tests","args":{"argv":["<runner>","<arg>"]}} ; '
    '{"tool":"finish","summary":"<text>"} (finish is offered only when the server allows it). '
    "run_tests accepts only python -m unittest|pytest ..., node --test ..., npm test. Other tools: delete_file(path, expected_digest), move_file(source, target, expected_digest), run_command(argv, cwd, timeout), "
    "install_dependencies(manager, packages). argv is a list, never a shell string. Pass expected_digest (from read_file/list_files) when "
    "changing an existing file. Write only inside write_scope; test files must be inside it too, with conventional names "
    "(test_*.py, *_test.py, *.test.js, tests/). Environment: commands have no network; the python image has only the standard library "
    "(no pytest); the node image has the built-in test runner (node --test). The finished app is declared in lifecycle.app.json {runtime: python|node, start: argv list, port: 8080, health: /path}, listens on 0.0.0.0:8080 and keeps data under /data. The server decides RED, GREEN and completion from recorded "
    "exit codes; stating that something passed has no effect. Follow gate.next. Implement only the acceptance criteria shown; "
    "do not install packages outside the approved list.")


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


SKIPPED_LINE = ("-", "=", "Ran ", "FAILED", "OK", "#", "^", "~")
ERROR_WORDS = ("error", "exception", "assert")
MUTATING = frozenset({"write_file", "delete_file", "move_file", "install_dependencies"})
SUMMARY_CHARS = 200


def failure_summary(stdout, stderr):
    """The last line of the real output that names an error (stderr first, then stdout); None when no line does."""
    for text in (stderr, stdout):
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line and not line.startswith(SKIPPED_LINE) and any(word in line.lower() for word in ERROR_WORDS):
                return line[:SUMMARY_CHARS]
    return None


def repeated_without_change(entries):
    """True when the newest run produced exactly the previous same command's output and no file was changed in between."""
    current = entries[-1]
    for index in range(len(entries) - 2, -1, -1):
        entry = entries[index]
        if entry["ok"] and entry["tool"] in MUTATING:
            return False
        if entry["ok"] and entry["tool"] == current["tool"] and entry["args"].get("argv") == current["args"].get("argv"):
            return entry["stdout_digest"] == current["stdout_digest"] and entry["stderr_digest"] == current["stderr_digest"]
    return False


def history_entry(entry):
    return dict(tool=entry["tool"], args=summarize_args(entry["tool"], entry["args"]), ok=entry["ok"], error=entry["error_code"], exit_code=entry["exit_code"])


class Refused(Exception):
    """The model asked to finish while the ledger does not allow it."""


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
            if getattr(error, "needs_input", False) or error.code in ("RUNTIME_UNAVAILABLE", "TEMPORARILY_UNAVAILABLE"):
                raise   # the user, or a resource wait, decides; the model is not asked to retry around a broken container
            return dict(ok=False, error=f"{error.code}: {error.message}"), f"{error.code}:{error.message}"
        observation = dict(ok=True)
        if tool == "read_file":
            observation.update(path=result["path"], content=tail(result["content"], CONTENT_CAP), digest=result["content_digest"])
        elif tool in ("run_command", "run_tests", "install_dependencies"):
            observation.update(exit_code=result["exit_code"], timed_out=result["timed_out"], stdout=tail(result["stdout"], OUTPUT_CAP),
                               stderr=tail(result["stderr"], OUTPUT_CAP))
            if result["exit_code"] not in (0, None):
                summary = failure_summary(result["stdout"], result["stderr"])
                if summary:
                    observation["failure_summary"] = summary
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
            allowed, reason = can_finish(entries, options.get("task_kind"))
            schema = action_schema(allowed)
            try:
                action = await worker.infer(job, self.fit(call), schema)
                if isinstance(action, dict) and action.get("tool") == "finish" and not allowed:
                    raise Refused(reason)
                Draft202012Validator(schema).validate(action)
            except Refused as refused:
                last, signature = dict(ok=False, error="아직 끝낼 수 없습니다: " + str(refused)), "finish:" + str(refused)
            except ValueError as error:   # the answer was not decodable JSON; keep the raw head as evidence, never crash the run
                self.record_format_error(job, error)
                last, signature = dict(ok=False, error="출력이 올바른 JSON이 아닙니다: " + str(error)[:120]), "decode:" + str(error)[:80]
            except ValidationError as error:
                last, signature = dict(ok=False, error="형식 오류: " + error.message[:200]), "format:" + error.message[:200]
            else:
                if action["tool"] == "finish":
                    return dict(summary=action.get("summary", ""), steps=steps)
                last, signature = self.execute(toolbox, action["tool"], action.get("args", {}))
                if last.get("ok") and action["tool"] in ("run_tests", "run_command"):
                    ledger = self.store.tool_calls(job["run_id"], options["task_id"])
                    if ledger and repeated_without_change(ledger):
                        last["repeated_without_change"] = "파일 변경 없이 같은 명령이 같은 결과를 냈습니다."
                signature = digest([action["tool"], action.get("args", {}), signature])
            if last.get("ok") and isinstance(action, dict) and action.get("tool") in CHANGING and not last.get("unchanged"):
                recent.clear()                  # a recorded change is progress; earlier repetition no longer counts
            recent.append(signature)
            if recent.count(signature) >= STREAK_LIMIT:
                raise DomainError("INVALID_COMMAND", f"같은 동작과 결과가 {STREAK_LIMIT}번 반복돼 사람의 입력이 필요합니다: "
                                  f"{(last or {}).get('error', '진전 없음')[:200]}", 422)
