"""Model-driven planning extras: idea alternatives, work breakdown and per-AC verification.

Each step is one small bounded call. The service validates what the model proposes and returns the errors to it;
it never fills in an answer. A repeated identical mistake stops for the user (no hidden attempt cap, no spin)."""
import asyncio
import copy
import json
import re

from jsonschema import Draft202012Validator, ValidationError

from backend.contracts import SCHEMAS, digest, require
from backend.store import now
from runner.context import bounded, mandatory
from runner.commands import TOOL_POLICY
from runner.plan_checks import AREAS, INLINE_FLAGS, check_verification, check_work_plan

DEFS = SCHEMAS["http.v1.schema.json"]["$defs"]
KINDS = ["contract", "infra", "backend", "frontend", "ai_data", "integration"]
MAX_CHECKS_PER_AC = 3

ALTERNATIVES_SCHEMA = dict(type="object", additionalProperties=False, required=["alternatives"], properties=dict(
    alternatives=dict(type="array", minItems=1, maxItems=3, items=DEFS["PlanAlternative"]),
    single_reason=dict(type="string", maxLength=2000)))
AREA_JUDGEMENT = dict(type="object", additionalProperties=False, required=["needed", "reason"], properties=dict(
    needed=dict(type="boolean"), reason=dict(type="string", minLength=1, maxLength=2000)))
WORK_PLAN_SCHEMA = dict(type="object", additionalProperties=False, required=["areas", "work_plan"], properties=dict(
    areas=dict(type="object", additionalProperties=False, required=list(AREAS), properties={area: AREA_JUDGEMENT for area in AREAS}),
    work_plan=dict(type="array", minItems=1, maxItems=30, items=DEFS["WorkItem"]),
    dependencies=DEFS["PlanDependencies"]))


def omitted_areas(areas):
    """The areas the model itself judged not needed, with its own reason; the service decides nothing here."""
    return [dict(kind=area, reason=areas[area]["reason"]) for area in AREAS if not areas[area]["needed"]]
VERIFICATION_SCHEMA = dict(type="object", additionalProperties=False, required=["checks"], properties=dict(
    checks=dict(type="array", maxItems=MAX_CHECKS_PER_AC, items=DEFS["CheckSpec"]),
    manual_reason=dict(type=["string", "null"], maxLength=2000)))


FILE_PATH_PATTERN = "^[A-Za-z0-9_.-][^ ]*$"   # workspace-relative: no leading slash; no backslash, which Ollama's grammar rejects


def sampling_verification_schema():
    """The verification answer shape the model is sampled with: policy it keeps breaking is enforced by the format itself.
    The server still validates with VERIFICATION_SCHEMA and the full check rules, so this only narrows what is generated."""
    schema = copy.deepcopy(VERIFICATION_SCHEMA)
    inline_programs = [e for e in TOOL_POLICY["executables"] if e in INLINE_FLAGS]
    for variant in schema["properties"]["checks"]["items"]["oneOf"]:
        properties = variant["properties"]
        if properties["kind"] == {"const": "command"}:
            properties["argv"] = dict(properties["argv"], prefixItems=[{"enum": inline_programs}])
        elif properties["kind"] == {"const": "file"}:
            properties["path"] = dict(properties["path"], pattern=FILE_PATH_PATTERN)
    return schema


SCOPE_PATTERN = "^[^/ ][^ ]*$"   # a write scope is a workspace-relative glob: no leading slash; no backslash, which Ollama's grammar rejects


def sampling_work_plan_schema():
    """The work-plan answer shape the model is sampled with; the server still validates the contract schema and check_work_plan."""
    schema = copy.deepcopy(WORK_PLAN_SCHEMA)
    scope = schema["properties"]["work_plan"]["items"]["properties"]["write_scope"]
    scope["items"] = dict(scope["items"], pattern=SCOPE_PATTERN)
    return schema


def summary(plan):
    return {k: plan[k] for k in ("goal", "features", "non_goals", "constraints")} | dict(
        acceptance=[dict(id=a["id"], title=a["title"], description=a["description"]) for a in plan["acceptance"]])


class PlanExtras:
    def __init__(self, store):
        self.store = store

    # -- bounded ask with validation feedback ---------------------------
    async def ask(self, job, worker, step, call, schema, check, sampling=None):
        key = digest(["plan-extras", job["run_id"], step, call])   # step inputs only; volatile failure notes must not change it
        call = dict(role="planner", step=step, **mandatory(job["packet"]), **call)
        cached = self._recall(key)
        if cached is not None:
            return cached
        seen = set()
        while True:
            proposal = await worker.infer(job, bounded(dict(call)), sampling or schema)
            try:
                Draft202012Validator(schema).validate(proposal)
                errors = check(proposal)
            except ValidationError as error:
                errors = [f"형식 오류: {error.message[:300]}"]
            if not errors:
                self._remember(key, proposal)
                return proposal
            await asyncio.to_thread(self.store.record_model_output, dict(
                run_id=job["run_id"], job_id=job.get("id"), attempt_id=job.get("attempt_id"), role="planner", step=step,
                kind="rejected", content=json.dumps(errors, ensure_ascii=False)))
            current = digest(errors)
            # a mistake that comes back, even after a different one, is no progress (the model may alternate between two wrong answers)
            require(current not in seen, "INVALID_COMMAND", f"{step} 단계에서 같은 오류가 반복돼 사람의 입력이 필요합니다: {errors[0]}", 422)
            seen.add(current)
            call = dict(call, previous_errors=errors[:5])

    def _recall(self, key):
        with self.store.transaction() as db:
            row = db.execute("SELECT body FROM context_steps WHERE source_digest=? AND step=0", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _remember(self, key, proposal):
        with self.store.transaction() as db:
            db.execute("INSERT OR IGNORE INTO context_steps VALUES (?, 0, ?, ?)", (key, json.dumps(proposal, ensure_ascii=False), now()))

    # -- steps ----------------------------------------------------------
    async def alternatives(self, job, worker, plan):
        selected = job["packet"]["options"].get("selected_alternative_id")
        if selected is not None:   # the user chose among the alternatives already shown; do not regenerate them
            prior = (job["packet"].get("prior_draft") or {}).get("alternatives", [])
            require(selected in {a["id"] for a in prior}, "INVALID_COMMAND", "선택한 대안이 직전 초안에 없습니다.", 422)
            return dict(alternatives=prior, selected_alternative_id=selected)

        def check(value):
            ids = [a["id"] for a in value["alternatives"]]
            errors = ["대안 ID가 중복됐습니다."] if len(set(ids)) != len(ids) else []
            if len(ids) == 1 and not value.get("single_reason", "").strip():
                errors.append("대안이 하나뿐이면 그 이유(single_reason)가 필요합니다.")
            return errors
        value = await self.ask(job, worker, "alternatives", dict(
            current_plan=summary(plan),
            instructions="Propose 1 to 3 alternative approaches. The FIRST alternative describes the current plan itself. Each alternative needs "
                         "id, summary, differences versus the current plan, and risks. If only one approach is reasonable return exactly one "
                         "alternative and explain why in single_reason. Do not invent requirements."), ALTERNATIVES_SCHEMA, check)
        result = dict(alternatives=value["alternatives"], selected_alternative_id=value["alternatives"][0]["id"])
        if len(value["alternatives"]) == 1:
            result["single_alternative_reason"] = value["single_reason"]
        return result

    async def work_plan(self, job, worker, plan):
        def check(value):
            return check_work_plan(value["work_plan"], omitted_areas(value["areas"]), plan["acceptance"])
        value = await self.ask(job, worker, "work_plan", dict(
            plan=summary(plan), stack=job["packet"]["template_contract"].get("stack", []), kinds=KINDS,
            instructions="First judge each area (" + ", ".join(AREAS) + ") in `areas`: needed true or false, with a short reason either way. "
                         "Then break the plan into work items. Each item: id, kind, title, depends_on (item ids), acceptance_ids (plan AC ids), "
                         "write_scope (glob paths this item alone writes). Items that are not ordered by depends_on must not share paths. "
                         "Every AC must be linked to an item. An area judged needed must have at least one work item of that kind; an area judged "
                         "not needed must have none. Put the packages the work needs in dependencies.pip / dependencies.npm."),
            WORK_PLAN_SCHEMA, check, sampling_work_plan_schema())
        return dict(work_plan=value["work_plan"], omitted_areas=omitted_areas(value["areas"]), dependencies=value.get("dependencies", {}))

    async def verification(self, job, worker, plan, work_plan):
        specs, manual, prefixes = [], [], set()
        areas = [dict(kind=i["kind"], title=i["title"], write_scope=i["write_scope"]) for i in work_plan]
        for ac in plan["acceptance"]:
            def check(value, ac=ac):
                return check_verification([dict(c, ac_ids=[ac["id"]]) for c in value["checks"]], [], plan["acceptance"])   # the model's own ids, so errors name its checks
            value = await self.ask(job, worker, "verification", dict(
                acceptance_criterion=dict(id=ac["id"], title=ac["title"], description=ac["description"]),
                features=plan["features"], work_areas=areas,
                instructions="Propose up to 3 declarative checks (http, command or file) that demonstrate this single acceptance criterion "
                             "against the finished app. Give each a unique short id and put this criterion's id in ac_ids. If it cannot be "
                             "checked mechanically return no checks and explain in manual_reason. A command check must be self-contained inline code "
                             "(python -c or node -e that imports the implementation and asserts the expected value); it must never run test files or a test runner."), VERIFICATION_SCHEMA, check, sampling_verification_schema())
            prefix = re.sub(r"[^A-Za-z0-9_-]", "_", ac["id"])[:30] or "ac"
            if prefix in prefixes:   # different criterion ids can sanitise to the same text; a check id must still name one check
                prefix = f"{prefix[:24]}_{len(prefixes) + 1}"
            prefixes.add(prefix)
            specs += [dict(c, id=f"{prefix}-{n}", ac_ids=[ac["id"]]) for n, c in enumerate(value["checks"], 1)]
            if not value["checks"] and value.get("manual_reason"):
                manual.append(dict(ac_id=ac["id"], reason=value["manual_reason"]))
        problems = check_verification(specs, manual, plan["acceptance"])
        require(not problems, "INVALID_COMMAND", "점검 명세가 서로 맞지 않습니다: " + "; ".join(problems[:3]), 422)
        return dict(verification=specs, manual_acceptance=manual)
