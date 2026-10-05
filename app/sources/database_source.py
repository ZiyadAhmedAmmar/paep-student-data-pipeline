"""Extract raw academic enrollment data from SQLite."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from app.sources.base_source import BaseSource
from app.utils.config_loader import load_config


_QUERY = """
SELECT e.student_id, c.course_name, c.credit_hours, e.semester, e.score
FROM enrollments AS e
JOIN courses AS c ON c.course_id = e.course_id
ORDER BY e.student_id;
"""


class DatabaseSourceError(RuntimeError):
    """SQLite connection or extraction failure."""


class DatabaseSource(BaseSource):
    """Extract raw enrollments from a configured SQLite database."""

    def __init__(self, config: dict | None = None) -> None:
        if config is None:
            config = load_config()

        try:
            raw_path = config["sources"]["database"]["path"]
        except (KeyError, TypeError) as exc:
            raise ValueError("Missing configuration: sources.database.path") from exc

        if not isinstance(raw_path, (str, Path)) or not str(raw_path).strip():
            raise ValueError("sources.database.path must be a non-empty path")

        self.path = Path(raw_path).resolve()

    def extract(self) -> pd.DataFrame:
        path = self.path
        try:
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise DatabaseSourceError(
                f"Cannot open SQLite database '{path}': {exc}"
            ) from exc

        with closing(connection):
            try:
                cursor = connection.execute(_QUERY)
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()
            except sqlite3.Error as exc:
                raise DatabaseSourceError(
                    f"Cannot extract enrollments from SQLite database '{path}': {exc}"
                ) from exc

        return pd.DataFrame.from_records(rows, columns=columns)


def extract_database(config: dict | None = None) -> pd.DataFrame:
    """Return raw enrollments without validation or cleaning.

    Pass configuration returned by load_config(), or omit it to load the default.
    Relative paths supplied directly are relative to the working directory.
    The connection is read-only and is always closed.
    """
    return DatabaseSource(config).extract()
