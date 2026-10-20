from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
DATABASE = Path("/data/app.sqlite3")


def connect():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL)")
    return db


class NewItem(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ChangeStatus(BaseModel):
    status: Literal["open", "done"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/items")
def items():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM items ORDER BY id")]


@app.post("/api/items", status_code=201)
def create_item(item: NewItem):
    with connect() as db:
        cursor = db.execute("INSERT INTO items (title,status) VALUES (?, 'open')", (item.title,))
        return {"id": cursor.lastrowid, "title": item.title, "status": "open"}


@app.patch("/api/items/{item_id}")
def change_status(item_id: int, change: ChangeStatus):
    with connect() as db:
        if db.execute("UPDATE items SET status=? WHERE id=?", (change.status, item_id)).rowcount == 0:
            raise HTTPException(404, "Not found")
        return dict(db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone())


app.mount("/assets", StaticFiles(directory="app_frontend"), name="assets")


@app.get("/")
def index():
    return FileResponse("app_frontend/index.html")
