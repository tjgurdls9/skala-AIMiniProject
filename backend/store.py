import copy
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from backend.contracts import canonical, digest, require, validate


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid4().hex


class Store:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    run_id TEXT, content TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    snapshot TEXT NOT NULL, resume_state TEXT, source_run_id TEXT);
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL REFERENCES runs(id), seq INTEGER NOT NULL,
                    body TEXT NOT NULL, PRIMARY KEY(run_id, seq));
                CREATE TABLE IF NOT EXISTS commands (
                    run_id TEXT NOT NULL REFERENCES runs(id), id TEXT NOT NULL,
                    body TEXT NOT NULL, receipt TEXT NOT NULL, PRIMARY KEY(run_id, id));
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    metadata TEXT NOT NULL, content TEXT NOT NULL, public INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS specs (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    package TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    version INTEGER NOT NULL, role TEXT NOT NULL, state TEXT NOT NULL,
                    context TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS worker_heartbeat (
                    id INTEGER PRIMARY KEY CHECK(id=1), updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    target_digest TEXT NOT NULL, state TEXT NOT NULL, result TEXT);
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    candidate_digest TEXT NOT NULL, role TEXT NOT NULL,
                    body TEXT NOT NULL, UNIQUE(run_id, candidate_digest, role));
                CREATE TRIGGER IF NOT EXISTS requests_immutable BEFORE UPDATE ON requests
                    BEGIN SELECT RAISE(ABORT, 'immutable request'); END;
                CREATE TRIGGER IF NOT EXISTS artifacts_immutable BEFORE UPDATE ON artifacts
                    BEGIN SELECT RAISE(ABORT, 'immutable artifact'); END;
                CREATE TRIGGER IF NOT EXISTS specs_immutable BEFORE UPDATE ON specs
                    BEGIN SELECT RAISE(ABORT, 'immutable spec'); END;
                CREATE TRIGGER IF NOT EXISTS reviews_immutable BEFORE UPDATE ON reviews
                    BEGIN SELECT RAISE(ABORT, 'immutable review'); END;
            """)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def project(self, data):
        result = {"project_id": uid(), "title": data["title"], "created_at": now()}
        with self.transaction() as db:
            db.execute("INSERT INTO projects VALUES (?, ?, ?)", tuple(result.values()))
            db.execute("INSERT INTO requests VALUES (?, ?, NULL, ?, ?)",
                       (uid(), result["project_id"], data["request"], now()))
        return result

    @staticmethod
    def load(db, run_id):
        row = db.execute("SELECT snapshot FROM runs WHERE id=?", (run_id,)).fetchone()
        require(row is not None, "NOT_FOUND", "실행을 찾을 수 없습니다.", 404)
        return json.loads(row["snapshot"])

    def snapshot(self, run_id):
        with self.transaction() as db:
            return self.load(db, run_id)

    @staticmethod
    def save(db, snapshot, event_type, summary, **fields):
        snapshot["state_version"] += 1
        snapshot["last_event_seq"] += 1
        validate("Snapshot", snapshot)
        event = dict(kind="event", protocol_version=1, event_id=uid(),
                     seq=snapshot["last_event_seq"], run_id=snapshot["run_id"], mode=snapshot["mode"],
                     state_version=snapshot["state_version"], occurred_at=now(),
                     event_type=event_type, summary=summary, artifact_ids=[], **fields)
        validate("Event", event)
        db.execute("INSERT INTO events VALUES (?, ?, ?)", (snapshot["run_id"], event["seq"], canonical(event)))
        db.execute("UPDATE runs SET snapshot=? WHERE id=?", (canonical(snapshot), snapshot["run_id"]))

    @staticmethod
    def schedule(db, snapshot, role="planner"):
        db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, 'pending', NULL, ?)",
                   (uid(), snapshot["run_id"], snapshot["state_version"], role, now()))

    def create_run(self, project_id, data):
        with self.transaction() as db:
            project = db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
            require(project is not None, "NOT_FOUND", "프로젝트를 찾을 수 없습니다.", 404)
            run_id = uid()
            if data["mode"] == "replay":
                source = self.load(db, data["source_run_id"])
                require(source["project_id"] == project_id and source["mode"] == "live",
                        "NOT_FOUND", "같은 프로젝트의 실제 기록이 필요합니다.", 404)
                rows = db.execute("SELECT body FROM events WHERE run_id=? ORDER BY seq", (source["run_id"],)).fetchall()
                manifest = {"snapshot": source, "events": [json.loads(r[0]) for r in rows]}
                snapshot = copy.deepcopy(source)
                snapshot.update(run_id=run_id, mode="replay", replay_source={
                    "source_run_id": source["run_id"], "recorded_at": now(), "manifest_digest": digest(manifest)})
                db.execute("INSERT INTO runs VALUES (?, ?, ?, NULL, ?)",
                           (run_id, project_id, canonical(snapshot), source["run_id"]))
                # Artifact records are immutable; replay resolves IDs through its frozen source snapshot.
                for row in rows:
                    event = json.loads(row[0])
                    event.update(run_id=run_id, mode="replay")
                    db.execute("INSERT INTO events VALUES (?, ?, ?)", (run_id, event["seq"], canonical(event)))
            else:
                snapshot = dict(kind="snapshot", protocol_version=1, project_id=project_id, run_id=run_id,
                                mode="live", state="planning", state_version=0, last_event_seq=0,
                                spec_version_id=None, phases=[], sprints=[], tasks=[], approvals=[], reports=[], artifacts=[])
                db.execute("INSERT INTO runs VALUES (?, ?, ?, NULL, NULL)", (run_id, project_id, canonical(snapshot)))
                self.save(db, snapshot, "run_state_changed", "기획 작업이 접수됐습니다.")
                self.schedule(db, snapshot)
            validate("Snapshot", snapshot)
            return snapshot

    def events(self, run_id, cursor):
        with self.transaction() as db:
            snapshot = self.load(db, run_id)
            require(0 <= cursor <= snapshot["last_event_seq"], "CURSOR_INVALID", "최신 스냅샷으로 다시 연결하세요.")
            return [json.loads(r[0]) for r in db.execute(
                "SELECT body FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 200", (run_id, cursor))]

    def command(self, run_id, command):
        with self.transaction() as db:
            snapshot = self.load(db, run_id)
            require(command["run_id"] == run_id, "INVALID_COMMAND", "실행 ID가 일치하지 않습니다.", 422)
            previous = db.execute("SELECT body, receipt FROM commands WHERE run_id=? AND id=?",
                                  (run_id, command["command_id"])).fetchone()
            if previous:
                require(previous["body"] == canonical(command), "COMMAND_CONFLICT", "명령 ID가 다른 요청에 사용됐습니다.")
                return json.loads(previous["receipt"])
            require(snapshot["mode"] == "live", "REPLAY_READ_ONLY", "재생은 읽기 전용입니다.")
            require(snapshot["state_version"] == command["expected_state_version"], "VERSION_CONFLICT", "최신 스냅샷을 읽고 다시 요청하세요.")
            require(snapshot["state"] not in ("succeeded", "cancelled"), "INVALID_STATE", "종료된 실행에는 새 실행이 필요합니다.")
            action, payload = command["action"], command["payload"]
            event_type, summary = "run_state_changed", "실행 상태가 변경됐습니다."
            schedule = False
            if action in ("pause", "cancel"):
                if snapshot["state"] != "paused":
                    db.execute("UPDATE runs SET resume_state=? WHERE id=?", (snapshot["state"], run_id))
                snapshot["state"] = "paused" if action == "pause" else "cancelled"
            elif action == "resume":
                require(snapshot["state"] in ("paused", "waiting_resource", "waiting_quota", "needs_input", "failed"),
                        "INVALID_STATE", "현재 상태는 재개 대상이 아닙니다.")
                row = db.execute("SELECT resume_state FROM runs WHERE id=?", (run_id,)).fetchone()
                snapshot["state"] = row[0] or "planning"
                # The worker rechecks readiness and approval before any new work.
                schedule = snapshot["state"] in ("planning", "building")
                snapshot.pop("reason", None)
            elif action == "request_changes":
                known = {a["id"] for a in snapshot["artifacts"]}
                require(set(payload.get("artifact_ids", [])).issubset(known), "INVALID_COMMAND", "연결된 아티팩트가 필요합니다.", 422)
                db.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?)",
                           (uid(), snapshot["project_id"], run_id, payload["feedback"], now()))
                for approval in snapshot["approvals"]:
                    approval["state"] = "invalidated"
                for task in snapshot["tasks"]:
                    task["state"] = "superseded"
                # shortcut: scope classification is not implemented, all changes require plan reapproval.
                snapshot.update(state="planning", spec_version_id=None, reports=[], reason="변경 원문을 보존했습니다. 기획 재승인이 필요합니다.")
                schedule, event_type, summary = True, "changes_requested", "변경 요청이 저장됐습니다."
            elif action == "decide":
                approval = next((a for a in snapshot["approvals"] if a["id"] == payload["approval_id"]), None)
                require(approval is not None and approval["state"] == "pending" and
                        approval["target_digest"] == payload["target_digest"] and
                        approval["target_digest"] == digest(approval["target"]) and
                        approval["target"]["spec_version_id"] == snapshot["spec_version_id"],
                        "STALE_APPROVAL", "최신 승인 대상을 다시 확인하세요.")
                require(approval["target"]["gate"] == "plan" and snapshot["state"] == "awaiting_plan_approval",
                        "RUNTIME_UNAVAILABLE", "배포 실행기는 아직 활성화되지 않았습니다.")
                approval.update(state="approved" if payload["decision"] == "approve" else "rejected",
                                decided_by="local-operator", decided_at=now())
                if "feedback" in payload:
                    approval["feedback"] = payload["feedback"]
                snapshot["state"] = "building" if payload["decision"] == "approve" else "needs_input"
                schedule = payload["decision"] == "approve"
                event_type, summary = "approval_decided", "기획 승인 결정이 저장됐습니다."
            db.execute("UPDATE jobs SET state='superseded' WHERE run_id=? AND state IN ('pending','running')", (run_id,))
            self.save(db, snapshot, event_type, summary, command_id=command["command_id"])
            if schedule:
                self.schedule(db, snapshot, "builder" if snapshot["state"] == "building" else "planner")
            receipt = dict(command_id=command["command_id"], run_id=run_id, status="accepted", accepted_at=now())
            db.execute("INSERT INTO commands VALUES (?, ?, ?, ?)", (run_id, command["command_id"], canonical(command), canonical(receipt)))
            return receipt

    @staticmethod
    def artifact(db, snapshot, kind, title, content, public=True):
        metadata = dict(id=uid(), title=title, kind=kind, content_digest=digest(content), public_summary=title)
        validate("Artifact", metadata)
        db.execute("INSERT INTO artifacts VALUES (?, ?, ?, ?, ?)",
                   (metadata["id"], snapshot["run_id"], canonical(metadata), canonical(content), int(public)))
        if public:
            snapshot["artifacts"].append(metadata)
        return metadata

    def read_artifact(self, artifact_id):
        with self.transaction() as db:
            row = db.execute("SELECT content, metadata FROM artifacts WHERE id=? AND public=1", (artifact_id,)).fetchone()
            require(row is not None, "NOT_FOUND", "아티팩트를 찾을 수 없습니다.", 404)
            content, metadata = json.loads(row[0]), json.loads(row[1])
            require(digest(content) == metadata["content_digest"], "TEMPORARILY_UNAVAILABLE", "아티팩트 무결성을 확인할 수 없습니다.", 503)
            return content
