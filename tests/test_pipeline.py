"""End-to-end orchestration tests for main().

Each test builds an isolated environment under tmp_path (config, CSV copy,
SQLite database, localhost HTTP API fixture) so no project outputs or
canonical raw files are touched and no external internet is required.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import Counter
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import main as main_module
from main import FINAL_COLUMNS, main

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "database" / "schema.sql"
SEED_PATH = REPO_ROOT / "database" / "seed.sql"
API_DATA_PATH = REPO_ROOT / "mock_api" / "students_academic.json"
CANONICAL_CSV_PATH = REPO_ROOT / "data" / "raw" / "students.csv"

EXPECTED_VALID_IDS = [1001, 1002, 1006, 1007, 1008, 1009, 1011, 1012]
EXPECTED_REJECTION_REASONS = Counter(
	{
		"Invalid Age": 1,
		"Missing student_id": 1,
		"Invalid Attendance": 1,
		"Invalid GPA": 1,
		"Incompatible student_id": 1,
		"Invalid Score": 1,
	}
)
EXPECTED_REJECTIONS_BY_ID = {
	1005: "Invalid Age",
	1003: "Invalid Attendance",
	1004: "Invalid GPA",
	1099: "Incompatible student_id",
	1010: "Invalid Score",
}


@pytest.fixture
def api_server():
	"""Start localhost HTTP servers serving a JSON fixture file."""
	servers: list[HTTPServer] = []

	def start(data_path: Path) -> str:
		class StudentAPIHandler(BaseHTTPRequestHandler):
			def do_GET(self) -> None:
				if self.path != "/students":
					self.send_error(404, "Not Found")
					return
				payload = data_path.read_bytes()
				self.send_response(200)
				self.send_header("Content-Type", "application/json")
				self.send_header("Content-Length", str(len(payload)))
				self.end_headers()
				self.wfile.write(payload)

			def log_message(self, format: str, *args: object) -> None:
				return

		server = HTTPServer(("localhost", 0), StudentAPIHandler)
		servers.append(server)
		thread = threading.Thread(target=server.serve_forever, daemon=True)
		thread.start()
		host, port = server.server_address
		return f"http://{host}:{port}/students"

	yield start

	for server in servers:
		server.shutdown()
		server.server_close()


@pytest.fixture
def pipeline_env(tmp_path, api_server):
	"""Build an isolated pipeline environment with canonical fixture data."""
	api_url = api_server(API_DATA_PATH)

	csv_path = tmp_path / "raw" / "students.csv"
	csv_path.parent.mkdir(parents=True)
	csv_path.write_text(CANONICAL_CSV_PATH.read_text(encoding="utf-8"), encoding="utf-8")

	db_path = tmp_path / "students.db"
	with closing(sqlite3.connect(db_path)) as connection:
		connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
		connection.executescript(SEED_PATH.read_text(encoding="utf-8"))
		connection.commit()

	paths = SimpleNamespace(
		processed=tmp_path / "processed" / "final_dataset.csv",
		rejected=tmp_path / "rejected" / "rejected_records.csv",
		log=tmp_path / "logs" / "pipeline.log",
		state=tmp_path / "state" / "pipeline_state.json",
	)

	def make_config(**overrides) -> Path:
		config = {
			"sources": {
				"csv": {"path": str(csv_path)},
				"api": {
					"url": overrides.pop("api_url", api_url),
					"timeout_seconds": 5,
				},
				"database": {"path": str(db_path)},
			},
			"output": {
				"processed": str(overrides.pop("processed", paths.processed)),
				"rejected": str(overrides.pop("rejected", paths.rejected)),
			},
			"logging": {"path": str(paths.log)},
			"incremental": {
				"enabled": overrides.pop("incremental_enabled", True),
				"state_path": str(paths.state),
			},
		}
		config_path = tmp_path / "config.json"
		config_path.write_text(json.dumps(config), encoding="utf-8")
		return config_path

	return SimpleNamespace(
		csv_path=csv_path,
		db_path=db_path,
		paths=paths,
		make_config=make_config,
	)


def _read_final(paths) -> pd.DataFrame:
	return pd.read_csv(paths.processed)


def _read_rejected(paths) -> pd.DataFrame:
	return pd.read_csv(paths.rejected)


def _read_state(paths) -> dict:
	return json.loads(paths.state.read_text(encoding="utf-8"))


def _run_sql(db_path: Path, statement: str) -> None:
	with closing(sqlite3.connect(db_path)) as connection:
		connection.execute(statement)
		connection.commit()


def test_first_run_creates_outputs_with_canonical_valid_records(pipeline_env):
	main(pipeline_env.make_config())

	assert pipeline_env.paths.processed.exists()
	assert pipeline_env.paths.rejected.exists()
	assert pipeline_env.paths.log.exists()
	assert pipeline_env.paths.state.exists()

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	assert list(final.columns) == FINAL_COLUMNS
	assert final["source"].eq("CSV|API|DATABASE").all()

	student_1002 = final.loc[final["student_id"] == 1002].iloc[0]
	assert student_1002["gpa"] == pytest.approx(3.0)
	student_1011 = final.loc[final["student_id"] == 1011].iloc[0]
	assert student_1011["attendance"] == pytest.approx(85)

	student_1006 = final.loc[final["student_id"] == 1006].iloc[0]
	assert student_1006["major"] == "Unknown"
	assert final.loc[final["student_id"] == 1007].shape[0] == 1


def test_mongodb_backend_uses_database_stage_and_preserves_pipeline_results(
	pipeline_env, monkeypatch
):
	config_path = pipeline_env.make_config()
	config = json.loads(config_path.read_text(encoding="utf-8"))
	config["sources"]["database"]["backend"] = "mongodb"
	config_path.write_text(json.dumps(config), encoding="utf-8")
	read_sqlite = main_module.extract_database
	monkeypatch.setattr(
		main_module,
		"extract_mongodb",
		lambda current_config: read_sqlite(current_config),
	)
	monkeypatch.setattr(
		main_module,
		"extract_database",
		lambda _: pytest.fail("SQLite must not be selected for MongoDB backend."),
	)

	main(config_path)

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	assert final["source"].eq("CSV|API|DATABASE").all()


def test_first_run_rejected_records_match_canonical_contract(pipeline_env):
	main(pipeline_env.make_config())

	rejected = _read_rejected(pipeline_env.paths)
	assert list(rejected.columns) == ["student_id", "source", "stage", "error_reason"]
	assert len(rejected) == 6
	assert Counter(rejected["error_reason"]) == EXPECTED_REJECTION_REASONS
	assert (rejected["stage"] == "SOURCE_VALIDATION").all()

	missing_id_rows = rejected.loc[rejected["student_id"].isna()]
	assert len(missing_id_rows) == 1
	assert missing_id_rows.iloc[0]["error_reason"] == "Missing student_id"
	assert missing_id_rows.iloc[0]["source"] == "CSV"

	expected_sources = {1005: "CSV", 1003: "API", 1004: "API", 1099: "API", 1010: "DATABASE"}
	known = rejected.loc[rejected["student_id"].notna()]
	for row in known.itertuples():
		assert row.error_reason == EXPECTED_REJECTIONS_BY_ID[int(row.student_id)]
		assert row.source == expected_sources[int(row.student_id)]


def test_first_run_logs_canonical_metrics_summary(pipeline_env):
	main(pipeline_env.make_config())

	log_text = pipeline_env.paths.log.read_text(encoding="utf-8")
	for line in (
		"Pipeline started.",
		"Pipeline completed.",
		"CSV Records : 14",
		"API Records : 13",
		"Database Records : 12",
		"Integrated Records : 8",
		"Valid Records : 8",
		"Rejected Records : 6",
		"Duplicate Records : 1",
		"Missing Values : 4",
		"Processing Time :",
	):
		assert line in log_text


def test_second_unchanged_run_keeps_complete_snapshot(pipeline_env):
	config_path = pipeline_env.make_config()
	main(config_path)
	first_final = _read_final(pipeline_env.paths)

	main(config_path)
	second_final = _read_final(pipeline_env.paths)

	pd.testing.assert_frame_equal(first_final, second_final)
	assert second_final["student_id"].tolist() == EXPECTED_VALID_IDS
	assert len(_read_rejected(pipeline_env.paths)) == 6
	assert len(_read_state(pipeline_env.paths)["records"]) == 8


def test_changed_record_is_reprocessed_and_snapshot_stays_complete(pipeline_env):
	config_path = pipeline_env.make_config()
	main(config_path)

	updated_csv = pipeline_env.csv_path.read_text(encoding="utf-8").replace(
		'"Aden"', '"Mokha"'
	)
	pipeline_env.csv_path.write_text(updated_csv, encoding="utf-8")
	main(config_path)

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	student_1008 = final.loc[final["student_id"] == 1008].iloc[0]
	assert student_1008["city"] == "Mokha"
	student_1011 = final.loc[final["student_id"] == 1011].iloc[0]
	assert student_1011["attendance"] == pytest.approx(85)
	assert len(_read_state(pipeline_env.paths)["records"]) == 8


def test_changed_imputation_median_reprocesses_unchanged_integrated_rows(
	pipeline_env, api_server, tmp_path
):
	config_path = pipeline_env.make_config()
	main(config_path)
	first_final = _read_final(pipeline_env.paths)
	first_1002 = first_final.loc[first_final["student_id"] == 1002].iloc[0]
	assert first_1002["gpa"] == pytest.approx(3.0)
	first_state = _read_state(pipeline_env.paths)

	# Change only another API record's GPA so the raw API GPA median drops
	# from 3.0 to 2.9 while 1002's integrated row (gpa still missing) is
	# byte-for-byte identical between the two runs.
	modified_api = json.loads(API_DATA_PATH.read_text(encoding="utf-8"))
	for record in modified_api:
		if record["student_id"] == 1001:
			record["gpa"] = 2.0
	modified_api_path = tmp_path / "students_academic_median_changed.json"
	modified_api_path.write_text(json.dumps(modified_api), encoding="utf-8")

	main(pipeline_env.make_config(api_url=api_server(modified_api_path)))

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	student_1002 = final.loc[final["student_id"] == 1002].iloc[0]
	assert student_1002["gpa"] == pytest.approx(2.9)
	second_state = _read_state(pipeline_env.paths)
	assert second_state["records"]["1002"] != first_state["records"]["1002"]
	assert len(second_state["records"]) == 8


def test_deleted_record_leaves_snapshot_without_that_student(pipeline_env):
	config_path = pipeline_env.make_config()
	main(config_path)

	_run_sql(
		pipeline_env.db_path,
		"DELETE FROM enrollments WHERE student_id = 1008;",
	)
	main(config_path)

	final = _read_final(pipeline_env.paths)
	assert 1008 not in final["student_id"].tolist()
	assert final["student_id"].tolist() == [
		1001, 1002, 1006, 1007, 1009, 1011, 1012,
	]
	assert "1008" not in _read_state(pipeline_env.paths)["records"]


def test_missing_previous_final_output_falls_back_to_full_processing(pipeline_env):
	config_path = pipeline_env.make_config()
	main(config_path)
	first_final = _read_final(pipeline_env.paths)
	pipeline_env.paths.processed.unlink()

	main(config_path)

	pd.testing.assert_frame_equal(first_final, _read_final(pipeline_env.paths))


def test_malformed_previous_final_output_falls_back_to_full_processing(pipeline_env):
	config_path = pipeline_env.make_config()
	main(config_path)
	expected_final = _read_final(pipeline_env.paths)

	# Corrupt the previous snapshot while keeping the row count at 8:
	# student 1001 appears twice and student 1002 is missing.
	duplicated_1001 = expected_final.loc[expected_final["student_id"] == 1001]
	without_1002 = expected_final.loc[expected_final["student_id"] != 1002]
	malformed = pd.concat([without_1002, duplicated_1001], ignore_index=True)
	assert len(malformed) == 8
	malformed.to_csv(pipeline_env.paths.processed, index=False, encoding="utf-8")

	main(config_path)

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	assert final["student_id"].is_unique
	assert final.loc[final["student_id"] == 1002].shape[0] == 1
	assert (final["student_id"] == 1001).sum() == 1
	pd.testing.assert_frame_equal(final, expected_final)


@pytest.mark.parametrize(
	("raw_id", "expected"),
	[
		(1001, 1001),
		(1001.0, 1001),
		("1001", 1001),
	],
)
def test_snapshot_student_id_normalization_accepts_exact_integers(raw_id, expected):
	normalized = main_module._normalize_integer_student_ids(pd.Series([raw_id]))

	assert normalized is not None
	assert normalized.dtype == "int64"
	assert normalized.tolist() == [expected]


@pytest.mark.parametrize(
	"raw_id",
	[
		1001.5,
		"1001.5",
		float("nan"),
		None,
		float("inf"),
		float("-inf"),
		"abc",
	],
)
def test_snapshot_student_id_normalization_rejects_invalid_values(raw_id):
	assert main_module._normalize_integer_student_ids(pd.Series([raw_id])) is None


def test_fractional_previous_student_id_triggers_full_processing(pipeline_env):
	config_path = pipeline_env.make_config()
	main(config_path)
	expected_final = _read_final(pipeline_env.paths)

	malformed = expected_final.astype({"student_id": "float64"})
	malformed.loc[malformed["student_id"] == 1001, "student_id"] = 1001.5
	malformed.loc[malformed["student_id"] == 1001.5, "city"] = "Corrupt"
	malformed.to_csv(pipeline_env.paths.processed, index=False, encoding="utf-8")

	main(config_path)

	final = _read_final(pipeline_env.paths)
	pd.testing.assert_frame_equal(final, expected_final)
	assert "Corrupt" not in final["city"].tolist()


def test_previous_student_ids_must_be_unique_after_normalization(
	pipeline_env,
):
	config_path = pipeline_env.make_config()
	main(config_path)
	expected_final = _read_final(pipeline_env.paths)

	malformed = expected_final.astype({"student_id": "object"})
	malformed.loc[malformed["student_id"] == 1002, "student_id"] = "1001.0"
	malformed.loc[malformed["student_id"] == "1001.0", "city"] = "Corrupt"
	malformed.to_csv(pipeline_env.paths.processed, index=False, encoding="utf-8")

	main(config_path)

	final = _read_final(pipeline_env.paths)
	pd.testing.assert_frame_equal(final, expected_final)
	assert final["student_id"].is_unique


def test_output_failure_on_first_run_does_not_save_state(pipeline_env, tmp_path):
	blocked_output = tmp_path / "blocked_output"
	blocked_output.mkdir()
	config_path = pipeline_env.make_config(processed=blocked_output)

	with pytest.raises(IsADirectoryError):
		main(config_path)

	assert not pipeline_env.paths.state.exists()
	# Rejected output is written before the final output under the safe
	# ordering; only the state must stay absent so no snapshot is ever
	# committed against a missing final output.
	assert pipeline_env.paths.rejected.exists()


def test_output_failure_after_successful_run_keeps_previous_state(pipeline_env, tmp_path):
	main(pipeline_env.make_config())
	previous_state_text = pipeline_env.paths.state.read_text(encoding="utf-8")

	blocked_output = tmp_path / "blocked_rejected"
	blocked_output.mkdir()
	config_path = pipeline_env.make_config(rejected=blocked_output)

	with pytest.raises(IsADirectoryError):
		main(config_path)

	assert pipeline_env.paths.state.read_text(encoding="utf-8") == previous_state_text


def test_rejected_write_failure_keeps_final_output_consistent_for_later_runs(
	pipeline_env, tmp_path
):
	config_path = pipeline_env.make_config()
	main(config_path)
	first_final = _read_final(pipeline_env.paths)
	previous_state_text = pipeline_env.paths.state.read_text(encoding="utf-8")

	# RUN 2 changes the source to Mokha but fails while writing the
	# rejected output; the reusable final snapshot must stay at Aden.
	updated_csv = pipeline_env.csv_path.read_text(encoding="utf-8").replace(
		'"Aden"', '"Mokha"'
	)
	pipeline_env.csv_path.write_text(updated_csv, encoding="utf-8")
	blocked_rejected = tmp_path / "blocked_rejected"
	blocked_rejected.mkdir()
	failure_config = pipeline_env.make_config(rejected=blocked_rejected)

	with pytest.raises(IsADirectoryError):
		main(failure_config)

	final_after_failure = _read_final(pipeline_env.paths)
	student_1008 = final_after_failure.loc[final_after_failure["student_id"] == 1008]
	assert student_1008.iloc[0]["city"] == "Aden"
	assert pipeline_env.paths.state.read_text(encoding="utf-8") == previous_state_text

	# RUN 3 reverts the source and removes the failure. The run matches the
	# saved state and reuses rows, which must come from the unchanged Aden
	# snapshot — never the Mokha data that failed to commit.
	reverted_csv = pipeline_env.csv_path.read_text(encoding="utf-8").replace(
		'"Mokha"', '"Aden"'
	)
	pipeline_env.csv_path.write_text(reverted_csv, encoding="utf-8")
	main(pipeline_env.make_config())

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	student_1008 = final.loc[final["student_id"] == 1008].iloc[0]
	assert student_1008["city"] == "Aden"
	pd.testing.assert_frame_equal(final, first_final)
	assert pipeline_env.paths.state.read_text(encoding="utf-8") == previous_state_text


def test_state_save_failure_restores_previous_final_and_state(
	pipeline_env, monkeypatch
):
	config_path = pipeline_env.make_config()
	main(config_path)
	final_before = pipeline_env.paths.processed.read_bytes()
	state_before = pipeline_env.paths.state.read_bytes()

	# RUN 2 changes the source to Mokha. save_state first performs a partial
	# (corrupt) write, then fails; the final output has already been replaced
	# with Mokha rows at that point.
	updated_csv = pipeline_env.csv_path.read_text(encoding="utf-8").replace(
		'"Aden"', '"Mokha"'
	)
	pipeline_env.csv_path.write_text(updated_csv, encoding="utf-8")

	def failing_save_state(state, state_path):
		Path(state_path).write_text('{"version": 1, "records": {"1001"', encoding="utf-8")
		raise OSError("state save failed")

	monkeypatch.setattr(main_module, "save_state", failing_save_state)
	with pytest.raises(OSError):
		main(config_path)

	# Rollback must restore the exact previous final/state bytes.
	assert pipeline_env.paths.processed.read_bytes() == final_before
	assert pipeline_env.paths.state.read_bytes() == state_before

	# RUN 3 reverts the source and uses the real save_state: the run matches
	# the restored state and must reuse Aden rows, never stale Mokha values.
	reverted_csv = updated_csv.replace('"Mokha"', '"Aden"')
	pipeline_env.csv_path.write_text(reverted_csv, encoding="utf-8")
	monkeypatch.undo()
	main(config_path)

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	student_1008 = final.loc[final["student_id"] == 1008].iloc[0]
	assert student_1008["city"] == "Aden"
	assert pipeline_env.paths.processed.read_bytes() == final_before
	assert pipeline_env.paths.state.read_bytes() == state_before


def test_first_run_state_failure_leaves_no_reusable_artifacts(
	pipeline_env, monkeypatch
):
	config_path = pipeline_env.make_config()

	def failing_save_state(state, state_path):
		Path(state_path).write_text('{"version": 1', encoding="utf-8")
		raise OSError("state save failed")

	monkeypatch.setattr(main_module, "save_state", failing_save_state)
	with pytest.raises(OSError):
		main(config_path)

	# A failed first run must not leave a reusable final snapshot or any
	# partial state behind; the recalculated rejected output may remain.
	assert not pipeline_env.paths.processed.exists()
	assert not pipeline_env.paths.state.exists()
	assert pipeline_env.paths.rejected.exists()

	monkeypatch.undo()
	main(config_path)

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	assert len(_read_state(pipeline_env.paths)["records"]) == 8


def test_incremental_disabled_processes_all_rows_independently_of_state(pipeline_env):
	main(pipeline_env.make_config())
	previous_state_text = pipeline_env.paths.state.read_text(encoding="utf-8")
	pipeline_env.paths.processed.unlink()

	main(pipeline_env.make_config(incremental_enabled=False))

	final = _read_final(pipeline_env.paths)
	assert final["student_id"].tolist() == EXPECTED_VALID_IDS
	assert final["source"].eq("CSV|API|DATABASE").all()
	assert pipeline_env.paths.state.read_text(encoding="utf-8") == previous_state_text


def test_raw_source_files_are_not_modified_by_pipeline(pipeline_env):
	def digest(path: Path) -> str:
		return hashlib.sha256(path.read_bytes()).hexdigest()

	before = {
		path: digest(path)
		for path in (pipeline_env.csv_path, pipeline_env.db_path, API_DATA_PATH)
	}

	config_path = pipeline_env.make_config()
	main(config_path)
	main(config_path)

	for path, expected in before.items():
		assert digest(path) == expected
