from __future__ import annotations

import json

import pandas as pd
import pytest

from app.sources.web_scraping_source import (
	WebScrapingSource,
	WebScrapingSourceError,
)
from web_scraping_pipeline import run_pipeline


HTML = """
<html><body>
<table><thead><tr><th>Student</th><th>GPA</th></tr></thead>
<tbody><tr><td>1001</td><td>3.5</td></tr></tbody></table>
<table><thead><tr><th>Student</th><th>Score</th></tr></thead>
<tbody><tr><td>1002</td><td>90</td></tr></tbody></table>
</body></html>
"""


class _FakeResponse:
	text = HTML

	def raise_for_status(self):
		return None


def test_source_reads_selected_table_and_renames_columns(monkeypatch):
	monkeypatch.setattr(
		"app.sources.web_scraping_source.requests.get",
		lambda *args, **kwargs: _FakeResponse(),
	)
	source = WebScrapingSource(
		{
			"url": "https://example.test/students",
			"table_index": 1,
			"column_mapping": {"Student": "student_id"},
		}
	)

	result = source.extract()

	assert result.to_dict("records") == [{"student_id": "1002", "Score": "90"}]


def test_source_reports_missing_table_index(monkeypatch):
	monkeypatch.setattr(
		"app.sources.web_scraping_source.requests.get",
		lambda *args, **kwargs: _FakeResponse(),
	)

	with pytest.raises(WebScrapingSourceError, match="table index 2"):
		WebScrapingSource({"url": "https://example.test", "table_index": 2}).extract()


def test_separate_pipeline_cleans_transforms_and_writes_its_own_output(
	tmp_path, monkeypatch
):
	monkeypatch.setattr(
		"app.sources.web_scraping_source.requests.get",
		lambda *args, **kwargs: _FakeResponse(),
	)
	config = {
		"sources": {
			"csv": {"path": "students.csv"},
			"api": {"url": "http://localhost/students", "timeout_seconds": 1},
			"database": {"path": "students.db"},
		},
		"output": {"processed": "old-output.csv", "rejected": "rejected.csv"},
		"logging": {"path": "old-pipeline.log"},
		"incremental": {"enabled": False, "state_path": "state.json"},
		"scraping": {
			"url": "https://example.test/students",
			"table_index": 0,
			"column_mapping": {"Student": "student_id", "GPA": "gpa"},
			"required_columns": ["student_id", "gpa"],
			"output": "scraped/separate.csv",
			"logging_path": "scraped/pipeline.log",
		},
	}
	config_path = tmp_path / "config.json"
	config_path.write_text(json.dumps(config), encoding="utf-8")

	result = run_pipeline(config_path)

	assert result["student_id"].tolist() == [1001]
	assert result.loc[0, "performance_level"] == "Excellent"
	assert (tmp_path / "scraped" / "separate.csv").exists()
	assert not (tmp_path / "old-output.csv").exists()