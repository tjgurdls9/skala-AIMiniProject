"""One durable build/review step at a time; only the server publishes results."""

import asyncio
import difflib
import json
import os
from pathlib import Path
import socket
import time

import httpx


from backend.contracts import ROOT, SECRET, canonical, digest, require
from backend.store import Store, now, uid
from runner.access import RoleScope, issue_grant
from runner.builder_loop import BuilderLoop
from runner.candidate import commit_task, freeze_model, workspace_state
from runner.commands import DockerExecutor
from runner.intervention import unledgered
from runner.tools import ToolBox
from runner.model import ModelUnavailable
from runner.sandbox import Sandbox
from runner.review import Reviewer, model_validation_body


class Pipeline:
    def __init__(self, store, embedding=""):
        self.store, self.embedding = store, embedding
        self.engine = Sandbox(store.path.parent)
        self.recovery_after = {}
        self.executor = None   # model tool executor: digest-pinned python/node images; injected in tests, built from env otherwise

    def reconcile_cancelled(self, worker):
        with self.store.transaction() as db:
            if not worker.owns(db):
                return
            rows = [dict(row) for row in db.execute("SELECT o.* FROM operations o JOIN runs r ON r.id=o.run_id WHERE json_extract(r.snapshot,'$.state')='cancelled' AND o.state IN ('pending','applied','uncertain')")]
        for row in rows:
            operation = json.loads(row["result"])
            if operation.get("kind") != "preview" or self.recovery_after.get(row["id"], 0) > time.monotonic():
                continue
            with self.store.transaction() as db:
                if not worker.owns(db):
                    return
            stopped = self.cleanup_preview(operation)
            state = ("superseded" if row["state"] == "applied" else "not_applied") if stopped else "uncertain"
            self.recovery_after[row["id"]] = time.monotonic() + 30
            with self.store.transaction() as db:
                if not worker.owns(db):
                    return
                db.execute("UPDATE operations SET state=? WHERE id=?", (state, row["id"]))
                snapshot = self.store.load(db, row["run_id"])
                if snapshot["state"] == "cancelled" and state != row["state"]:
                    self.store.save(db, snapshot, "tool_finished" if stopped else "operation_uncertain",
                                    "취소된 프리뷰 자원을 정리했습니다. 데이터 볼륨은 보존합니다." if stopped else "프리뷰 자원 정리 결과를 확인할 수 없습니다.", bump=False)

    def valid(self, db, job, worker):
        snapshot = self.store.load(db, job["run_id"])
        row = db.execute("SELECT state FROM jobs WHERE id=?", (job["id"],)).fetchone()
        if not worker.owns(db) or not worker.attempt_active(db, job) or row[0] != "running" or snapshot["mode"] != "live" or snapshot["state_version"] != job["version"]:
            return None
        return snapshot

    @staticmethod
    def completed(db, job):
        db.execute("UPDATE jobs SET state='finished' WHERE id=?", (job["id"],))
        db.execute("INSERT INTO attempt_results VALUES (?, 'finished', ?)", (job["attempt_id"], now()))

    def tool_executor(self):
        if self.executor is None:
            python, node = os.environ.get("LIFECYCLE_PYTHON_IMAGE"), os.environ.get("LIFECYCLE_NODE_IMAGE")
            require(bool(python and node), "RUNTIME_UNAVAILABLE", "격리 실행 이미지(LIFECYCLE_PYTHON_IMAGE, LIFECYCLE_NODE_IMAGE)가 구성되지 않았습니다.", 503)
            self.executor = DockerExecutor(dict(python=python, node=node))
        return self.executor

    @staticmethod
    def read_tree(workspace):
        """Text files of the workspace by relative path (the model can only write text), for before/after diffs."""
        tree = {}
        for path in sorted(workspace.rglob("*")):
            if path.is_file() and not path.is_symlink() and ".git" not in path.relative_to(workspace).parts:
                try:
                    tree[path.relative_to(workspace).as_posix()] = path.read_text()
                except UnicodeDecodeError:
                    continue
        return tree

    async def model_edit(self, job, worker, workspace):
        scope = RoleScope(self.store, await asyncio.to_thread(issue_grant, self.store, job, workspace))
        toolbox = ToolBox.from_scope(self.store, scope, self.tool_executor(), os.environ.get("LIFECYCLE_REGISTRY_NETWORK"),
                                     {"HTTPS_PROXY": os.environ["LIFECYCLE_REGISTRY_PROXY"]} if os.environ.get("LIFECYCLE_REGISTRY_PROXY") else None)
        await BuilderLoop(self.store).run(job, worker, toolbox)

    def edits_between_tasks(self, job, workspace):
        """Intervention marks for changes made after the previous task's commit and before this task started."""
        last = self.store.code_diffs(job["run_id"], job["packet"]["spec_version_id"])
        if not last:
            return []
        head, dirty = workspace_state(workspace)
        return ([dict(kind="history_changed", paths=[])] if head != last[-1]["commit"] else []) + \
               ([dict(kind="edited_between_tasks", paths=dirty)] if dirty else [])

    async def build(self, job, worker):
        options = job["packet"]["options"]
        runtime_image = digest(self.tool_executor().images)
        template_id = job["packet"]["template_contract"]["template"]
        workspace = await asyncio.to_thread(self.engine.workspace, job["run_id"], job["packet"]["spec_version_id"], template_id)
        inherited = await asyncio.to_thread(self.edits_between_tasks, job, workspace)
        before = self.read_tree(workspace)
        await self.model_edit(job, worker, workspace)
        after = self.read_tree(workspace)
        ledger = self.store.tool_calls(job["run_id"], options["task_id"])
        # one commit per finished task keeps the history reviewers and rollbacks need
        commit = await asyncio.to_thread(commit_task, workspace, options["task_id"], options.get("task_title", "작업"))
        with self.store.transaction() as db:
            snapshot = self.valid(db, job, worker)
            if snapshot is None:
                return
            task = next(t for t in snapshot["tasks"] if t["id"] == options["task_id"])
            changes = [{"path": path, "before_digest": digest(before.get(path, "")), "after_digest": digest(after.get(path, "")),
                        "diff": "".join(difflib.unified_diff(before.get(path, "").splitlines(True), after.get(path, "").splitlines(True), fromfile=path, tofile=path))}
                       for path in sorted(set(before) | set(after)) if before.get(path) != after.get(path)]
            found = inherited + ([dict(kind="outside_ledger", paths=paths)] if (paths := unledgered([c["path"] for c in changes], ledger)) else [])
            body = dict(spec_version_id=snapshot["spec_version_id"], task_id=task["id"], mode="edit", write_scope=list(options.get("write_scope", [])),
                        changes=changes, runtime_image=runtime_image, commit=commit, interventions=found)
            artifact = self.store.artifact(db, snapshot, "code_diff", task["title"] + " 결과", body)
            if found:
                self.store.save(db, snapshot, "warning", "도구 원장에 없는 작업 공간 변경이 있어 개입으로 표시했습니다. 자율 수행 근거로 쓰지 않습니다.", bump=False, task_id=task["id"])
            task["artifact_ids"].append(artifact["id"])
            worker.publish_evidence(db, snapshot, job)
            remaining = [t for t in snapshot["tasks"] if t["id"] != task["id"] and t["role"] == "builder" and
                         t["spec_version_id"] == snapshot["spec_version_id"] and t["state"] in ("pending", "ready", "running")]
            if remaining:
                task["state"] = "succeeded"
                succeeded = {t["id"] for t in snapshot["tasks"] if t["state"] == "succeeded"}
                for following in remaining:
                    if set(following["depends_on"]).issubset(succeeded):
                        following["state"] = "ready"
                self.store.save(db, snapshot, "task_finished", task["title"] + " 완료. 다음 의존 작업을 준비합니다.", task_id=task["id"])
                self.completed(db, job)
                self.store.schedule(db, snapshot, "builder")
                return
            self.store.save(db, snapshot, "tool_finished", "담당 파일 변경을 보존했습니다. 후보 고정이 필요합니다.", bump=False, task_id=task["id"])
        if not await asyncio.to_thread(worker.current, job):
            return
        candidate = await asyncio.to_thread(freeze_model, self.engine, workspace, Path(str(workspace) + ".deps"), self.tool_executor().images)
        candidate["template_id"] = template_id
        with self.store.transaction() as db:
            snapshot = self.valid(db, job, worker)
            if snapshot is None:
                return
            key = digest([job["attempt_id"], {k: candidate[k] for k in ("commit_sha", "image_digest", "manifest")}])
            builders = [t for t in snapshot["tasks"] if t["spec_version_id"] == snapshot["spec_version_id"] and t["role"] == "builder" and t["state"] != "superseded"]
            require(bool(builders), "INVALID_STATE", "활성 구현 작업이 필요합니다.")
            candidate["sprint_id"] = builders[-1]["sprint_id"]
            if Store.invalidate_acceptance(snapshot):
                self.store.save(db, snapshot, "approval_invalidated", "새 후보가 고정돼 이전 사람 확인 승인이 무효가 됐습니다.")
            db.execute("INSERT OR IGNORE INTO candidates VALUES (?, ?, ?, ?)",
                       (key, snapshot["run_id"], snapshot["spec_version_id"], canonical(candidate)))
            public = {k: candidate[k] for k in ("commit_sha", "image_digest", "manifest")}
            artifact = self.store.artifact(db, snapshot, "build", "고정 구현 후보", public)
            for task in builders:
                task.update(state="succeeded", artifact_ids=task["artifact_ids"] + [artifact["id"]])
            for role in ("validator", "security"):
                snapshot["tasks"].append(dict(id=uid(), phase_id=builders[-1]["phase_id"], sprint_id=builders[-1]["sprint_id"],
                    spec_version_id=snapshot["spec_version_id"], role=role, work_kind="validation" if role == "validator" else "security",
                    title="독립 기능 검증" if role == "validator" else "독립 보안 검사", state="ready", depends_on=[t["id"] for t in builders],
                    acceptance_ids=builders[-1]["acceptance_ids"], artifact_ids=[]))
            snapshot.update(state="reviewing", reports=[])
            snapshot.pop("reason", None)
            self.store.save(db, snapshot, "task_finished", "구현 후보 커밋과 이미지를 고정했습니다. 독립 검토가 필요합니다.")
            self.store.schedule(db, snapshot, "validator")
            self.completed(db, job)

    def candidate(self, db, snapshot):
        row = db.execute("SELECT id, body FROM candidates WHERE run_id=? AND spec_version_id=? ORDER BY rowid DESC LIMIT 1",
                         (snapshot["run_id"], snapshot["spec_version_id"])).fetchone()
        require(row is not None, "INVALID_STATE", "고정된 후보가 필요합니다.")
        return row[0], json.loads(row[1])

    async def review(self, job, worker):
        with self.store.transaction() as db:
            snapshot = self.store.load(db, job["run_id"])
            candidate_key, candidate = self.candidate(db, snapshot)
            spec = json.loads(db.execute("SELECT package FROM specs WHERE id=?", (snapshot["spec_version_id"],)).fetchone()[0])
            previous = db.execute("SELECT body FROM reviews WHERE run_id=? AND candidate_digest=? AND role=?",
                                  (job["run_id"], candidate_key, job["role"])).fetchone()
        reviewer = Reviewer(self.engine, lambda: worker.current(job))
        try:
            if previous:
                body = json.loads(previous[0])
            elif job["role"] == "validator":   # the approved checks decide; no model is asked
                outcomes, info = await asyncio.to_thread(reviewer.model_validation, candidate, spec.get("verification", []),
                                                         self.tool_executor().images["python"])
                body = model_validation_body(spec, outcomes, info)
            else:
                body = await asyncio.to_thread(reviewer.security, candidate, self.tool_executor().images["python"], spec.get("dependencies"))
        except Exception as error:
            body = dict(verdict="error", error_type=type(error).__name__, summary="검토 도구/입력 처리를 완료하지 못했습니다.")
        require(not SECRET.search(canonical(body)), "INVALID_COMMAND", "검토 출력에 비밀 형식이 포함됐습니다.", 422)
        body.update(role=job["role"], spec_version_id=spec["spec_version_id"], commit_sha=candidate["commit_sha"], image_digest=candidate["image_digest"])
        with self.store.transaction() as db:
            snapshot = self.valid(db, job, worker)
            if snapshot is None:
                return
            db.execute("INSERT OR IGNORE INTO reviews VALUES (?, ?, ?, ?, ?)", (uid(), job["run_id"], candidate_key, job["role"], canonical(body)))
            rows = db.execute("SELECT * FROM reviews WHERE run_id=? AND candidate_digest=? ORDER BY role", (job["run_id"], candidate_key)).fetchall()
            self.completed(db, job)
            if {row["role"] for row in rows} != {"validator", "security"}:
                # No public event/artifact exposes the first pending verdict to the other reviewer.
                self.store.schedule(db, snapshot, "security")
                return
            reports = []
            for row in rows:
                content = json.loads(row["body"])
                artifact = self.store.artifact(db, snapshot, "test_result" if row["role"] == "validator" else "security_result", "독립 " + row["role"] + " 보고서", content)
                reports.append(dict(id=row["id"], role=row["role"], spec_version_id=spec["spec_version_id"],
                    commit_sha=candidate["commit_sha"], image_digest=candidate["image_digest"], verdict=content["verdict"],
                    artifact_id=artifact["id"], content_digest=artifact["content_digest"]))
                for task in snapshot["tasks"]:
                    if task["spec_version_id"] == spec["spec_version_id"] and task["role"] == row["role"] and task["sprint_id"] == candidate["sprint_id"]:
                        task.update(state="succeeded" if content["verdict"] == "pass" else "blocked", artifact_ids=[artifact["id"]])
            snapshot["reports"] = reports
            if all(r["verdict"] == "pass" for r in reports):
                snapshot.update(state="preview_ready", reason="두 검토를 통과했습니다. 격리 프리뷰 준비가 필요합니다.")
                self.store.save(db, snapshot, "review_submitted", "동일 후보의 두 독립 검토를 수집했습니다.")
                self.store.schedule(db, snapshot, "release")
            else:
                db.execute("UPDATE runs SET resume_state='building' WHERE id=?", (job["run_id"],))
                snapshot.update(state="waiting_resource" if any(r["verdict"] in ("error", "not_run") for r in reports) else "needs_input",
                                reason="검증·보안 중 미충족 검토가 있어 출시를 차단했습니다. 근거를 확인하고 수정/재개하세요.")
                self.store.save(db, snapshot, "review_submitted", snapshot["reason"])

    async def release(self, job, worker):
        with self.store.transaction() as db:
            snapshot = self.valid(db, job, worker)
            if snapshot is None:
                return
            candidate_key, candidate = self.candidate(db, snapshot)
            require(snapshot["state"] == "preview_ready", "RUNTIME_UNAVAILABLE", "실제 배포 실행은 대상 확인·승인 후 연결됩니다.")
            require({r["role"] for r in snapshot["reports"]} == {"validator", "security"} and len(snapshot["reports"]) == 2 and
                    all(r["verdict"] == "pass" and r["commit_sha"] == candidate["commit_sha"] and
                        r["image_digest"] == candidate["image_digest"] and r["spec_version_id"] == snapshot["spec_version_id"] for r in snapshot["reports"]),
                    "INVALID_STATE", "같은 후보의 두 독립 검토가 필요합니다.")
            # Physical attempts get separate names; a stale cleanup cannot remove its successor.
            operation_id = digest([job["run_id"], candidate_key, "preview", job["attempt_id"]])
            unresolved = [(r["id"], json.loads(r["result"])) for r in db.execute(
                "SELECT id,result FROM operations WHERE run_id=? AND id!=? AND state IN ('pending','uncertain')",
                (job["run_id"], operation_id)) if json.loads(r["result"]).get("kind") == "preview"]
            old_preview = db.execute("SELECT p.body, c.spec_version_id, p.candidate_digest FROM previews p JOIN candidates c ON c.id=p.candidate_digest WHERE p.run_id=?", (job["run_id"],)).fetchone()
            old_operation = json.loads(old_preview["body"]) if old_preview else None
            previous = db.execute("SELECT result FROM operations WHERE id=?", (operation_id,)).fetchone()
            if previous:
                operation = json.loads(previous[0])
            else:
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                operation = dict(kind="preview", network="lifecycle-" + uid(), app="lifecycle-" + uid(), proxy="lifecycle-" + uid(),
                                 port=port, url=f"http://localhost:{port}", origin=f"http://localhost:{port}", commit_sha=candidate["commit_sha"])
                operation["data_volume"] = (old_operation.get("data_volume", old_operation["app"] + "-data")
                    if old_preview and old_preview["spec_version_id"] == snapshot["spec_version_id"] else
                    f"lifecycle-{job['run_id']}-{snapshot['spec_version_id']}-data")
                db.execute("INSERT INTO operations VALUES (?, ?, ?, 'pending', ?)",
                           (operation_id, job["run_id"], candidate_key, canonical(operation)))
        published = False
        starting = None
        try:
            for old_id, orphan in unresolved:
                stopped = await asyncio.to_thread(self.cleanup_preview, orphan)
                with self.store.transaction() as db:
                    db.execute("UPDATE operations SET state=? WHERE id=?", ("not_applied" if stopped else "uncertain", old_id))
                require(stopped, "TEMPORARILY_UNAVAILABLE", "이전 프리뷰 자원의 실제 상태를 확인한 뒤 재개하세요.", 503)
            starting = asyncio.create_task(asyncio.to_thread(self.preview_services, candidate, operation, lambda: worker.current(job)))
            await asyncio.shield(starting)
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5) as client:
                for _ in range(20):
                    if not await asyncio.to_thread(worker.current, job):
                        return
                    try:
                        response = await client.get(operation["url"] + candidate["app"]["health"])
                        if 200 <= response.status_code < 400:   # the same rule the validator applies to the path the app declared
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.5)
                else:
                    raise ModelUnavailable("Preview health unavailable")
            with self.store.transaction() as db:
                snapshot = self.valid(db, job, worker)
                if snapshot is None:
                    return
                preview = {k: operation[k] for k in ("url", "origin", "commit_sha")}
                self.store.artifact(db, snapshot, "preview", "격리 로컬 프리뷰", preview)
                db.execute("INSERT OR REPLACE INTO previews VALUES (?, ?, ?)", (job["run_id"], candidate_key, canonical(operation)))
                db.execute("UPDATE operations SET state='applied' WHERE id=?", (operation_id,))
                snapshot["reason"] = "로컬 프리뷰가 준비됐습니다. 실제 Git 푸시·배포는 대상과 승인을 확인한 뒤 진행합니다."
                if self.request_acceptance(db, snapshot, candidate):
                    snapshot["reason"] = "로컬 프리뷰가 준비됐습니다. 사람 확인이 필요한 기준을 프리뷰에서 확인하고 승인하세요."
                self.store.save(db, snapshot, "preview_ready", snapshot["reason"])
                self.completed(db, job)
                published = True
            if old_operation and old_operation["app"] != operation["app"]:
                await asyncio.to_thread(self.retire_preview, old_operation)
        finally:
            if not published:
                # Cancelling to_thread does not stop Docker; wait before confirming absence.
                if starting is not None:
                    await asyncio.gather(starting, return_exceptions=True)
                stopped = await asyncio.to_thread(self.cleanup_preview, operation)
                with self.store.transaction() as db:
                    db.execute("UPDATE operations SET state=? WHERE id=?", ("not_applied" if stopped else "uncertain", operation_id))

    @staticmethod
    def request_acceptance(db, snapshot, candidate):
        """Ask the user to confirm the criteria only a person can judge, once per candidate; True if a request was added."""
        package = json.loads(db.execute("SELECT package FROM specs WHERE id=?", (snapshot["spec_version_id"],)).fetchone()[0])
        target = Store.acceptance_target(snapshot, package, candidate["commit_sha"], candidate["image_digest"])
        if target is None or any(a["target"] == target and a["state"] in ("pending", "approved") for a in snapshot["approvals"]):
            return False
        snapshot["approvals"].append(dict(id=uid(), state="pending", target_digest=digest(target), target=target))
        return True

    def preview_services(self, candidate, operation, current):
        def active():
            if not current():
                raise ModelUnavailable("Attempt superseded")
        active()
        try:
            self.engine.docker("network", "inspect", operation["network"])
        except ModelUnavailable:
            self.engine.docker("network", "create", "--internal", operation["network"])
        ingress = operation["network"] + "-ingress"
        try:
            self.engine.docker("network", "inspect", ingress)
        except ModelUnavailable:
            self.engine.docker("network", "create", ingress)
        active()
        try:
            container = json.loads(self.engine.docker("inspect", operation["app"]))[0]
            require(container["Image"] == candidate["image_digest"], "INVALID_STATE", "기존 프리뷰 이미지가 다릅니다.")
            if not container["State"]["Running"]:
                self.engine.docker("start", operation["app"])
        except ModelUnavailable:
            self.engine.start_candidate(candidate, operation["network"], operation["app"], data_volume=operation.get("data_volume"))
        active()
        try:
            container = json.loads(self.engine.docker("inspect", operation["proxy"]))[0]
            require(container["Image"] == self.engine.runtime(), "INVALID_STATE", "프리뷰 프록시 이미지가 다릅니다.")
            if not container["State"]["Running"]:
                self.engine.docker("start", operation["proxy"])
        except ModelUnavailable:
            self.engine.docker("run", "-d", *self.engine.limits(operation["proxy"], operation["network"]),
                "--network", ingress,
                "--mount", f"type=bind,src={ROOT / 'infra/checks'},dst=/checks,readonly",
                "-p", f"127.0.0.1:{operation['port']}:8081", self.engine.runtime(), "python", "/checks/preview.py", operation["app"] + ":8080")

    def cleanup_preview(self, operation):
        stopped = self.engine.cleanup(operation["proxy"])
        stopped = self.engine.cleanup(operation["app"]) and stopped
        for network in (operation["network"] + "-ingress", operation["network"]):
            try:
                self.engine.docker("network", "rm", network)
            except ModelUnavailable:
                pass
        try:
            networks = self.engine.docker("network", "ls", "--format", "{{.Name}}").splitlines()
            return stopped and not {operation["network"], operation["network"] + "-ingress"}.intersection(networks)
        except ModelUnavailable:
            return False

    def retire_preview(self, operation):
        stopped = self.cleanup_preview(operation)
        with self.store.transaction() as db:
            db.execute("UPDATE operations SET state=? WHERE result=?", ("superseded" if stopped else "uncertain", canonical(operation)))
