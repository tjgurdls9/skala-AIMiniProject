from pathlib import Path
import sqlite3

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
DATABASE = Path("/data/app.sqlite3")


def connect():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS preferences (id INTEGER PRIMARY KEY CHECK(id=1), radius_m INTEGER NOT NULL, internet_only INTEGER NOT NULL)")
    return db


class Preferences(BaseModel):
    model_config = {"extra": "forbid"}
    radius_m: int = Field(default=1500, ge=100, le=5000)
    internet_only: bool = False


class Search(Preferences):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    query: str = Field(default="", max_length=120)
    external_consent: bool = False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/map/source")
def source():
    return {"status": "unconfigured", "provider": None, "external_requests": False,
            "message": "외부 지도·장소 연결은 결정 보류입니다. 실제 검색/추천 결과가 없습니다."}


@app.post("/api/map/search")
def search(request: Search):
    return JSONResponse({"error": {"code": "PROVIDER_UNCONFIGURED", "message": "지도·장소 공급자가 미설정입니다. 위치/검색어를 외부로 전송하지 않았습니다."}}, status_code=503)


@app.get("/api/preferences")
def preferences():
    db = connect()
    try:
        row = db.execute("SELECT radius_m,internet_only FROM preferences WHERE id=1").fetchone()
        return dict(radius_m=row["radius_m"], internet_only=bool(row["internet_only"])) if row else Preferences().model_dump()
    finally:
        db.close()


@app.post("/api/preferences")
def save_preferences(value: Preferences):
    db = connect()
    try:
        with db:
            db.execute("INSERT INTO preferences VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET radius_m=excluded.radius_m,internet_only=excluded.internet_only", (value.radius_m, int(value.internet_only)))
        return value.model_dump()
    finally:
        db.close()


app.mount("/assets", StaticFiles(directory="app_frontend"), name="assets")


@app.get("/")
def index():
    return FileResponse("app_frontend/index.html")
