"""Server-issued job capabilities; a model never chooses its role or host paths."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import tempfile
import time

from backend.contracts import SCHEMAS, SECRET, digest, require

WRITABLE_FILES = ("app_backend/main.py", "app_frontend/app.js", "app_frontend/index.html", "app_frontend/style.css")

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

    def path(self, name, db=None):
        authority, _ = self.authority(db)
        require(isinstance(name, str), "FORBIDDEN", "파일 이름이 필요합니다.", 403)
        relative = PurePosixPath(name)
        require(isinstance(name, str) and len(name) <= 200 and not relative.is_absolute() and
                ".." not in relative.parts and "\\" not in name and bool(relative.parts) and
                relative.parts[0] in ("app_backend", "app_frontend") and
                all(not p.startswith(".") and not any(ord(c) < 32 for c in p) for p in relative.parts),
                "FORBIDDEN", "담당 앱 파일 경계를 벗어났습니다.", 403)
        require(authority["workspace"] is not None, "FORBIDDEN", "작업 공간이 없습니다.", 403)
        root = Path(authority["workspace"])
        require(not root.is_symlink(), "FORBIDDEN", "심볼릭 링크 작업 공간은 허용하지 않습니다.", 403)
        path = root
        for part in relative.parts:
            path = path / part
            require(not path.is_symlink(), "FORBIDDEN", "심볼릭 링크는 허용하지 않습니다.", 403)
        require(path.resolve().is_relative_to(root.resolve()), "FORBIDDEN", "작업 공간을 벗어났습니다.", 403)
        return path

    def read(self, name):
        path = self.path(name)
        require(path.is_file() and path.stat().st_size <= 65536, "NOT_FOUND", "읽을 수 있는 작은 파일이 필요합니다.", 404)
        content = path.read_text()
        return dict(path=name, content=content, content_digest=digest(content))

    def patch(self, name, content, expected_digest):
        require(isinstance(content, str) and len(content.encode()) <= 65536 and not SECRET.search(content),
                "INVALID_COMMAND", "작은 비밀정보 없는 텍스트만 허용됩니다.", 422)
        # Serialize the authority check and replacement with pause/change commands.
        with self.store.transaction() as db:
            authority, _ = self.authority(db)
            require(authority["role"] == "builder", "FORBIDDEN", "구현 역할만 파일을 수정할 수 있습니다.", 403)
            require(name in WRITABLE_FILES, "FORBIDDEN", "이 템플릿에서 수정 가능한 파일이 아닙니다.", 403)
            options = json.loads(authority["context"] or "{}").get("options", {})
            require(name in options.get("writable_files", WRITABLE_FILES), "FORBIDDEN", "현재 Sprint의 쓰기 범위 밖입니다.", 403)
            path = self.path(name, db)
            require(not path.exists() or path.stat().st_size <= 65536, "FORBIDDEN", "작은 파일만 수정할 수 있습니다.", 403)
            current = digest(path.read_text()) if path.exists() else None
            require(current == expected_digest, "VERSION_CONFLICT", "파일이 변경됐습니다. 다시 읽으세요.")
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as temp:
                temp.write(content)
                temporary = temp.name
            try:
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        return dict(path=name, content_digest=digest(content))
