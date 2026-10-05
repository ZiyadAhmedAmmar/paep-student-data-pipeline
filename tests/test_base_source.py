"""Common source contract and wrapper compatibility."""

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
import requests

from app.sources.api_source import APISource, extract_api_data
from app.sources.base_source import BaseSource
from app.sources.csv_source import CSVSource, load_data
from app.sources.database_source import DatabaseSource, extract_database


def test_base_source_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseSource()


def test_subclass_without_extract_is_still_abstract():
    class IncompleteSource(BaseSource):
        pass

    with pytest.raises(TypeError):
        IncompleteSource()


@pytest.mark.parametrize("source_cls", [CSVSource, APISource, DatabaseSource])
def test_concrete_sources_implement_base_source(source_cls):
    assert issubclass(source_cls, BaseSource)


def test_csv_source_contract_and_wrapper(tmp_path: Path):
    csv_path = tmp_path / "students.csv"
    csv_path.write_text("student_id\n1\n2\n", encoding="utf-8")

    df = CSVSource(csv_path).extract()

    assert isinstance(df, pd.DataFrame)
    pd.testing.assert_frame_equal(load_data(csv_path), df)


def test_api_source_contract_and_wrapper(monkeypatch):
    payload = [
        {"student_id": 1001, "gpa": 3.5, "attendance": 90, "status": "active"}
    ]

    class FakeResponse:
        content = json.dumps(payload).encode("utf-8")

        def raise_for_status(self):
            return None

        def json(self):
            return json.loads(self.content)

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    config = {"url": "http://localhost/students", "timeout_seconds": 1}

    df = APISource(config).extract()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    pd.testing.assert_frame_equal(extract_api_data(config), df)


def test_database_source_contract_and_wrapper(tmp_path: Path):
    db_path = tmp_path / "students.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE courses (
            course_id INTEGER PRIMARY KEY,
            course_name TEXT,
            credit_hours INTEGER
        );
        CREATE TABLE enrollments (
            student_id INTEGER,
            course_id INTEGER,
            semester TEXT,
            score INTEGER
        );
        INSERT INTO courses VALUES (1, 'Data Engineering', 3);
        INSERT INTO enrollments VALUES (1001, 1, '2026-Fall', 90);
        """
    )
    connection.commit()
    connection.close()
    config = {"sources": {"database": {"path": str(db_path)}}}

    df = DatabaseSource(config).extract()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    pd.testing.assert_frame_equal(extract_database(config), df)
