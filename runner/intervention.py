"""Workspace changes that no ledgered tool call explains. A developer's edit must never be counted as the model's work.

Commands run with the workspace mounted read-only, so the ledger is the only way a task can change it."""

from runner.tools import LOCK_FILES

MUTATING = {"write_file": ("path",), "delete_file": ("path",), "move_file": ("source", "target")}


def ledgered_paths(calls):
    """Paths a successful file-mutation tool call touched, plus the lock file a successful install writes itself."""
    paths = {call["args"][key] for call in calls if call["ok"] for key in MUTATING.get(call["tool"], ())}
    return paths | {LOCK_FILES[call["args"]["manager"]] for call in calls
                    if call["ok"] and call["tool"] == "install_dependencies" and call["args"].get("manager") in LOCK_FILES}


def unledgered(changed, calls):
    """Changed paths with no ledger entry."""
    return sorted(set(changed) - ledgered_paths(calls))
