"""RED -> GREEN as the server judges it, from the tool ledger's real exit codes (never from model statements)."""
from dataclasses import dataclass
from pathlib import PurePosixPath

TDD_KINDS = frozenset({"backend", "frontend", "ai_data"})
TEST_PATTERNS = ("tests/**", "**/tests/**", "test_*.py", "**/test_*.py", "*_test.py", "**/*_test.py", "*.test.*", "**/*.test.*",
                 "*.spec.*", "**/*.spec.*", "**/__tests__/**")
MUTATIONS = frozenset({"write_file", "delete_file", "move_file"})


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


def progress(entries, kind):
    """Phase of the current task: `red` (write failing tests first), `impl` (tests fail or code changed since, make them pass), `done`."""
    if kind not in TDD_KINDS:
        return Progress("free", "")
    phase, tests_written, implemented = "red", False, False
    for entry in entries:
        if not entry["ok"]:
            continue
        if entry["tool"] in MUTATIONS:
            if any(is_test_path(p) for p in mutated_paths(entry)):
                phase, tests_written, implemented = "red", True, False
            elif phase != "red":
                phase, implemented = "impl", True
        elif entry["tool"] == "run_tests":
            code = entry["exit_code"]
            if phase == "red" and tests_written and code not in (0, None):
                phase, implemented = "impl", False
            elif phase == "impl" and implemented and code == 0:
                phase = "done"
    message = dict(red="먼저 실패하는 테스트를 작성하고 run_tests로 실패(종료 코드 0이 아님)를 확인해야 구현 파일을 쓸 수 있습니다.",
                   impl="테스트가 실패하는 상태입니다. 구현을 작성한 뒤 run_tests가 통과(종료 코드 0)해야 합니다.",
                   done="테스트가 통과했습니다.")[phase]
    return Progress(phase, message)


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
        passed = any(e["ok"] and e["tool"] == "run_tests" and e["exit_code"] == 0 for e in entries[last_change + 1:])
        return (passed, "" if passed else "마지막 변경 뒤에 run_tests가 통과(종료 코드 0)해야 합니다.")
    return True, ""
