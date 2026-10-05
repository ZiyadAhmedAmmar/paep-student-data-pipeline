import logging
from pathlib import Path

import pandas as pd
import pytest

from app.transformation.transformer import (
	calculate_imputation_stats,
	transform,
	transform_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _CaptureHandler(logging.Handler):
	def __init__(self):
		super().__init__()
		self.messages: list[str] = []

	def emit(self, record):
		self.messages.append(record.getMessage())


def canonical_api_data() -> pd.DataFrame:
	return pd.read_json(PROJECT_ROOT / "mock_api" / "students_academic.json")


def test_transform_fills_missing_major_and_numeric_values_from_valid_medians():
	data = pd.DataFrame(
		{
			"student_id": [1001, 1002, 1003, 1011],
			"major": ["math", None, "science", "art"],
			"gpa": [3.0, None, 4.5, 2.0],
			"attendance": [90, 80, 105, None],
		}
	)

	result = transform_data(data)

	assert result.loc[1, "major"] == "Unknown"
	assert result.loc[1, "gpa"] == 2.5
	assert result.loc[3, "attendance"] == 85
	assert result.loc[2, "gpa"] == 4.5
	assert result.loc[2, "attendance"] == 105
	assert pd.isna(result.loc[2, "performance_level"])
	assert pd.isna(result.loc[2, "attendance_status"])


def test_canonical_medians_exclude_invalid_values():
	result = transform_data(canonical_api_data())

	assert result.loc[result["student_id"] == 1002, "gpa"].item() == 3.0
	assert result.loc[result["student_id"] == 1011, "attendance"].item() == 85.0
	assert result["gpa"].median() == 3.0
	assert result["attendance"].median() == 85.0
	assert result.loc[result["student_id"] == 1004, "gpa"].item() == 4.5
	assert result.loc[result["student_id"] == 1003, "attendance"].item() == 105


@pytest.mark.parametrize(
	("gpa", "expected"),
	[
		(3.5, "Excellent"),
		(3.0, "Very Good"),
		(2.5, "Good"),
		(2.0, "Acceptable"),
		(1.9, "At Risk"),
	],
)
def test_performance_level_thresholds(gpa, expected):
	result = transform_data(pd.DataFrame({"gpa": [gpa], "attendance": [75]}))

	assert result.loc[0, "performance_level"] == expected


@pytest.mark.parametrize(
	("attendance", "expected"), [(75, "Good"), (74.99, "Low")]
)
def test_attendance_status_threshold(attendance, expected):
	result = transform_data(pd.DataFrame({"gpa": [3.0], "attendance": [attendance]}))

	assert result.loc[0, "attendance_status"] == expected


def test_numeric_columns_are_converted_without_rejecting_invalid_values():
	data = pd.DataFrame(
		{
			"student_id": ["1001"],
			"age": ["22"],
			"gpa": ["4.5"],
			"attendance": ["105"],
			"score": ["88"],
		}
	)

	result = transform_data(data)

	for column in ("student_id", "age", "gpa", "attendance", "score"):
		assert pd.api.types.is_numeric_dtype(result[column])
	assert result.loc[0, "gpa"] == 4.5
	assert result.loc[0, "attendance"] == 105


def test_calculate_imputation_stats_from_canonical_api_data():
	stats = calculate_imputation_stats(canonical_api_data())

	assert stats == {"gpa": 3.0, "attendance": 85.0}


def test_calculate_imputation_stats_ignores_missing_and_out_of_range_values():
	data = pd.DataFrame(
		{
			"gpa": [1.0, 2.0, None, 4.5, float("nan"), pd.NA, "bad"],
			"attendance": [50, 60, None, 105, float("nan"), pd.NA, "bad"],
		}
	)

	stats = calculate_imputation_stats(data)

	assert stats == {"gpa": 1.5, "attendance": 55.0}


def test_calculate_imputation_stats_is_deterministic():
	data = canonical_api_data()

	assert calculate_imputation_stats(data) == calculate_imputation_stats(data)


def test_calculate_imputation_stats_omits_fields_without_valid_values():
	data = pd.DataFrame(
		{"gpa": [None, 5.0, -1.0], "attendance": [float("nan"), float("nan"), float("nan")]}
	)

	stats = calculate_imputation_stats(data)

	assert stats == {}


def test_external_stats_from_raw_api_impute_integrated_data():
	raw_stats = calculate_imputation_stats(canonical_api_data())
	assert raw_stats["gpa"] == 3.0
	assert raw_stats["attendance"] == 85.0

	integrated_data = pd.DataFrame(
		{
			"student_id": [1001, 1002, 1011, 1012],
			"gpa": [2.9, None, 2.7, 2.9],
			"attendance": [80, 88, None, 80],
		}
	)

	result = transform_data(integrated_data, imputation_stats=raw_stats)

	assert result.loc[result["student_id"] == 1002, "gpa"].item() == 3.0
	assert result.loc[result["student_id"] == 1011, "attendance"].item() == 85.0


def test_transform_data_without_stats_computes_medians_from_input():
	data = pd.DataFrame(
		{
			"student_id": [1001, 1002, 1011],
			"gpa": [2.0, None, 2.0],
			"attendance": [50, 60, None],
		}
	)

	result = transform_data(data)

	assert result.loc[result["student_id"] == 1002, "gpa"].item() == 2.0
	assert result.loc[result["student_id"] == 1011, "attendance"].item() == 55.0


@pytest.mark.parametrize(
	"imputation_stats",
	[
		{"gpa": float("nan"), "attendance": 85.0},
		{"gpa": 3.0, "attendance": float("nan")},
		{"gpa": "3.0", "attendance": 85.0},
		{"gpa": True, "attendance": 85.0},
		{"gpa": None, "attendance": 85.0},
		{"gpa": 4.5, "attendance": 85.0},
		{"gpa": -0.5, "attendance": 85.0},
		{"gpa": 3.0, "attendance": 105},
		{"gpa": 3.0, "attendance": -1},
		{"attendance": 85.0},
		{"gpa": 3.0},
		[("gpa", 3.0), ("attendance", 85.0)],
	],
)
def test_transform_data_rejects_invalid_imputation_stats(imputation_stats):
	data = pd.DataFrame({"gpa": [None], "attendance": [None]})

	with pytest.raises(ValueError):
		transform_data(data, imputation_stats=imputation_stats)


def test_transform_data_does_not_load_config_or_create_logger(monkeypatch):
	def _fail(*args, **kwargs):
		raise AssertionError("transformation must not own config or logging")

	monkeypatch.setattr("app.utils.config_loader.load_config", _fail)
	monkeypatch.setattr("app.utils.logger.setup_logger", _fail)

	data = pd.DataFrame({"major": [None], "gpa": [None], "attendance": [None]})

	transform_data(data)


def test_transform_data_ignores_configured_log_destination(tmp_path, monkeypatch):
	log_path = tmp_path / "pipeline.log"
	monkeypatch.setattr(
		"app.utils.config_loader.load_config",
		lambda *args, **kwargs: {"logging": {"path": str(log_path)}},
	)
	data = pd.DataFrame({"gpa": [3.0], "attendance": [80]})

	transform_data(data)

	assert not log_path.exists()
	assert logging.getLogger("app.transformation.transformer").handlers == []


def test_transform_data_logs_through_passed_logger_without_new_handlers():
	logger = logging.getLogger("test.transformation.passed")
	for handler in list(logger.handlers):
		logger.removeHandler(handler)
	logger.setLevel(logging.INFO)
	capture = _CaptureHandler()
	logger.addHandler(capture)

	data = pd.DataFrame({"major": [None], "gpa": [None], "attendance": [80]})
	transform_data(data, logger=logger)

	assert any(
		"Starting student data transformation for 1 records." in message
		for message in capture.messages
	)
	assert any(
		"Replaced 1 missing major values with Unknown." in message
		for message in capture.messages
	)
	assert len(logger.handlers) == 1
	assert not any(isinstance(handler, logging.FileHandler) for handler in logger.handlers)


def test_transform_data_does_not_mutate_input():
	data = pd.DataFrame(
		{
			"student_id": [1001, 1002],
			"major": ["Math", None],
			"gpa": [2.9, None],
			"attendance": [80, None],
		}
	)
	before = data.copy()

	with_stats = transform_data(data, imputation_stats={"gpa": 3.0, "attendance": 85.0})
	without_stats = transform_data(data)

	assert data.equals(before)
	assert with_stats.loc[1, "gpa"] == 3.0
	assert with_stats.loc[1, "attendance"] == 85.0
	assert without_stats.loc[1, "gpa"] == 2.9
	assert without_stats.loc[1, "attendance"] == 80.0


def test_transform_alias_forwards_options_correctly():
	stats = {"gpa": 3.0, "attendance": 85.0}
	data = pd.DataFrame(
		{
			"student_id": [1002, 1011],
			"gpa": [None, 2.7],
			"attendance": [88, None],
		}
	)
	logger = logging.getLogger("test.transformation.alias")
	for handler in list(logger.handlers):
		logger.removeHandler(handler)
	logger.setLevel(logging.INFO)
	capture = _CaptureHandler()
	logger.addHandler(capture)

	result = transform(data, imputation_stats=stats, logger=logger)
	fallback = transform(data)

	assert result.loc[0, "gpa"] == 3.0
	assert result.loc[1, "attendance"] == 85.0
	assert fallback.loc[0, "gpa"] == 2.7
	assert fallback.loc[1, "attendance"] == 88.0
	assert any(
		"Starting student data transformation for 2 records." in message
		for message in capture.messages
	)
