"""SQLite extraction contract, raw values, and error handling."""

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from app.sources.database_source import DatabaseSourceError, extract_database
from app.utils.config_loader import load_config


ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["student_id", "course_name", "credit_hours", "semester", "score"]


def test_canonical_counts_join_and_unchanged_files():
    config = load_config()
    path = Path(config["sources"]["database"]["path"])
    files = [path, ROOT / "database/schema.sql", ROOT / "database/seed.sql"]
    before = [hashlib.sha256(file.read_bytes()).hexdigest() for file in files]

    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0] == 12

    result = extract_database(config)

    assert isinstance(result, pd.DataFrame)
    assert result.columns.tolist() == COLUMNS
    assert len(result) == 12
    assert result["student_id"].tolist() == list(range(1001, 1013))
    assert result["course_name"].tolist() == [
        "Data Engineering", "Database Systems",
        "Machine Learning", "Python Programming",
    ] * 3
    assert result["credit_hours"].tolist() == [3, 3, 4, 3] * 3
    assert result["semester"].tolist() == ["2026-Fall"] * 12
    assert result["score"].tolist() == [
        93, 88, 77, 91, 85, 79, 95, 67, 58, 105, 73, 89,
    ]
    assert result.loc[result["student_id"] == 1010, "score"].item() == 105
    assert [hashlib.sha256(file.read_bytes()).hexdigest() for file in files] == before


def test_default_config_works_outside_project_root(monkeypatch):
    monkeypatch.chdir(ROOT / "app")
    assert len(extract_database()) == 12


@pytest.fixture
def memory_database(monkeypatch):
    # Only this in-memory database is modified by tests.
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (ROOT / "database/schema.sql").read_text(encoding="utf-8")
    )
    connector = Mock(return_value=connection)
    monkeypatch.setattr("app.sources.database_source.sqlite3.connect", connector)
    yield connection, connector
    connection.close()


def test_custom_path_read_only_and_raw_values(memory_database):
    connection, connector = memory_database
    connection.execute("INSERT INTO courses VALUES (7, '  MiXeD Course  ', 3)")
    connection.executemany(
        "INSERT INTO enrollments VALUES (?, ?, ?, ?)",
        [(1010, 7, "  Fall  ", 105), (1010, 7, "  Fall  ", None)],
    )
    custom_path = ROOT / "database/custom # source.db"
    result = extract_database({"sources": {"database": {"path": str(custom_path)}}})

    connector.assert_called_once_with(
        custom_path.resolve().as_uri() + "?mode=ro", uri=True
    )
    assert result["student_id"].tolist() == [1010, 1010]
    assert result["course_name"].tolist() == ["  MiXeD Course  "] * 2
    assert result["semester"].tolist() == ["  Fall  "] * 2
    assert result["score"].dropna().tolist() == [105]
    assert result["score"].isna().sum() == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_empty_tables_preserve_columns(memory_database):
    result = extract_database()
    assert result.empty
    assert result.columns.tolist() == COLUMNS


def test_connection_failure_is_clear(monkeypatch):
    cause = sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(
        "app.sources.database_source.sqlite3.connect", Mock(side_effect=cause)
    )
    with pytest.raises(DatabaseSourceError, match="Cannot open SQLite database") as error:
        extract_database()
    assert error.value.__cause__ is cause
    assert load_config()["sources"]["database"]["path"] in str(error.value)


def test_query_failure_is_clear_and_connection_is_closed(memory_database):
    connection, _ = memory_database
    connection.execute("DROP TABLE enrollments")

    with pytest.raises(DatabaseSourceError, match="Cannot extract enrollments") as error:
        extract_database()

    assert isinstance(error.value.__cause__, sqlite3.OperationalError)
    assert "no such table: enrollments" in str(error.value)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


@pytest.mark.parametrize("config", [
    {}, {"sources": {}}, {"sources": {"database": {}}},
    {"sources": {"database": {"path": ""}}},
    {"sources": {"database": {"path": 123}}},
])
def test_invalid_configuration_is_clear(config):
    with pytest.raises(ValueError, match="sources.database.path"):
        extract_database(config)
