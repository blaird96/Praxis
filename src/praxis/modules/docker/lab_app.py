"""Shared tiny HTTP app files for Docker labs."""

from __future__ import annotations

from pathlib import Path

APP_PY = '''\
from http.server import BaseHTTPRequestHandler, HTTPServer
import os

PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
'''

REQUIREMENTS = "\n"


def write_app(repo_path: Path) -> None:
    (repo_path / "app.py").write_text(APP_PY, encoding="utf-8")
    (repo_path / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")


def resource_prefix(repo_path: Path) -> str:
    """Deterministic docker name prefix from workspace session folder name."""
    session_id = repo_path.resolve().parent.name
    safe = "".join(ch if ch.isalnum() else "-" for ch in session_id)[:20]
    return f"praxis-{safe}"
