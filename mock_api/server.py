"""Lightweight mock REST API for canonical academic student records."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Type


DEFAULT_DATA_PATH = Path(__file__).with_name("students_academic.json")


def load_students(data_path: str | Path = DEFAULT_DATA_PATH) -> list[dict]:
    """Load the canonical academic student records served by the mock API."""
    with Path(data_path).open(encoding="utf-8") as data_file:
        data = json.load(data_file)

    if not isinstance(data, list):
        raise ValueError("Student seed data must be a JSON array.")

    return data


def make_handler(data_path: str | Path = DEFAULT_DATA_PATH) -> Type[BaseHTTPRequestHandler]:
    """Create a request handler bound to a specific seed data file."""

    class StudentAPIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/students":
                self.send_error(404, "Not Found")
                return

            try:
                payload = json.dumps(load_students(data_path)).encode("utf-8")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                self.send_error(500, f"Unable to load student records: {exc}")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return StudentAPIHandler


def create_server(
    host: str = "localhost",
    port: int = 8000,
    data_path: str | Path = DEFAULT_DATA_PATH,
) -> HTTPServer:
    """Create an HTTP server for tests or local development."""
    return HTTPServer((host, port), make_handler(data_path))


def main() -> None:
    server = create_server()
    print("Mock API serving GET /students at http://localhost:8000/students")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
