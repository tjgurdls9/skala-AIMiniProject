"""Synthetic trial fixture; not the product backend."""
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/healthz":
            self.send_error(404)
            return
        data_dir = Path(os.environ.get("DATA_DIR", "/data"))
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(data_dir / "trial.db") as connection:
                connection.execute("CREATE TABLE IF NOT EXISTS trial (value TEXT)")
                connection.execute("SELECT 1").fetchone()
        except (OSError, sqlite3.Error):
            status, payload = 503, {"status": "unavailable"}
        else:
            status, payload = 200, {"status": "ok", "fixture": True}
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
