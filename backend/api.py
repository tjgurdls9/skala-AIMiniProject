import asyncio
import hmac
import json
import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from jsonschema import ValidationError

from backend.config import Settings
from backend.contracts import DomainError, SCHEMAS, require, validate
from backend.store import Store
from runner.model import Ollama

SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,})")


def create_app(settings=None, store=None, model=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings.from_env()
        app.state.store = store or Store(app.state.settings.database)
        app.state.model = model or Ollama(app.state.settings.model, app.state.settings.ollama_url)
        yield

    async def authorize(request: Request):
        supplied = request.headers.get("authorization", "")
        require(hmac.compare_digest(supplied.encode(), ("Bearer " + request.app.state.settings.token).encode()),
                "UNAUTHORIZED", "운영자 인증이 필요합니다.", 401)

    app = FastAPI(title="Development lifecycle", version="0.1.0", lifespan=lifespan,
                  dependencies=[Depends(authorize)], docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def request_boundary(request, call_next):
        # Bound chunked bodies too; Content-Length alone is not a trust boundary.
        if request.method in ("POST", "PUT", "PATCH"):
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 131072:
                    return JSONResponse({"error": {"code": "BODY_TOO_LARGE", "message": "요청 크기 제한을 초과했습니다."}}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def malformed(request, exc):
        return JSONResponse({"error": {"code": "INVALID_COMMAND", "message": "요청 형식을 확인하세요."}}, status_code=422)

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
        import time
        ready = bool(row and time.time() - row[0] < 15)
        status = await request.app.state.model.status()
        value = dict(protocol_version=1, live_available=ready and status == "ready", provider="ollama_local",
                     model=request.app.state.settings.model or None, model_status=status,
                     runner_status="ready" if ready else "unavailable", inference_slots=1,
                     external_api_enabled=False, deployment_enabled=False, reasons=[])
        if not ready:
            value["reasons"].append("실행기 heartbeat가 없습니다.")
        if status != "ready":
            value["reasons"].append("명시적으로 설정한 로컬 Qwen/DeepSeek 모델이 필요합니다.")
        value["reasons"].append("현재 LIVE는 기획·승인까지 지원합니다. 생성 앱 구현·독립 검토·배포는 아직 비활성입니다.")
        validate("Runtime", value)
        return value

    @app.get("/api/runtime")
    async def get_runtime(request: Request):
        return await runtime(request)

    @app.get("/api/contracts/{name}")
    def contract(name: str):
        require(name in SCHEMAS, "NOT_FOUND", "계약을 찾을 수 없습니다.", 404)
        return SCHEMAS[name]

    @app.post("/api/projects", status_code=201)
    async def project(request: Request):
        value = request.app.state.store.project(await payload(request, "ProjectCreate"))
        validate("Project", value)
        return value

    @app.post("/api/projects/{project_id}/runs", status_code=201)
    async def run(project_id: str, request: Request):
        data = await payload(request, "RunCreate")
        if data["mode"] == "live":
            readiness = await runtime(request)
            require(readiness["live_available"], "RUNTIME_UNAVAILABLE", "모델과 실행기를 준비한 뒤 LIVE를 생성하세요.")
        return request.app.state.store.create_run(project_id, data)

    @app.get("/api/runs/{run_id}")
    def snapshot(run_id: str, request: Request):
        value = request.app.state.store.snapshot(run_id)
        validate("Snapshot", value)
        return value

    @app.post("/api/runs/{run_id}/commands", status_code=202)
    async def command(run_id: str, request: Request):
        value = request.app.state.store.command(run_id, await payload(request, "Command"))
        validate("CommandReceipt", value)
        return value

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request, after: int | None = None):
        header = request.headers.get("last-event-id")
        require(header is not None or after is not None, "CURSOR_INVALID", "스냅샷의 last_event_seq를 after로 지정하세요.", 422)
        try:
            cursor = int(header) if header is not None else after
        except ValueError:
            raise DomainError("CURSOR_INVALID", "올바른 이벤트 cursor가 필요합니다.", 422)
        store = request.app.state.store
        store.events(run_id, cursor)

        async def stream():
            nonlocal cursor
            idle = 0
            while not await request.is_disconnected():
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

    return app


app = create_app()
