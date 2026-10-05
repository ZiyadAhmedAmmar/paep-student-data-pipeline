from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pandas as pd
import pytest
import requests

from app.sources.api_source import APISource, APISourceError
from mock_api.server import make_handler


class StaticResponseHandler(BaseHTTPRequestHandler):
    status_code = 200
    body = b"[]"
    content_type = "application/json"

    def do_GET(self) -> None:
        self.send_response(self.status_code)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def http_server():
    servers: list[HTTPServer] = []

    def start(handler_cls: type[BaseHTTPRequestHandler]) -> str:
        server = HTTPServer(("localhost", 0), handler_cls)
        servers.append(server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        return f"http://{host}:{port}/students"

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()


def test_extracts_canonical_dataset_through_real_http_request(http_server):
    url = http_server(make_handler())

    df = APISource({"url": url, "timeout_seconds": 2}).extract()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 13
    assert {"student_id", "gpa", "attendance", "status"}.issubset(df.columns)

    by_id = df.set_index("student_id")
    assert pd.isna(by_id.loc[1002, "gpa"])
    assert pd.isna(by_id.loc[1011, "attendance"])
    assert by_id.loc[1003, "attendance"] == 105
    assert by_id.loc[1004, "gpa"] == 4.5
    assert 1099 in by_id.index
    assert by_id.loc[1006, "status"] == " Active "
    assert by_id.loc[1002, "status"] == "active"


def test_extract_uses_config_mapping(http_server):
    url = http_server(make_handler())

    df = APISource({"url": url, "timeout_seconds": 2}).extract()

    assert len(df) == 13


def test_default_configuration_comes_from_shared_config():
    source = APISource()

    assert source.url == "http://localhost:8000/students"
    assert source.timeout_seconds == 5


@pytest.mark.parametrize(
    "config",
    [
        {"url": "", "timeout_seconds": 1},
        {"url": None, "timeout_seconds": 1},
        {"url": "http://localhost", "timeout_seconds": 0},
        {"url": "http://localhost", "timeout_seconds": -1},
        {"url": "http://localhost", "timeout_seconds": float("nan")},
        {"url": "http://localhost", "timeout_seconds": float("inf")},
        {"url": "http://localhost", "timeout_seconds": True},
    ],
)
def test_invalid_configuration_is_rejected(config):
    with pytest.raises(APISourceError):
        APISource(config)


def test_connection_error_is_reported(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr(requests, "get", raise_connection_error)
    source = APISource({"url": "http://localhost:1/students", "timeout_seconds": 0.1})

    with pytest.raises(APISourceError, match="connection"):
        source.extract()


def test_timeout_is_reported(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests, "get", raise_timeout)
    source = APISource({"url": "http://localhost/students", "timeout_seconds": 0.1})

    with pytest.raises(APISourceError, match="timed out"):
        source.extract()


def test_http_error_is_reported(http_server):
    class ErrorHandler(StaticResponseHandler):
        status_code = 500
        body = b'{"error": "failed"}'

    source = APISource({"url": http_server(ErrorHandler), "timeout_seconds": 2})

    with pytest.raises(APISourceError, match="HTTP error"):
        source.extract()


def test_invalid_json_is_reported(http_server):
    class InvalidJSONHandler(StaticResponseHandler):
        body = b"not-json"

    source = APISource({"url": http_server(InvalidJSONHandler), "timeout_seconds": 2})

    with pytest.raises(APISourceError, match="Invalid JSON"):
        source.extract()


@pytest.mark.parametrize("body", [b"", b"[]"])
def test_empty_response_is_reported(http_server, body):
    class EmptyHandler(StaticResponseHandler):
        pass

    EmptyHandler.body = body
    source = APISource({"url": http_server(EmptyHandler), "timeout_seconds": 2})

    with pytest.raises(APISourceError, match="empty"):
        source.extract()


def test_non_list_payload_is_reported(http_server):
    class ObjectHandler(StaticResponseHandler):
        body = json.dumps({"student_id": 1001}).encode("utf-8")

    source = APISource({"url": http_server(ObjectHandler), "timeout_seconds": 2})

    with pytest.raises(APISourceError, match="JSON array"):
        source.extract()


def test_each_record_must_contain_required_fields(http_server):
    class HeterogeneousHandler(StaticResponseHandler):
        body = json.dumps(
            [
                {"student_id": 1001, "gpa": 3.5, "attendance": 90, "status": "active"},
                {"student_id": 1002},
            ]
        ).encode("utf-8")

    source = APISource({"url": http_server(HeterogeneousHandler), "timeout_seconds": 2})

    with pytest.raises(APISourceError, match="record 1.*attendance.*gpa.*status"):
        source.extract()


def test_imported_api_logger_has_no_file_handler():
    api_logger = logging.getLogger("app.sources.api_source")

    assert not any(isinstance(handler, logging.FileHandler) for handler in api_logger.handlers)
