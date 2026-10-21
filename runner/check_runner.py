"""Mechanical evaluation of declarative checks and the acceptance verdicts derived from them.

Verdicts come from observed results compared with the approved expectations. No model text is read here."""
from dataclasses import dataclass

from runner.commands import TOOL_POLICY


@dataclass(frozen=True)
class CheckOutcome:
    id: str
    status: str            # passed | failed | error
    detail: str
    evidence: dict


def subset(expected, actual):
    """Every expected key/element appears in actual; list elements may match in any position; bool never equals int."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and all(any(subset(e, a) for a in actual) for e in expected)
    return expected == actual


def _http(spec, env):
    observed = []
    for step in spec["steps"]:
        status, body = env.http(step["method"], step["path"], step.get("json"))
        observed.append(dict(method=step["method"], path=step["path"], status=status))
        expect = step["expect"]
        if status != expect["status"]:
            return CheckOutcome(spec["id"], "failed", f"{step['method']} {step['path']}: 상태 {status} (기대 {expect['status']})", dict(steps=observed))
        if "json_subset" in expect and not subset(expect["json_subset"], body):
            return CheckOutcome(spec["id"], "failed", f"{step['method']} {step['path']}: 응답이 기대 일부와 다릅니다.", dict(steps=observed))
    return CheckOutcome(spec["id"], "passed", "", dict(steps=observed))


def _command(spec, env):
    result = env.run(spec["argv"], spec.get("cwd", "."), TOOL_POLICY["timeout_default"])
    evidence = dict(exit_code=result.exit_code, timed_out=result.timed_out)
    expect = spec["expect"]
    if result.timed_out:
        return CheckOutcome(spec["id"], "failed", "제한 시간을 넘었습니다.", evidence)
    if result.exit_code != expect["exit"]:
        return CheckOutcome(spec["id"], "failed", f"종료 코드 {result.exit_code} (기대 {expect['exit']})", evidence)
    missing = [text for text in expect.get("stdout_contains", []) if text not in result.stdout]
    if missing:
        return CheckOutcome(spec["id"], "failed", "출력에 기대 문구가 없습니다: " + ", ".join(missing), evidence)
    return CheckOutcome(spec["id"], "passed", "", evidence)


def _file(spec, env):
    content = env.read_text(spec["path"])
    expect = spec["expect"]
    evidence = dict(exists=content is not None)
    if (content is not None) != expect["exists"]:
        return CheckOutcome(spec["id"], "failed", "파일 존재 여부가 기대와 다릅니다.", evidence)
    missing = [text for text in expect.get("contains", []) if content is None or text not in content]
    if missing:
        return CheckOutcome(spec["id"], "failed", "파일에 기대 문구가 없습니다: " + ", ".join(missing), evidence)
    return CheckOutcome(spec["id"], "passed", "", evidence)


EVALUATORS = dict(http=_http, command=_command, file=_file)


def evaluate(spec, env):
    """Run one check against an environment (http / run / read_text). Failures of the tool itself are `error`, not `failed`."""
    try:
        return EVALUATORS[spec["kind"]](spec, env)
    except Exception as error:  # noqa: BLE001 - any tool breakage must surface as an error outcome, never as a pass
        return CheckOutcome(spec["id"], "error", type(error).__name__, {})


def acceptance_verdicts(acceptance, verification, manual_acceptance, outcomes):
    """Per AC: met only if every linked check passed; failed checks win, then tool errors, then missing runs."""
    by_id = {o.id: o for o in outcomes}
    manual = {m["ac_id"] for m in manual_acceptance}
    verdicts = []
    for ac in acceptance:
        linked = [spec["id"] for spec in verification if ac["id"] in spec["ac_ids"]]
        results = [by_id.get(name) for name in linked]
        if not linked:
            status, reason = "not_run", "manual" if ac["id"] in manual else "no_check"
        elif any(r is not None and r.status == "failed" for r in results):
            status, reason = "unmet", "check_failed"
        elif any(r is not None and r.status == "error" for r in results):
            status, reason = "failed", "tool_error"
        elif any(r is None for r in results):
            status, reason = "not_run", "not_executed"
        else:
            status, reason = "met", "checks_passed"
        verdicts.append(dict(id=ac["id"], status=status, reason=reason, check_ids=linked))
    return verdicts
