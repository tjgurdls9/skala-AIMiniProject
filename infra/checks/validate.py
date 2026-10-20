"""Protected HTTP checks; this file is never mounted in the candidate container."""
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

base, mode = sys.argv[1:3]

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

opener = build_opener(ProxyHandler({}), NoRedirect())


def request(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=3) as response:
            raw = response.read(65537)
            assert len(raw) <= 65536
            return response.status, json.loads(raw)
    except HTTPError as error:
        return error.code, None


results = {}
try:
    for attempt in range(50):
        try:
            status, health = request("/health")
            if status == 200:
                break
        except (URLError, OSError):
            pass
        time.sleep(0.1)
    results["health"] = status == 200 and health == {"status": "ok"}
    if mode == "persist":
        status, items = request("/api/items")
        results["persistent_storage"] = status == 200 and any(str(item["id"]) == sys.argv[3] and item["status"] == "done" for item in items)
    else:
        title = "protected-" + uuid4().hex
        status, item = request("/api/items", "POST", {"title": title})
        results["create"] = status == 201 and item["title"] == title and item["status"] == "open"
        item_id = item["id"]
        status, items = request("/api/items")
        results["list"] = status == 200 and item in items
        status, changed = request("/api/items/" + str(item_id), "PATCH", {"status": "done"})
        results["update"] = status == 200 and changed["status"] == "done"
        results["invalid_input"] = request("/api/items", "POST", {"title": ""})[0] == 422
except Exception:
    results["tool_error"] = False
print(json.dumps({"checks": results, "item_id": locals().get("item_id"), "pass": bool(results) and all(results.values())}))
