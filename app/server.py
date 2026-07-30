import hmac
import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .store import Store

STATIC = Path(__file__).parent / "static"
DATA_DIR = Path(os.getenv("CLIPHUB_DATA_DIR", "data"))
STORE = Store(DATA_DIR / "cliphub.db")
API_KEY = os.getenv("CLIPHUB_API_KEY", "")


class Handler(BaseHTTPRequestHandler):
    server_version = "ClipHub/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def json_response(self, data: object, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise ValueError("request body is too large")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def authorized(self) -> bool:
        if not API_KEY or hmac.compare_digest(self.headers.get("X-API-Key", ""), API_KEY):
            return True
        self.json_response({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
        return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.json_response({"status": "ok"})
            return
        if parsed.path.startswith("/api/"):
            if not self.authorized(): return
            params = parse_qs(parsed.query)
            if parsed.path == "/api/clips":
                self.json_response({"items": STORE.clips(params.get("q", [""])[0], params.get("archived", ["0"])[0] == "1")})
            elif parsed.path == "/api/prompts":
                self.json_response({"items": STORE.prompts()})
            else:
                self.json_response({"error": "not found"}, 404)
            return
        self.static_file(parsed.path)

    def do_POST(self) -> None:
        if not self.authorized(): return
        try:
            payload = self.body()
            if self.path == "/api/clips": result = STORE.add_clip(payload)
            elif self.path == "/api/prompts": result = STORE.add_prompt(payload)
            elif self.path == "/api/combine": result = {"content": STORE.combine(payload.get("ids", []), payload.get("mode", "plain"))}
            else:
                self.json_response({"error": "not found"}, 404); return
            self.json_response(result, HTTPStatus.CREATED)
        except (ValueError, json.JSONDecodeError) as error:
            self.json_response({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def do_PATCH(self) -> None:
        if not self.authorized(): return
        try:
            if not self.path.startswith("/api/clips/"): raise ValueError("not found")
            result = STORE.update_clip(int(self.path.rsplit("/", 1)[1]), self.body())
            self.json_response(result or {"error": "not found"}, 200 if result else 404)
        except (ValueError, json.JSONDecodeError) as error:
            self.json_response({"error": str(error)}, 400)

    def do_DELETE(self) -> None:
        if not self.authorized(): return
        try:
            deleted = STORE.delete_clip(int(self.path.rsplit("/", 1)[1]))
            self.json_response({"deleted": deleted}, 200 if deleted else 404)
        except ValueError:
            self.json_response({"error": "not found"}, 404)

    def static_file(self, path: str) -> None:
        relative = "index.html" if path == "/" else path.lstrip("/")
        candidate = (STATIC / relative).resolve()
        if STATIC.resolve() not in candidate.parents or not candidate.is_file():
            candidate = STATIC / "index.html"
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(candidate)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def run() -> None:
    host, port = os.getenv("CLIPHUB_HOST", "127.0.0.1"), int(os.getenv("CLIPHUB_PORT", "8080"))
    print(f"ClipHub listening on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    run()
