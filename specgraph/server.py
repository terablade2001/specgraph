"""Local editor server. Standard library only.

Safety: listens on 127.0.0.1 only; every API call needs a random per-run token
(so other web pages cannot call it); the Host header must be local (blocks DNS
rebinding); only whitelisted static files are served.
"""
import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import TOOL_NAME, VERSION, DEFAULT_UNDO
from . import gitio, history as H, model as M, ops as O, query as Q
from .store import StoreError

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/favicon.svg": ("favicon.svg", "image/svg+xml")}
MAX_BODY = 5 * 1024 * 1024
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors 'none'")


def make_handler(store, token):
    write_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "%s/%s" % (TOOL_NAME, VERSION)

        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            self.wfile.write(body)

        def _local(self):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost")

        def _authorized(self):
            given = self.headers.get("X-%s-Token" % TOOL_NAME, "")
            return secrets.compare_digest(given.encode("utf-8", "replace"), token.encode())

        def _state(self):
            return store.state()

        def do_GET(self):
            url = urlparse(self.path)
            if not self._local():
                return self._send(403, {"error": "forbidden host"})
            if url.path in STATIC:
                name, ctype = STATIC[url.path]
                with open(os.path.join(WEB, name), "rb") as fh:
                    return self._send(200, fh.read(), ctype)
            if url.path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if not url.path.startswith("/api/"):
                return self._send(404, {"error": "not found"})
            if not self._authorized():
                return self._send(401, {"error": "missing or wrong token; start the tool again and use the link it prints"})
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                self._send(200, self._get(url.path, q))
            except StoreError as exc:
                self._send(409, {"error": str(exc), "code": exc.code})
            except (KeyError, ValueError) as exc:
                self._send(400, {"error": "bad request: %s" % exc})

        def _get(self, path, q):
            if path == "/api/state":
                return self._state()
            model = store.load()
            if path == "/api/head":
                return {"head": (model.get("stamp") or {}).get("id")}
            if path == "/api/ops":
                return {name: fn.doc for name, fn in O.OPS.items()}
            if path == "/api/search":
                return Q.search(model, q.get("q", ""), q.get("stereotype") or None, q.get("status") or None,
                                q.get("folder") or None, q.get("unused") == "1")
            if path in ("/api/usage", "/api/trace", "/api/history") and q.get("id") not in model["elements"]:
                raise ValueError("unknown element")
            if path == "/api/usage":
                return Q.usage(model, q["id"])
            if path == "/api/trace":
                return Q.trace(model, q["id"], int(q["depth"]) if q.get("depth") else None)
            if path == "/api/history":
                return H.element_history(store, q["id"])
            if path == "/api/matrix":
                return Q.matrix(model, q["rows"], q["cols"], q["types"].split(",") if q.get("types") else None)
            if path == "/api/config-usage":
                return O.config_usage(model, q["kind"], q["key"])
            raise ValueError("unknown endpoint")

        def do_POST(self):
            url = urlparse(self.path)
            if not self._local():
                return self._send(403, {"error": "forbidden host"})
            if not self._authorized():
                return self._send(401, {"error": "missing or wrong token"})
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                return self._send(415, {"error": "JSON only"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                return self._send(413, {"error": "request too large"})
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("expected an object")
            except ValueError as exc:
                return self._send(400, {"error": "bad JSON: %s" % exc})
            try:
                with write_lock:
                    if url.path == "/api/ops":
                        ops = body.get("ops")
                        if body.get("confirmed") is not True and isinstance(ops, list) and any(
                                isinstance(o, dict) and o.get("op") == "element.delete" for o in ops):
                            raise StoreError("deleting an element from the model must be confirmed", "confirm")
                        if body.get("confirmed") is not True and store.foreign_unlocks(store.load(), ops):
                            raise StoreError("unlocking another user's lock must be confirmed", "confirm")
                        _, results = store.apply(ops, body.get("base"))
                    elif url.path == "/api/undo":
                        store.undo(body.get("base"))
                        results = []
                    elif url.path == "/api/adopt":
                        store.adopt()
                        results = []
                    else:
                        return self._send(404, {"error": "not found"})
                self._send(200, dict(self._state(), results=results))
            except StoreError as exc:
                self._send(409, {"error": str(exc), "code": exc.code})
            except (M.ModelError, gitio.GitError) as exc:
                self._send(409, {"error": str(exc), "code": "rejected"})

    return Handler


def start(store, port=8765, token=None):
    """Start the server; returns (httpd, url). Tries a few ports."""
    token = token or secrets.token_urlsafe(24)
    last = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), make_handler(store, token))
            httpd.daemon_threads = True
            return httpd, "http://127.0.0.1:%d/#t=%s" % (p, token)
        except OSError as exc:
            last = exc
    raise StoreError("no free port: %s" % last)


def serve(store, port=8765, open_browser=True, undo=DEFAULT_UNDO):
    if not store.exists():
        raise StoreError("%s does not exist; run the 'init' command first" % store.path)
    store.prove_identity()  # no private key, no editor
    store.undo_steps = max(0, min(undo, 1000))
    httpd, url = start(store, port)
    print("%s editor running. Open:\n  %s\nPress Ctrl+C to stop." % (TOOL_NAME, url))
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
