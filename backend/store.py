import copy
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from backend.contracts import DomainError, canonical, digest, plan_inputs, require, validate


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid4().hex


def style_change(payload):
    text = payload["feedback"].casefold()
    # shortcut: only explicit CSS feedback reuses approval; ambiguous changes replan.
    return (payload["scope"] == "implementation" and
            bool(re.search(r"색|간격|여백|글꼴|폰트|레이아웃|배치|테두리|크기|색상|color|spacing|layout|font|css", text)) and
            not re.search(r"기능|추가|삭제|인증|권한|결제|데이터|저장|api|stack|deploy|배포|new|add|remove|auth|data|storage|script", text))


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
                CREATE TABLE IF NOT EXISTS worker_lock (
                    id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    owner TEXT NOT NULL, context TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempt_results (
                    attempt_id TEXT PRIMARY KEY REFERENCES attempts(id),
                    outcome TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS grants (
                    token_hash TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    role TEXT NOT NULL, workspace TEXT, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    spec_version_id TEXT NOT NULL REFERENCES specs(id), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS previews (
                    run_id TEXT PRIMARY KEY REFERENCES runs(id), candidate_digest TEXT NOT NULL,
                    body TEXT NOT NULL);
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
            if "attempt_id" not in {row[1] for row in db.execute("PRAGMA table_info(grants)")}:
                db.execute("ALTER TABLE grants ADD COLUMN attempt_id TEXT REFERENCES attempts(id)")
            for table in ("requests", "artifacts", "specs", "reviews", "events", "commands", "attempts", "attempt_results", "candidates"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{action.lower()}_blocked BEFORE {action} ON {table} "
                               f"BEGIN SELECT RAISE(ABORT, 'immutable record'); END")

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
        validate("ProjectCreate", data)
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

    def acceptance_status(self, run_id):
        with self.transaction() as db:
            snapshot = self.load(db, run_id)
            result = dict(spec_version_id=snapshot["spec_version_id"], items=[])
            if snapshot["spec_version_id"] is None:
                return result
            spec = json.loads(db.execute("SELECT package FROM specs WHERE id=?", (snapshot["spec_version_id"],)).fetchone()[0])
            report = next((r for r in snapshot["reports"] if r["role"] == "validator" and r["spec_version_id"] == snapshot["spec_version_id"]), None)
            statuses = {}
            if report:
                content = json.loads(db.execute("SELECT content FROM artifacts WHERE id=? AND public=1", (report["artifact_id"],)).fetchone()[0])
                require(digest(content) == report["content_digest"] and all(content.get(k) == report[k] for k in ("spec_version_id", "commit_sha", "image_digest", "role")),
                        "TEMPORARILY_UNAVAILABLE", "판정 근거 무결성을 확인할 수 없습니다.", 503)
                if report["verdict"] in ("pass", "fail"):
                    statuses = {item["id"]: item["status"] for item in content.get("judgement", {}).get("acceptance", [])}
            for ac in spec["acceptance"]:
                item = dict(id=ac["id"], status=statuses.get(ac["id"], "not_run" if report else "unmet"))
                if report:
                    item["report_id"] = report["id"]
                result["items"].append(item)
            validate("AcceptanceStatus", result)
            return result

    @staticmethod
    def save(db, snapshot, event_type, summary, bump=True, **fields):
        if bump:
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
    def schedule(db, snapshot, role="planner", options=None):
        db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                   (uid(), snapshot["run_id"], snapshot["state_version"], role, canonical({"options": options or {}}), now()))

    def create_run(self, project_id, data):
        validate("RunCreate", data)
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
        validate("Command", command)
        with self.transaction() as db:
            snapshot = self.load(db, run_id)
            require(command["run_id"] == run_id, "INVALID_COMMAND", "실행 ID가 일치하지 않습니다.", 422)
            previous = db.execute("SELECT body, receipt FROM commands WHERE run_id=? AND id=?",
                                  (run_id, command["command_id"])).fetchone()
            if previous:
                require(previous["body"] == canonical(command), "COMMAND_CONFLICT", "명령 ID가 다른 요청에 사용됐습니다.")
                return json.loads(previous["receipt"])
            require(snapshot["mode"] == "live", "REPLAY_READ_ONLY", "재생은 읽기 전용입니다.")
            if snapshot["state_version"] != command["expected_state_version"]:
                raise DomainError("VERSION_CONFLICT", "최신 스냅샷을 읽고 다시 요청하세요.",
                                  current_state_version=snapshot["state_version"])
            require(snapshot["state"] not in ("succeeded", "cancelled"), "INVALID_STATE", "종료된 실행에는 새 실행이 필요합니다.")
            action, payload = command["action"], command["payload"]
            event_type, summary = "run_state_changed", "실행 상태가 변경됐습니다."
            schedule = False
            options = {}
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
                schedule = snapshot["state"] in ("planning", "building", "reviewing", "preview_ready", "deploying")
                previous = db.execute("SELECT context FROM jobs WHERE run_id=? ORDER BY rowid DESC LIMIT 1", (run_id,)).fetchone()
                options = json.loads(previous[0] or "{}").get("options", {}) if previous else {}
                snapshot.pop("reason", None)
            elif action == "request_changes":
                known = {a["id"] for a in snapshot["artifacts"]}
                require(set(payload.get("artifact_ids", [])).issubset(known), "INVALID_COMMAND", "연결된 아티팩트가 필요합니다.", 422)
                db.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?)",
                           (uid(), snapshot["project_id"], run_id, payload["feedback"], now()))
                implementation = snapshot["state"] == "preview_ready" and style_change(payload)
                for approval in snapshot["approvals"]:
                    if not implementation or approval["target"]["gate"] != "plan":
                        approval["state"] = "invalidated"
                for task in snapshot["tasks"]:
                    task["state"] = "superseded"
                if implementation:
                    phase_id, sprint_id = snapshot["phases"][-1]["id"], uid()
                    previous = snapshot["sprints"][-1]
                    snapshot["sprints"].append(dict(id=sprint_id, phase_id=phase_id, title="프리뷰 스타일 수정", goal=payload["feedback"], acceptance_ids=previous["acceptance_ids"]))
                    snapshot["tasks"].append(dict(id=uid(), phase_id=phase_id, sprint_id=sprint_id,
                        spec_version_id=snapshot["spec_version_id"], role="builder", work_kind="frontend", title="스타일 수정", state="pending",
                        depends_on=[], acceptance_ids=previous["acceptance_ids"], artifact_ids=[]))
                    options = {"writable_files": ["app_frontend/style.css"]}
                    snapshot.update(state="building", reports=[], reason="스타일 수정 Sprint입니다. 같은 명세로 후보를 다시 검사합니다.")
                else:
                    snapshot.update(state="planning", spec_version_id=None, reports=[], reason="변경 원문을 보존했습니다. 기획 재승인이 필요합니다.")
                schedule, event_type, summary = True, "changes_requested", "변경 요청이 저장됐습니다."
            elif action == "decide":
                approval = next((a for a in snapshot["approvals"] if a["id"] == payload["approval_id"]), None)
                require(approval is not None and approval["state"] == "pending" and
                        approval["target_digest"] == payload["target_digest"] and
                        approval["target_digest"] == digest(approval["target"]) and
                        approval["target"]["spec_version_id"] == snapshot["spec_version_id"],
                        "STALE_APPROVAL", "최신 승인 대상을 다시 확인하세요.")
                gate = approval["target"]["gate"]
                require(gate == "plan" and snapshot["state"] == "awaiting_plan_approval",
                        "INVALID_STATE", "현재 승인 게이트가 아닙니다.")
                spec = db.execute("SELECT package FROM specs WHERE id=? AND run_id=?",
                                  (snapshot["spec_version_id"], run_id)).fetchone()
                require(spec is not None and approval["target"]["plan_digest"] == digest(json.loads(spec[0])),
                        "STALE_APPROVAL", "저장된 기획과 승인 대상이 일치하지 않습니다.")
                require(json.loads(spec[0])["contract_digests"] == plan_inputs(),
                        "STALE_APPROVAL", "계약·템플릿·검사 입력이 바뀌었습니다. 재기획 후 승인하세요.")
                approval.update(state="approved" if payload["decision"] == "approve" else "rejected",
                                decided_by="local-operator", decided_at=now())
                if "feedback" in payload:
                    approval["feedback"] = payload["feedback"]
                    db.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?)",
                               (uid(), snapshot["project_id"], run_id, payload["feedback"], now()))
                snapshot["state"] = "building" if payload["decision"] == "approve" else "needs_input"
                schedule = payload["decision"] == "approve"
                event_type, summary = "approval_decided", "승인 결정이 저장됐습니다."
            db.execute("UPDATE jobs SET state='superseded' WHERE run_id=? AND state IN ('pending','running')", (run_id,))
            self.save(db, snapshot, event_type, summary, command_id=command["command_id"])
            if schedule:
                role = {"planning": "planner", "building": "builder", "reviewing": "validator", "preview_ready": "release", "deploying": "release"}[snapshot["state"]]
                self.schedule(db, snapshot, role, options)
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

    def replay_recordings(self):
        with self.transaction() as db:
            result = []
            for row in db.execute("SELECT r.snapshot, p.title FROM runs r JOIN projects p ON p.id=r.project_id ORDER BY r.rowid DESC"):
                snapshot = json.loads(row[0])
                if snapshot["mode"] != "live":
                    continue
                events = [json.loads(r[0]) for r in db.execute(
                    "SELECT body FROM events WHERE run_id=? ORDER BY seq", (snapshot["run_id"],))]
                result.append(dict(project_id=snapshot["project_id"], title=row[1], source_run_id=snapshot["run_id"],
                                   recorded_at=now(), manifest_digest=digest({"snapshot": snapshot, "events": events})))
            return result
