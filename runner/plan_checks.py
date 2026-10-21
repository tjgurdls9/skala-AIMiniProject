"""Supervisor-side validation of a model-proposed work plan and verification specs; pure functions, no model."""
from backend.contracts import DomainError
from runner.commands import validate_command
from runner.workspace import relative_parts

AREAS = ("infra", "backend", "frontend", "ai_data")
WILDCARDS = "*?["


def literal_prefix(pattern):
    cut = min((pattern.index(c) for c in WILDCARDS if c in pattern), default=len(pattern))
    return pattern[:cut]


def scopes_overlap(first, second):
    """Conservative: two glob scopes overlap when one literal prefix starts with the other."""
    a, b = literal_prefix(first), literal_prefix(second)
    return a.startswith(b) or b.startswith(a)


def _reachable(items):
    """For each item id, the set of ids it depends on, directly or transitively (cycle-safe)."""
    graph = {i["id"]: [d for d in i["depends_on"] if d in {x["id"] for x in items}] for i in items}
    closure = {}
    for start in graph:
        seen, stack = set(), list(graph[start])
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(graph[node])
        closure[start] = seen
    return closure


def check_work_plan(work_plan, omitted_areas, acceptance):
    """Return human-readable errors; an empty list means the plan may be shown for approval."""
    if not work_plan:
        return ["작업 분해가 비어 있습니다."]
    errors, ids = [], [i["id"] for i in work_plan]
    errors += [f"작업 ID가 중복됐습니다: {name}" for name in sorted({n for n in ids if ids.count(n) > 1})]
    known, ac_ids = set(ids), [a["id"] for a in acceptance]
    for entry in work_plan:
        errors += [f"{entry['id']}: 없는 작업에 의존합니다: {d}" for d in entry["depends_on"] if d not in known]
        errors += [f"{entry['id']}: 알 수 없는 AC {a}" for a in entry["acceptance_ids"] if a not in ac_ids]
    closure = _reachable(work_plan)
    errors += [f"순환 의존이 있습니다: {name}" for name in sorted(n for n in closure if n in closure[n])]
    covered = {a for entry in work_plan for a in entry["acceptance_ids"]}
    errors += [f"{ac} AC가 작업에 연결되지 않았습니다." for ac in ac_ids if ac not in covered]
    for index, first in enumerate(work_plan):
        for second in work_plan[index + 1:]:
            ordered = second["id"] in closure[first["id"]] or first["id"] in closure[second["id"]]
            if not ordered and any(scopes_overlap(a, b) for a in first["write_scope"] for b in second["write_scope"]):
                errors.append(f"{first['id']}와 {second['id']}의 쓰기 범위가 겹치고 서로 순서가 없습니다.")
    planned, omitted = {i["kind"] for i in work_plan}, {o["kind"] for o in omitted_areas}
    for area in AREAS:
        if area not in planned and area not in omitted:
            errors.append(f"{area} 영역이 작업에도 생략 이유에도 없습니다.")
        if area in planned and area in omitted:
            errors.append(f"{area} 영역이 작업에 있으면서 생략으로도 표시돼 이유가 모순됩니다.")
    return errors


def check_verification(verification, manual_acceptance, acceptance):
    errors, ac_ids = [], {a["id"] for a in acceptance}
    names = [v["id"] for v in verification]
    errors += [f"점검 ID가 중복됐습니다: {n}" for n in sorted({n for n in names if names.count(n) > 1})]
    for spec in verification:
        errors += [f"{spec['id']}: 알 수 없는 AC {a}" for a in spec["ac_ids"] if a not in ac_ids]
        try:
            if spec["kind"] == "command":
                validate_command(spec["argv"], spec.get("cwd", "."))
            elif spec["kind"] == "file":
                relative_parts(spec["path"])
        except DomainError as error:
            errors.append(f"{spec['id']}: {error.message}")
    marked = [m["ac_id"] for m in manual_acceptance]
    errors += [f"사람 확인 표시에 알 수 없는 AC {a}" for a in marked if a not in ac_ids]
    errors += [f"사람 확인 표시가 중복됐습니다: {a}" for a in sorted({a for a in marked if marked.count(a) > 1})]
    return errors


def unverified_acceptance(acceptance, verification, manual_acceptance):
    """AC ids that no check covers and nobody explicitly marked for human confirmation."""
    covered = {a for spec in verification for a in spec["ac_ids"]} | {m["ac_id"] for m in manual_acceptance}
    return [a["id"] for a in acceptance if a["id"] not in covered]
