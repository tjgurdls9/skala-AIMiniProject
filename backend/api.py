import asyncio
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from jsonschema import ValidationError
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from backend.config import Settings
from backend.archive import MAX_BYTES, export_recording, import_recording, unique_object
from backend.contracts import ROOT, DomainError, SCHEMAS, SECRET, require, validate
from backend.store import Store
from runner.model import Ollama

ORIGINS = {"http://127.0.0.1:5173", "http://127.0.0.1:8000"}
COOKIE = "lifecycle_session"


def allowed_origin(request):
    return request.headers.get("origin") in ORIGINS | {str(request.base_url).rstrip("/")}


def cookie_name(request):
    port = request.url.port
    return COOKIE if port in (None, 8000, 5173) else f"{COOKIE}_{port}"


def create_app(settings=None, store=None, model=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings.from_env()
        app.state.store = store or Store(app.state.settings.database)
        app.state.model = model or Ollama(app.state.settings.model, app.state.settings.ollama_url)
        app.state.sessions = {}
        yield

    async def authorize(request: Request):
        if request.url.path == "/api/session" and request.method == "POST":
            return
        supplied = request.headers.get("authorization", "")
        if hmac.compare_digest(supplied.encode(), ("Bearer " + request.app.state.settings.token).encode()):
            return
        key = hashlib.sha256(request.cookies.get(cookie_name(request), "").encode()).hexdigest()
        session = request.app.state.sessions.get(key)
        require(session is not None and session["expires"] > time.time(),
                "UNAUTHORIZED", "로컬 세션을 연결하세요.", 401)
        request.state.session_key = key
        request.state.session = session
        if request.method not in ("GET", "HEAD"):
            require(allowed_origin(request) and
                    hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), session["csrf_token"].encode()),
                    "FORBIDDEN", "같은 origin의 CSRF 토큰이 필요합니다.", 403)

    app = FastAPI(title="Development lifecycle", version="0.1.0", lifespan=lifespan,
                  dependencies=[Depends(authorize)], docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def request_boundary(request, call_next):
        if (not request.client or request.client.host not in ("127.0.0.1", "::1") or
                request.url.hostname not in ("127.0.0.1", "localhost") or
                (request.headers.get("origin") is not None and not allowed_origin(request))):
            return JSONResponse({"error": {"code": "FORBIDDEN", "message": "로컬 origin에서만 접근할 수 있습니다."}}, status_code=403)
        # Bound chunked bodies too; Content-Length alone is not a trust boundary.
        if request.method in ("POST", "PUT", "PATCH"):
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                limit = MAX_BYTES if request.url.path == "/api/recordings/import" else 131072
                if len(body) > limit:
                    return JSONResponse({"error": {"code": "BODY_TOO_LARGE", "message": "요청 크기 제한을 초과했습니다."}}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        value = {"error": {"code": exc.code, "message": exc.message}}
        if exc.current_state_version is not None:
            value["error"]["current_state_version"] = exc.current_state_version
        validate("Error", value)
        return JSONResponse(value, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def malformed(request, exc):
        return JSONResponse({"error": {"code": "INVALID_COMMAND", "message": "요청 형식을 확인하세요."}}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"error": {"code": "NOT_FOUND" if exc.status_code == 404 else "INVALID_COMMAND",
                                       "message": "지원하는 API 경로와 메서드를 확인하세요."}}, status_code=exc.status_code)

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request, exc):
        return JSONResponse({"error": {"code": "TEMPORARILY_UNAVAILABLE", "message": "저장소를 확인한 뒤 다시 연결하세요."}}, status_code=503)

    async def payload(request, name):
        try:
            data = await request.json()
            validate(name, data)
        except (ValueError, ValidationError):
            raise DomainError("INVALID_COMMAND", "계약에 맞는 JSON 요청이 필요합니다.", 422)
        require(not SECRET.search(json.dumps(data)), "INVALID_COMMAND", "비밀정보를 요청에 넣지 마세요.", 422)
        return data

    async def runtime(request):
        db = request.app.state.store
        with db.transaction() as connection:
            row = connection.execute("SELECT updated_at FROM worker_heartbeat WHERE id=1").fetchone()
            lock = connection.execute("SELECT expires FROM worker_lock WHERE id=1").fetchone()
        ready = bool(row and lock and 0 <= time.time() - row[0] < 10 and lock[0] > time.time())
        status = await request.app.state.model.status()
        value = dict(protocol_version=1, live_available=ready and status == "ready", provider="ollama_local",
                     model=request.app.state.settings.model or None, model_status=status,
                     runner_status="ready" if ready else "unavailable", inference_slots=1,
                     external_api_enabled=False, deployment_enabled=False, reasons=[])
        value.update(template_id=request.app.state.settings.template_id, data_source_status="not_required")
        if not ready:
            value["reasons"].append("실행기 heartbeat가 없습니다.")
        if status != "ready":
            value["reasons"].append("명시적으로 설정한 로컬 Qwen/DeepSeek 모델이 필요합니다.")
        value["reasons"].append(f"시작 프로젝트는 비어 있는 {value['template_id']}이며 앱 코드는 로컬 모델이 작성합니다. 격리 이미지·취약점 DB 준비가 필요하며 실제 배포는 비활성입니다.")
        validate("Runtime", value)
        return value

    @app.post("/api/session", status_code=201)
    async def open_session(request: Request, response: Response):
        require(allowed_origin(request), "FORBIDDEN", "로컬 origin이 필요합니다.", 403)
        sessions = request.app.state.sessions
        for key in list(sessions):
            if sessions[key]["expires"] <= time.time():
                del sessions[key]
        token, expires = secrets.token_urlsafe(32), time.time() + 8 * 3600
        value = {"csrf_token": secrets.token_urlsafe(32), "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat()}
        sessions[hashlib.sha256(token.encode()).hexdigest()] = {**value, "expires": expires}
        response.set_cookie(cookie_name(request), token, httponly=True, samesite="strict", max_age=8 * 3600, path="/api")
        validate("Session", value)
        return value

    @app.get("/api/session")
    def session(request: Request):
        require(hasattr(request.state, "session"), "FORBIDDEN", "브라우저 세션이 필요합니다.", 403)
        return {k: request.state.session[k] for k in ("csrf_token", "expires_at")}

    @app.delete("/api/session", status_code=204)
    def close_session(request: Request, response: Response):
        require(hasattr(request.state, "session_key"), "FORBIDDEN", "브라우저 세션이 필요합니다.", 403)
        del request.app.state.sessions[request.state.session_key]
        response.delete_cookie(cookie_name(request), path="/api")

    @app.get("/api/replays")
    def replays(request: Request):
        value = request.app.state.store.replay_recordings()
        validate("ReplayRecordings", value)
        return value

    @app.get("/api/environments/{environment_id}")
    def environment(environment_id: str):
        raise DomainError("NOT_FOUND", "설정된 배포 환경이 없습니다.", 404)

    @app.get("/api/runs/{run_id}/recording")
    def recording(run_id: str, request: Request):
        return export_recording(request.app.state.store.path, run_id)

    @app.post("/api/recordings/import")
    async def import_archive(request: Request):
        try:
            bundle = json.loads(await request.body(), object_pairs_hook=unique_object,
                                parse_constant=lambda _: require(False, "INVALID_COMMAND", "유한 JSON 값이 필요합니다.", 422))
            return await asyncio.to_thread(import_recording, request.app.state.store, bundle)
        except (ValueError, ValidationError, RecursionError):
            raise DomainError("INVALID_COMMAND", "계약에 맞는 기록 JSON이 필요합니다.", 422)

    @app.get("/api/runtime")
    async def get_runtime(request: Request):
        return await runtime(request)

    @app.get("/api/contracts/{name}")
    def contract(name: str):
        require(name in SCHEMAS, "NOT_FOUND", "계약을 찾을 수 없습니다.", 404)
        return SCHEMAS[name]

    @app.post("/api/projects", status_code=201)
    async def project(request: Request):
        value = await asyncio.to_thread(request.app.state.store.project, await payload(request, "ProjectCreate"))
        validate("Project", value)
        return value

    @app.post("/api/projects/{project_id}/runs", status_code=201)
    async def run(project_id: str, request: Request):
        data = await payload(request, "RunCreate")
        if data["mode"] == "live":
            readiness = await runtime(request)
            require(readiness["live_available"], "RUNTIME_UNAVAILABLE", "모델과 실행기를 준비한 뒤 LIVE를 생성하세요.")
        value = await asyncio.to_thread(request.app.state.store.create_run, project_id, data, request.app.state.settings.template_id)
        validate("Run", value)
        return value

    @app.get("/api/runs/{run_id}")
    def snapshot(run_id: str, request: Request):
        value = request.app.state.store.snapshot(run_id)
        validate("Snapshot", value)
        return value

    @app.post("/api/runs/{run_id}/commands", status_code=202)
    async def command(run_id: str, request: Request):
        value = await asyncio.to_thread(request.app.state.store.command, run_id, await payload(request, "Command"))
        validate("CommandReceipt", value)
        return value

    @app.get("/api/runs/{run_id}/acceptance")
    def acceptance(run_id: str, request: Request):
        value = request.app.state.store.acceptance_status(run_id)
        validate("AcceptanceStatus", value)
        return value

    @app.get("/api/runs/{run_id}/release")
    def release_view(run_id: str, request: Request):
        value = request.app.state.store.release_view(run_id)
        validate("ReleaseView", value)
        return value

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request, after: str | None = None):
        header = request.headers.get("last-event-id")
        require(header is not None or after is not None, "CURSOR_INVALID", "스냅샷의 last_event_seq를 after로 지정하세요.", 422)
        raw = header if header is not None else after
        require(bool(re.fullmatch(r"[0-9]{1,16}", raw)), "CURSOR_INVALID", "올바른 이벤트 cursor가 필요합니다.", 422)
        cursor = int(raw)
        store = request.app.state.store
        try:
            await asyncio.to_thread(store.events, run_id, cursor)
        except DomainError as exc:
            if exc.code != "CURSOR_INVALID":
                raise
            return StreamingResponse(iter(['event: resync\ndata: {"reason":"cursor_out_of_range"}\n\n']), media_type="text/event-stream")

        async def stream():
            nonlocal cursor
            idle = 0
            while not await request.is_disconnected():
                if hasattr(request.state, "session") and (request.state.session_key not in request.app.state.sessions or
                        request.state.session["expires"] <= time.time()):
                    break
                batch = await asyncio.to_thread(store.events, run_id, cursor)
                for event in batch:
                    cursor = event["seq"]
                    yield f"id: {cursor}\nevent: lifecycle\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if batch:
                    idle = 0
                    continue
                idle += 1
                if idle >= 15:
                    yield ": heartbeat\n\n"
                    idle = 0
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.get("/api/artifacts/{artifact_id}")
    def artifact(artifact_id: str, request: Request):
        return request.app.state.store.read_artifact(artifact_id)

    if (ROOT / "frontend/dist/index.html").is_file():
        app.mount("/", StaticFiles(directory=ROOT / "frontend/dist", html=True), name="office")
    return app


app = create_app()
