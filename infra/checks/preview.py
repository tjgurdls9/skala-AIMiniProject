"""Trusted preview proxy applies headers the generated app cannot remove."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

target = "http://" + sys.argv[1]

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

opener = build_opener(ProxyHandler({}), NoRedirect())


class Proxy(BaseHTTPRequestHandler):
    def end_headers(self):
        # The iframe has an opaque origin; no credentials or parent cookies are allowed.
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def handle_request(self):
        if not self.path.startswith("/") or self.path.startswith("//"):
            self.send_error(400)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if self.headers.get("Transfer-Encoding"):
            self.send_error(400)
            return
        if not 0 <= length <= 131072:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else None
        request = Request(target + self.path, data=body, method=self.command,
                          headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
        try:
            response = opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        except OSError:
            self.send_error(502)
            return
        with response:
            payload = response.read(2 * 1024 * 1024 + 1)
            if len(payload) > 2 * 1024 * 1024:
                self.send_error(502)
                return
            self.send_response(response.status)
            self.send_header("Content-Type", response.headers.get("Content-Type", "application/octet-stream"))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors http://127.0.0.1:5173 http://127.0.0.1:8000")
            self.end_headers()
            self.wfile.write(payload)

    do_GET = do_POST = do_PATCH = handle_request

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("0.0.0.0", 8081), Proxy).serve_forever()
