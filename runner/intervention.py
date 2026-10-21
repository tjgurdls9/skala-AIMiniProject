"""Workspace changes that no ledgered tool call explains. A developer's edit must never be counted as the model's work."""

MUTATING = {"write_file": ("path",), "delete_file": ("path",), "move_file": ("source", "target")}
COMMANDS = frozenset({"run_command", "run_tests", "install_dependencies"})


def ledgered_paths(calls):
    """Paths a successful file-mutation tool call touched."""
    return {call["args"][key] for call in calls if call["ok"] for key in MUTATING.get(call["tool"], ())}


def unledgered(changed, calls):
    """Changed paths with no ledger entry. ponytail: a task that ran commands may legitimately create files and they cannot be
    attributed, so only edits between tasks are caught there; per-file attribution of command output if that proves too loose."""
    if any(call["tool"] in COMMANDS for call in calls):
        return []
    return sorted(set(changed) - ledgered_paths(calls))
