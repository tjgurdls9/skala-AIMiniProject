"""One leased worker; each planning attempt commits independently of inference."""

import asyncio
import hashlib
import json
import time

import httpx

from backend.config import Settings
from backend.contracts import ROOT, SCHEMAS, SECRET, canonical, digest, require, validate
from backend.store import Store, now, uid
from runner.model import ModelUnavailable, Ollama

POLICY = "Local Ollama Qwen/DeepSeek only; no paid fallback or external API."


class Worker:
    def __init__(self, store, model):
        self.store, self.model, self.owner = store, model, uid()

    def heartbeat(self):
        with self.store.transaction() as db:
            clock = time.time()
            lock = db.execute("SELECT owner, expires FROM worker_lock WHERE id=1").fetchone()
            if lock and lock[0] != self.owner and lock[1] > clock:
                return False
            if not lock or lock[0] != self.owner:
                db.execute("INSERT OR IGNORE INTO attempt_results SELECT a.id, 'superseded', ? FROM attempts a "
                           "JOIN jobs j ON j.id=a.job_id WHERE j.state='running'", (now(),))
                db.execute("UPDATE jobs SET state='pending' WHERE state='running'")
            db.execute("INSERT OR REPLACE INTO worker_lock VALUES (1, ?, ?)", (self.owner, clock + 10))
            db.execute("INSERT OR REPLACE INTO worker_heartbeat VALUES (1, ?)", (clock,))
            return True

    def owns(self, db):
        row = db.execute("SELECT owner, expires FROM worker_lock WHERE id=1").fetchone()
        return row is not None and row[0] == self.owner and row[1] > time.time()

    def claim(self):
        with self.store.transaction() as db:
            if not self.owns(db):
                return None
            for row in db.execute("SELECT * FROM jobs WHERE state='pending' ORDER BY rowid"):
                snapshot = self.store.load(db, row["run_id"])
                if (snapshot["mode"] != "live" or row["version"] != snapshot["state_version"] or
                        snapshot["state"] not in ("planning", "building")):
                    db.execute("UPDATE jobs SET state='superseded' WHERE id=?", (row["id"],))
                    continue
                spec = db.execute("SELECT package FROM specs WHERE run_id=? ORDER BY rowid DESC LIMIT 1", (row["run_id"],)).fetchone()
                if snapshot["state"] == "building" and not any(
                        a["state"] == "approved" and a["target"]["gate"] == "plan" and
                        a["target"]["spec_version_id"] == snapshot["spec_version_id"] and
                        a["target_digest"] == digest(a["target"]) and spec and
                        a["target"]["plan_digest"] == digest(json.loads(spec[0])) for a in snapshot["approvals"]):
                    snapshot.update(state="needs_input", reason="최신 기획 승인이 필요합니다.")
                    self.store.save(db, snapshot, "warning", snapshot["reason"])
                    db.execute("UPDATE jobs SET state='superseded' WHERE id=?", (row["id"],))
                    continue
                requests = [dict(r) for r in db.execute(
                    "SELECT id, content, created_at FROM requests WHERE project_id=? AND (run_id IS NULL OR run_id=?) ORDER BY rowid",
                    (snapshot["project_id"], row["run_id"]))]
                packet = dict(role=row["role"], run_id=row["run_id"], state_version=row["version"],
                              spec_version_id=snapshot["spec_version_id"], requests=requests,
                              latest_spec=json.loads(spec[0]) if spec else None,
                              mandatory_policy=POLICY, permissions=["propose_plan"] if row["role"] == "planner" else [],
                              unresolved_failures=[snapshot["reason"]] if snapshot.get("reason") else [],
                              next_action="Propose one plan. Preserve corrections, list assumptions; never approve or execute tools.",
                              recheck=POLICY)
                attempt = uid()
                db.execute("UPDATE jobs SET state='running', context=? WHERE id=?", (canonical(packet), row["id"]))
                db.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?)", (attempt, row["id"], self.owner, canonical(packet), now()))
                return {**dict(row), "attempt_id": attempt, "packet": packet}
        return None

    def current(self, job):
        with self.store.transaction() as db:
            snapshot = self.store.load(db, job["run_id"])
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job["id"],)).fetchone()
            return (self.owns(db) and row[0] == "running" and snapshot["state_version"] == job["version"] and
                    snapshot["mode"] == "live" and snapshot["state"] in ("planning", "building"))

    def finish(self, job, proposal=None, failure=None):
        with self.store.transaction() as db:
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job["id"],)).fetchone()
            snapshot = self.store.load(db, job["run_id"])
            if (not self.owns(db) or row[0] != "running" or snapshot["state_version"] != job["version"] or
                    snapshot["mode"] != "live" or snapshot["state"] not in ("planning", "building")):
                db.execute("INSERT OR IGNORE INTO attempt_results VALUES (?, 'superseded', ?)", (job["attempt_id"], now()))
                return False
            if failure:
                state, reason = failure
                db.execute("UPDATE runs SET resume_state=? WHERE id=?", (snapshot["state"], snapshot["run_id"]))
                snapshot.update(state=state, reason=reason)
                self.store.save(db, snapshot, "resource_wait" if state == "waiting_resource" else "warning", reason)
            elif job["role"] == "planner":
                validate("PlanDraft", proposal)
                require(len({a["id"] for a in proposal["acceptance"]}) == len(proposal["acceptance"]),
                        "INVALID_COMMAND", "AC ID는 중복될 수 없습니다.", 422)
                spec_id = uid()
                package = {**proposal, "spec_version_id": spec_id, "stack": ["FastAPI", "Vue 3", "SQLite"],
                           "repository": None, "deployment": None, "free_policy": POLICY, "allowed_tools": [],
                           "contract_digests": {name: "sha256:" + hashlib.sha256((ROOT / "docs/planning" / name).read_bytes()).hexdigest()
                                                for name in SCHEMAS}}
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
                snapshot["tasks"].append(dict(id=uid(), phase_id=phase_id, sprint_id=sprint_id, spec_version_id=spec_id,
                                             role="builder", work_kind="integration", title="승인 명세 구현", state="pending",
                                             depends_on=[], acceptance_ids=[a["id"] for a in proposal["acceptance"]], artifact_ids=[]))
                self.store.save(db, snapshot, "plan_proposed", "기획 초안이 생성됐습니다. 내용을 확인하고 승인하세요.")
            else:
                # shortcut: isolated build tools are not connected, enable after D5 sandbox checks.
                db.execute("UPDATE runs SET resume_state='building' WHERE id=?", (snapshot["run_id"],))
                snapshot.update(state="waiting_resource", reason="격리 구현 실행기가 아직 연결되지 않았습니다. 구현 완료가 아닙니다.")
                self.store.save(db, snapshot, "resource_wait", snapshot["reason"])
            db.execute("UPDATE jobs SET state='finished' WHERE id=?", (job["id"],))
            db.execute("INSERT INTO attempt_results VALUES (?, ?, ?)",
                       (job["attempt_id"], "failed" if failure else "finished", now()))
            return True

    async def tick(self):
        job = await asyncio.to_thread(self.claim)
        if not job:
            return False
        try:
            proposal = None
            if job["role"] == "planner":
                # shortcut: conservative byte budget, replace with model tokenizer before longer contexts.
                if len(canonical(job["packet"]).encode()) > 4000:
                    await asyncio.to_thread(self.finish, job, failure=("needs_input", "문맥이 입력 예산을 초과했습니다. 필수 조건을 삭제하지 않고 작업 분해를 기다립니다."))
                    return True
                if not await asyncio.to_thread(self.current, job):
                    await asyncio.to_thread(self.finish, job)
                    return True
                generation = asyncio.create_task(self.model.generate(job["packet"], SCHEMAS["http.v1.schema.json"]["$defs"]["PlanDraft"]))
                try:
                    while not generation.done():
                        if not await asyncio.to_thread(self.current, job):
                            generation.cancel()
                            break
                        await asyncio.sleep(0.2)
                    proposal = await generation
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
                    await asyncio.to_thread(self.finish, job)
                    return True
                finally:
                    if not generation.done():
                        generation.cancel()
                    await asyncio.gather(generation, return_exceptions=True)
                validate("PlanDraft", proposal)
                require(not SECRET.search(canonical(proposal)), "INVALID_COMMAND", "모델 출력에 비밀정보가 포함됐습니다.", 422)
            await asyncio.to_thread(self.finish, job, proposal)
        except (ModelUnavailable, httpx.HTTPError, MemoryError):
            await asyncio.to_thread(self.finish, job, failure=("waiting_resource", "로컬 모델 또는 자원을 확인하고 재개하세요."))
        except Exception:
            await asyncio.to_thread(self.finish, job, failure=("failed", "역할 출력 또는 처리 오류입니다. 입력과 계약을 확인한 뒤 재개하세요."))
        return True

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
    asyncio.run(Worker(Store(settings.database), Ollama(settings.model, settings.ollama_url)).run())
