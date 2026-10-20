"""One leased worker; each planning attempt commits independently of inference."""

import asyncio
import json
import os
import time

import httpx

from backend.config import Settings
from backend.contracts import ROOT, SCHEMAS, SECRET, DomainError, canonical, digest, plan_inputs, require, validate
from backend.store import Store, now, uid
from runner.model import ModelUnavailable, Ollama
from runner.pipeline import Pipeline
from runner.context import PlanningContext

# This product has no permission to export prompts to a tracing service.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
from langgraph.graph import END, START, StateGraph

POLICY = "Local Ollama Qwen/DeepSeek only; no paid fallback or external API."


def failure_reason(error):
    if isinstance(error, ExceptionGroup) and len(error.exceptions) == 1:
        return failure_reason(error.exceptions[0])
    if isinstance(error, (ModelUnavailable, httpx.HTTPError, MemoryError)):
        return "waiting_resource", "로컬 모델 또는 자원을 확인하고 재개하세요."
    if isinstance(error, DomainError):
        state = "waiting_resource" if error.code in ("RUNTIME_UNAVAILABLE", "TEMPORARILY_UNAVAILABLE") else "needs_input"
        return state, error.message
    return "failed", "역할 출력 또는 처리 오류입니다. 입력과 계약을 확인한 뒤 재개하세요."


class Worker:
    def __init__(self, store, model, settings=None):
        self.store, self.model, self.owner = store, model, uid()
        self.pipeline = Pipeline(store, settings.embedding if settings else "")
        async def role_step(state):
            return {"result": await self.model.generate(state["packet"], state["schema"])}
        graph = StateGraph(dict)
        graph.add_node("role", role_step)
        graph.add_edge(START, "role")
        graph.add_edge("role", END)
        self.role_graph = graph.compile()

    def heartbeat(self):
        with self.store.transaction() as db:
            clock = time.time()
            lock = db.execute("SELECT owner, expires FROM worker_lock WHERE id=1").fetchone()
            if lock and lock[0] != self.owner and lock[1] > clock:
                return False
            if not lock or lock[0] != self.owner or lock[1] <= clock:
                db.execute("INSERT OR IGNORE INTO attempt_results SELECT a.id, 'superseded', ? FROM attempts a "
                           "JOIN jobs j ON j.id=a.job_id WHERE j.state='running'", (now(),))
                db.execute("UPDATE jobs SET state='pending' WHERE state='running'")
            db.execute("INSERT OR REPLACE INTO worker_lock VALUES (1, ?, ?)", (self.owner, clock + 10))
            db.execute("INSERT OR REPLACE INTO worker_heartbeat VALUES (1, ?)", (clock,))
            return True

    def owns(self, db):
        row = db.execute("SELECT owner, expires FROM worker_lock WHERE id=1").fetchone()
        return row is not None and row[0] == self.owner and row[1] > time.time()

    def attempt_active(self, db, job):
        row = db.execute("SELECT a.owner,r.outcome FROM attempts a LEFT JOIN attempt_results r ON r.attempt_id=a.id WHERE a.id=? AND a.job_id=?", (job["attempt_id"], job["id"])).fetchone()
        return row is not None and row["owner"] == self.owner and row["outcome"] is None

    def claim(self):
        with self.store.transaction() as db:
            if not self.owns(db):
                return None
            for row in db.execute("SELECT * FROM jobs WHERE state='pending' ORDER BY rowid"):
                snapshot = self.store.load(db, row["run_id"])
                if (snapshot["mode"] != "live" or row["version"] != snapshot["state_version"] or
                        row["role"] not in {"planning": {"planner"}, "building": {"builder"}, "reviewing": {"validator", "security"}, "preview_ready": {"release"}}.get(snapshot["state"], set())):
                    db.execute("UPDATE jobs SET state='superseded' WHERE id=?", (row["id"],))
                    continue
                spec = db.execute("SELECT package FROM specs WHERE run_id=? ORDER BY rowid DESC LIMIT 1", (row["run_id"],)).fetchone()
                if snapshot["state"] != "planning" and not any(
                        a["state"] == "approved" and a["target"]["gate"] == "plan" and
                        a["target"]["spec_version_id"] == snapshot["spec_version_id"] and
                        a["target_digest"] == digest(a["target"]) and spec and
                        a["target"]["plan_digest"] == digest(json.loads(spec[0])) and
                        json.loads(spec[0])["contract_digests"] == plan_inputs() for a in snapshot["approvals"]):
                    snapshot.update(state="needs_input", reason="최신 계약·템플릿·검사 입력에 대한 기획 승인이 필요합니다.")
                    self.store.save(db, snapshot, "warning", snapshot["reason"])
                    db.execute("UPDATE jobs SET state='superseded' WHERE id=?", (row["id"],))
                    continue
                requests = [dict(r) for r in db.execute(
                    "SELECT id, content, created_at FROM requests WHERE project_id=? AND (run_id IS NULL OR run_id=?) ORDER BY rowid",
                    (snapshot["project_id"], row["run_id"]))]
                options = json.loads(row["context"] or "{}").get("options", {})
                if row["role"] == "builder":
                    tasks = [t for t in snapshot["tasks"] if t["role"] == "builder" and t["spec_version_id"] == snapshot["spec_version_id"] and t["state"] in ("ready", "pending", "running", "blocked")]
                    succeeded = {t["id"] for t in snapshot["tasks"] if t["state"] == "succeeded"}
                    task = next((t for t in tasks if set(t["depends_on"]).issubset(succeeded)), None)
                    if task is None:
                        snapshot.update(state="needs_input", reason="실행 가능한 구현 작업이 없습니다. 기획/작업 의존성을 확인하세요.")
                        self.store.save(db, snapshot, "warning", snapshot["reason"])
                        db.execute("UPDATE jobs SET state='superseded' WHERE id=?", (row["id"],))
                        continue
                    scope = db.execute("SELECT mode,files FROM task_scopes WHERE task_id=?", (task["id"],)).fetchone()
                    options["task_id"] = task["id"]
                    if scope:
                        options.update(task_mode=scope["mode"], writable_files=json.loads(scope["files"]))
                    task["state"] = "running"
                    task.pop("reason", None)
                    self.store.save(db, snapshot, "task_started", task["title"], bump=False, task_id=task["id"])
                packet = dict(role=row["role"], run_id=row["run_id"], state_version=row["version"],
                              spec_version_id=snapshot["spec_version_id"], requests=requests,
                              latest_spec=json.loads(spec[0]) if spec else None,
                              mandatory_policy=POLICY, permissions=["propose_plan"] if row["role"] == "planner" else [],
                              unresolved_failures=list(dict.fromkeys(options.get("unresolved_failures", []) + ([snapshot["reason"]] if snapshot.get("reason") else []))),
                              next_action="Propose one plan. Preserve corrections, list assumptions; never approve or execute tools.",
                              options=options,
                              template_contract=json.loads((ROOT / "templates/requests-v1/contract.json").read_text()),
                              recheck=POLICY)
                if row["role"] == "planner":
                    packet["next_action"] = ("Propose the smallest plan supported by template_contract. Clearly state limitations and assumptions. "
                        "Use observable API acceptance criteria only: health, create, list, update, invalid_input, persistent_storage. "
                        "No AI/auth/payment or other stacks. Unsupported requests must be listed in non_goals and require operator clarification. Never approve or execute.")
                attempt = uid()
                db.execute("UPDATE jobs SET state='running', context=? WHERE id=?", (canonical(packet), row["id"]))
                db.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?)", (attempt, row["id"], self.owner, canonical(packet), now()))
                return {**dict(row), "attempt_id": attempt, "packet": packet}
        return None

    def current(self, job):
        with self.store.transaction() as db:
            snapshot = self.store.load(db, job["run_id"])
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job["id"],)).fetchone()
            return (self.owns(db) and self.attempt_active(db, job) and row[0] == "running" and snapshot["state_version"] == job["version"] and
                    snapshot["mode"] == "live" and snapshot["state"] in ("planning", "building", "reviewing", "preview_ready", "deploying"))

    def publish_evidence(self, db, snapshot, job):
        task_id = job["packet"]["options"].get("task_id")
        for kind, schema, event in (("context", "ContextEvidence", "context_saved"), ("retrieval", "RetrievalEvidence", "retrieval_finished")):
            body = job.get(kind + "_evidence")
            if not body:
                continue
            validate(schema, body)
            artifact = self.store.artifact(db, snapshot, kind, "문맥 준비 근거" if kind == "context" else "역할별 검색 근거", body)
            for task in snapshot["tasks"]:
                if task["id"] == task_id:
                    task["artifact_ids"].append(artifact["id"])
            self.store.save(db, snapshot, event, artifact["title"], bump=False,
                            artifact_ids=[artifact["id"]], **({"task_id": task_id} if task_id else {}))

    def finish(self, job, proposal=None, failure=None):
        with self.store.transaction() as db:
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job["id"],)).fetchone()
            snapshot = self.store.load(db, job["run_id"])
            if (not self.owns(db) or not self.attempt_active(db, job) or row[0] != "running" or snapshot["state_version"] != job["version"] or
                    snapshot["mode"] != "live" or snapshot["state"] not in ("planning", "building", "reviewing", "preview_ready", "deploying")):
                db.execute("INSERT OR IGNORE INTO attempt_results VALUES (?, 'superseded', ?)", (job["attempt_id"], now()))
                return False
            if failure:
                state, reason = failure
                for task in snapshot["tasks"]:
                    if task["id"] == job["packet"]["options"].get("task_id"):
                        task.update(state="blocked", reason=reason)
                db.execute("UPDATE runs SET resume_state=? WHERE id=?", (snapshot["state"], snapshot["run_id"]))
                snapshot.update(state=state, reason=reason)
                self.publish_evidence(db, snapshot, job)
                self.store.save(db, snapshot, "resource_wait" if state == "waiting_resource" else "warning", reason)
            elif job["role"] == "planner":
                validate("PlanDraft", proposal)
                require(len({a["id"] for a in proposal["acceptance"]}) == len(proposal["acceptance"]),
                        "INVALID_COMMAND", "AC ID는 중복될 수 없습니다.", 422)
                spec_id = uid()
                package = {**proposal, "spec_version_id": spec_id, "stack": ["FastAPI", "Vue 3", "SQLite"],
                           "repository": None, "deployment": None,
                           "free_policy": POLICY, "allowed_tools": ["read_file", "patch_file", "container_checks"],
                           "contract_digests": plan_inputs()}
                validate("PlanView", package)
                db.execute("INSERT INTO specs VALUES (?, ?, ?, ?)", (spec_id, snapshot["run_id"], canonical(package), now()))
                self.store.artifact(db, snapshot, "spec", "승인할 기획", package)
                target = dict(gate="plan", spec_version_id=spec_id, plan_digest=digest(package))
                snapshot["approvals"].append(dict(id=uid(), state="pending", target_digest=digest(target), target=target))
                snapshot.update(spec_version_id=spec_id, state="awaiting_plan_approval")
                snapshot.pop("reason", None)
                phase_id, sprint_id = uid(), uid()
                snapshot["phases"].append(dict(id=phase_id, title="설계·구현", order=len(snapshot["phases"])))
                snapshot["sprints"].append(dict(id=sprint_id, phase_id=phase_id, title="승인 기획 구현", goal=proposal["goal"],
                                               acceptance_ids=[a["id"] for a in proposal["acceptance"]]))
                template = job["packet"]["template_contract"]
                boundaries = self.store.artifact(db, snapshot, "contract", "분야별 작업·쓰기 경계", dict(
                    tasks=template["implementation_tasks"], omitted_work=template["omitted_work"], spec_version_id=spec_id))
                predecessor = []
                for scope in template["implementation_tasks"]:
                    task_id = uid()
                    snapshot["tasks"].append(dict(id=task_id, phase_id=phase_id, sprint_id=sprint_id, spec_version_id=spec_id,
                        role="builder", work_kind=scope["kind"], title=scope["title"], state="pending" if predecessor else "ready",
                        depends_on=predecessor, acceptance_ids=[a["id"] for a in proposal["acceptance"]], artifact_ids=[boundaries["id"]]))
                    db.execute("INSERT INTO task_scopes VALUES (?, ?, ?)", (task_id, scope["mode"], canonical(scope["files"])))
                    predecessor = [task_id]
                if job.get("context_evidence"):
                    job["context_evidence"]["spec_version_id"] = spec_id
                self.publish_evidence(db, snapshot, job)
                self.store.save(db, snapshot, "plan_proposed", "기획 초안이 생성됐습니다. 내용을 확인하고 승인하세요.")
            else:
                raise ValueError("Role must finish through its pipeline step")
            db.execute("UPDATE jobs SET state='finished' WHERE id=?", (job["id"],))
            db.execute("INSERT INTO attempt_results VALUES (?, ?, ?)",
                       (job["attempt_id"], "failed" if failure else "finished", now()))
            return True

    async def tick(self):
        await asyncio.to_thread(self.pipeline.reconcile_cancelled, self)
        job = await asyncio.to_thread(self.claim)
        if not job:
            return False
        try:
            if job["role"] == "builder":
                await self.pipeline.build(job, self)
                return True
            if job["role"] in ("validator", "security"):
                await self.pipeline.review(job, self)
                return True
            if job["role"] == "release":
                await self.pipeline.release(job, self)
                return True
            proposal = None
            if job["role"] == "planner":
                proposal = await PlanningContext(self.store).plan(job, self, SCHEMAS["http.v1.schema.json"]["$defs"]["PlanDraft"])
                validate("PlanDraft", proposal)
                require(not SECRET.search(canonical(proposal)), "INVALID_COMMAND", "모델 출력에 비밀정보가 포함됐습니다.", 422)
            await asyncio.to_thread(self.finish, job, proposal)
        except Exception as error:
            await asyncio.to_thread(self.finish, job, failure=failure_reason(error))
        return True

    async def infer(self, job, packet, schema):
        if not await asyncio.to_thread(self.current, job):
            raise ModelUnavailable("Attempt superseded")
        generation = asyncio.create_task(self.role_graph.ainvoke({"packet": packet, "schema": schema}))
        try:
            while not generation.done():
                if not await asyncio.to_thread(self.current, job):
                    generation.cancel()
                    break
                await asyncio.sleep(0.2)
            return (await generation)["result"]
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            raise ModelUnavailable("Attempt superseded")
        finally:
            if not generation.done():
                generation.cancel()
            await asyncio.gather(generation, return_exceptions=True)

    async def run(self):
        require(await asyncio.to_thread(self.heartbeat), "RUNTIME_UNAVAILABLE", "다른 실행기가 lease를 보유하고 있습니다.")

        async def keep_alive():
            while True:
                await asyncio.sleep(2)
                if not await asyncio.to_thread(self.heartbeat):
                    raise RuntimeError("Worker lease lost")

        async def work():
            while True:
                if not await self.tick():
                    await asyncio.sleep(1)

        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(keep_alive())
            tasks.create_task(work())


if __name__ == "__main__":
    settings = Settings.from_env()
    asyncio.run(Worker(Store(settings.database), Ollama(settings.model, settings.ollama_url), settings).run())
