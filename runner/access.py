"""Server-issued job capabilities; a model never chooses its role or host paths."""

import hashlib
import json
import secrets
import time

from backend.contracts import SCHEMAS, require

def issue_grant(store, job, workspace=None):
    token = secrets.token_urlsafe(32)
    with store.transaction() as db:
        row = db.execute("SELECT role, version, state FROM jobs WHERE id=? AND run_id=?", (job["id"], job["run_id"])).fetchone()
        require(row is not None and row["role"] == job["role"] and row["state"] == "running" and row["version"] == job["version"],
                "FORBIDDEN", "실행 중인 서버 작업이 필요합니다.", 403)
        db.execute("INSERT INTO grants VALUES (?, ?, ?, ?, ?, ?)",
                   (hashlib.sha256(token.encode()).hexdigest(), job["id"], job["role"], str(workspace) if workspace else None, time.time() + 900, job["attempt_id"]))
    return token


class RoleScope:
    def __init__(self, store, token):
        self.store, self.key = store, hashlib.sha256(token.encode()).hexdigest()

    def authority(self, db=None):
        if db is None:
            with self.store.transaction() as connection:
                return self.authority(connection)
        row = db.execute("SELECT g.*, j.run_id, j.version, j.state, j.context FROM grants g JOIN jobs j ON j.id=g.job_id WHERE token_hash=?", (self.key,)).fetchone()
        require(row is not None and row["expires"] > time.time() and row["state"] == "running", "FORBIDDEN", "작업 권한이 만료됐습니다.", 403)
        attempt = db.execute("SELECT a.owner, r.outcome FROM attempts a LEFT JOIN attempt_results r ON r.attempt_id=a.id WHERE a.id=?", (row["attempt_id"],)).fetchone()
        lease = db.execute("SELECT owner, expires FROM worker_lock WHERE id=1").fetchone()
        require(attempt is not None and attempt["outcome"] is None and lease is not None and
                lease["owner"] == attempt["owner"] and lease["expires"] > time.time(), "FORBIDDEN", "현재 실행 시도의 권한이 아닙니다.", 403)
        snapshot = self.store.load(db, row["run_id"])
        require(snapshot["mode"] == "live" and snapshot["state_version"] == row["version"] and
                snapshot["state"] not in ("paused", "cancelled"), "FORBIDDEN", "현재 작업 권한이 아닙니다.", 403)
        return dict(row), snapshot["spec_version_id"]

    def resource(self, name):
        authority, spec_id = self.authority()
        if name == "contract":
            return SCHEMAS
        require(name == "spec" and spec_id is not None, "FORBIDDEN", "허용된 resource가 아닙니다.", 403)
        with self.store.transaction() as db:
            row = db.execute("SELECT package FROM specs WHERE id=? AND run_id=?", (spec_id, authority["run_id"])).fetchone()
            require(row is not None, "NOT_FOUND", "명세를 찾을 수 없습니다.", 404)
            return json.loads(row[0])
