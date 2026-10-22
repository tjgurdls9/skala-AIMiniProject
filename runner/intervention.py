"""Workspace changes that no ledgered tool call explains. A developer's edit must never be counted as the model's work.

Commands run with the workspace mounted read-only, so the ledger is the only way a task can change it."""

MUTATING = {"write_file": ("path",), "delete_file": ("path",), "move_file": ("source", "target")}


def ledgered_paths(calls):
    """Paths a successful file-mutation tool call touched."""
    return {call["args"][key] for call in calls if call["ok"] for key in MUTATING.get(call["tool"], ())}


def unledgered(changed, calls):
    """Changed paths with no ledger entry."""
    return sorted(set(changed) - ledgered_paths(calls))
