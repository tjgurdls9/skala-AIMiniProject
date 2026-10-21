"""One HTTP request against the candidate app; prints {"status", "body"} or {"error"} as JSON and always exits 0.
This file is never mounted in the candidate container. Usage: http_probe.py <base> <METHOD> </path> [json-body]"""
import json
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
READ_LIMIT, TEXT_LIMIT, TIMEOUT = 65536, 4096, 5


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def body_of(raw):
    if len(raw) <= READ_LIMIT:
        try:
            return json.loads(raw)
        except ValueError:
            pass
    return {"_text": raw[:TEXT_LIMIT].decode(errors="replace")}


def main(base, method, path, body=None):
    if method not in METHODS or not path.startswith("/"):
        return {"error": "허용되지 않은 메서드나 경로입니다."}
    request = Request(base + path, data=body.encode() if body is not None else None, method=method, headers={"Content-Type": "application/json"})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=TIMEOUT) as response:
            return {"status": response.status, "body": body_of(response.read(READ_LIMIT + 1))}
    except HTTPError as error:
        return {"status": error.code, "body": body_of(error.read(READ_LIMIT + 1))}
    except Exception as error:  # noqa: BLE001 - a refused connection or timeout is the result, reported without a stack trace
        return {"error": type(error).__name__ + ": " + str(error)[:200]}


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:5])))
