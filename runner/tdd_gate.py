"""RED -> GREEN as the server judges it, from the tool ledger's real exit codes (never from model statements)."""
from dataclasses import dataclass
from pathlib import PurePosixPath
import re

TDD_KINDS = frozenset({"backend", "frontend", "ai_data"})
TEST_PATTERNS = ("tests/**", "**/tests/**", "test_*.py", "**/test_*.py", "*_test.py", "**/*_test.py", "*.test.*", "**/*.test.*",
                 "*.spec.*", "**/*.spec.*", "**/__tests__/**")
MUTATIONS = frozenset({"write_file", "delete_file", "move_file"})
NO_TESTS_RAN = "NO_TESTS_RAN"   # ledger error_code of a run_tests that exited 0 without a readable count of executed tests
SUMMARIES = (re.compile(r"^Ran (\d+) tests?\b", re.M), re.compile(r"^[#\u2139] pass (\d+)$", re.M), re.compile(r"\b(\d+) passed\b"),
             re.compile(r"\b(\d+) passing\b"), re.compile(r"\bno tests ran\b(?!.*\bpassed\b)", re.I))


def count_tests(stdout, stderr):
    """How many tests a runner says it executed (unittest, pytest, node:test, jest, mocha), or None if no summary is recognised."""
    text = stdout + "\n" + stderr
    for pattern in SUMMARIES:
        found = pattern.search(text)
        if found:
            return int(found.group(1)) if found.groups() else 0
    return None


@dataclass(frozen=True)
class Progress:
    phase: str      # red | impl | done | free
    message: str


def is_test_path(path):
    return any(PurePosixPath(path).full_match(pattern) for pattern in TEST_PATTERNS)


def mutated_paths(entry):
    args = entry["args"]
    return [args["path"]] if entry["tool"] != "move_file" else [args["source"], args["target"]]


def _ok_mutations(entries):
    return [e for e in entries if e["ok"] and e["tool"] in MUTATIONS]


def state_message(phase, tests_written, implemented, last_run):
    """Ledger facts plus the gate rule that applies; never what to test or how to implement."""
    if phase == "done":
        return "RED와 GREEN 기록 확인됨. finish 가능."
    if last_run == "no_tests":
        return "run_tests가 통과했지만 실행된 테스트가 확인되지 않습니다(실행된 테스트 수 0 또는 요약 없음). 테스트가 실제로 실행돼 통과해야 판정됩니다."
    if phase == "red":
        if not tests_written:
            return "테스트 파일 기록 없음. RED 판정에는 실패하는 테스트 파일 작성과 실패한 run_tests 기록이 필요합니다."
        if last_run == "none":
            return "테스트 파일 있음, run_tests 기록 없음. RED 판정에는 실패(종료 코드 ≠ 0)한 run_tests가 필요합니다."
        if last_run == 0:
            return "run_tests가 바로 통과(종료 코드 0). RED 판정에는 실패(종료 코드 ≠ 0)한 run_tests가 필요합니다."
        return "run_tests가 시간 초과(종료 코드 없음). RED 판정에는 실패(종료 코드 ≠ 0)한 run_tests가 필요합니다."
    if not implemented:
        if last_run == 0:
            return "테스트 경로 밖 구현 파일 기록 없이 run_tests가 통과. GREEN 판정에는 테스트 경로 밖에 구현 파일을 작성한 뒤 통과한 run_tests가 필요합니다."
        return "RED 확인됨, 테스트 경로 밖 구현 파일 기록 없음. GREEN 판정에는 구현 파일을 작성한 뒤 통과(종료 코드 0)한 run_tests가 필요합니다."
    if last_run == "none":
        return "구현 파일 있음, 이후 run_tests 기록 없음. GREEN 판정에는 통과(종료 코드 0)한 run_tests가 필요합니다."
    return "마지막 run_tests가 아직 실패. GREEN 판정에는 통과(종료 코드 0)한 run_tests가 필요합니다."


def progress(entries, kind):
    """Phase of the current task: `red` (write failing tests first), `impl` (RED seen; needs an implementation file and a passing run
    after the last change), `done`. Editing tests after RED is allowed: forcing a second failure blocked legitimate test fixes in real runs."""
    if kind not in TDD_KINDS:
        return Progress("free", "")
    phase, tests_written, implemented, last_run = "red", False, False, "none"   # last_run: exit code since the last change, or "none"
    for entry in entries:
        if not entry["ok"]:
            continue
        if entry["tool"] in MUTATIONS:
            last_run = "none"
            tests_only = all(is_test_path(p) for p in mutated_paths(entry))
            if phase == "red":
                tests_written = tests_written or tests_only
            else:   # a later change, even a test fix, only reopens the final pass; weakened tests are the independent validator's concern
                phase = "impl"
                implemented = implemented or not tests_only
        elif entry["tool"] == "run_tests":
            if entry.get("error_code") == NO_TESTS_RAN:   # a pass with nothing executed proves neither RED nor GREEN
                last_run = "no_tests"
                continue
            code = last_run = entry["exit_code"]
            if phase == "red" and tests_written and code not in (0, None):
                phase, implemented = "impl", False
            elif phase == "impl" and implemented and code == 0:
                phase = "done"
    return Progress(phase, state_message(phase, tests_written, implemented, last_run))


def can_finish(entries, kind):
    """(True, '') when the ledger shows the task earned completion, else (False, reason)."""
    changes = [i for i, e in enumerate(entries) if e["ok"] and (e["tool"] in MUTATIONS or e["tool"] == "install_dependencies")]
    if not changes:
        return False, "아무 변경 없이 작업을 끝낼 수 없습니다. 파일을 작성하세요."
    if kind in TDD_KINDS:
        state = progress(entries, kind)
        return (state.phase == "done", "" if state.phase == "done" else state.message + " 테스트 단계를 마친 뒤 끝낼 수 있습니다.")
    if kind == "integration":
        last_change = changes[-1]
        passed = any(e["ok"] and e["tool"] == "run_tests" and e["exit_code"] == 0 and
                     e.get("error_code") != NO_TESTS_RAN for e in entries[last_change + 1:])
        return (passed, "" if passed else "마지막 변경 뒤에 run_tests가 통과(종료 코드 0)해야 합니다.")
    return True, ""
