"""Transform cleaned source records without applying rejection rules."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping

import pandas as pd


NUMERIC_COLUMNS = ("student_id", "age", "gpa", "attendance", "credit_hours", "score")

_IMPUTATION_RANGES = {"gpa": (0, 4), "attendance": (0, 100)}

# Discards records on its own; transform_data logs only through a
# caller-provided logger and never owns config or handlers.
_NULL_LOGGER = logging.Logger("app.transformation.null", logging.CRITICAL + 1)


def _valid_median(series: pd.Series, lower: float, upper: float) -> float | None:
	numeric_values = pd.to_numeric(series, errors="coerce")
	valid_values = numeric_values[numeric_values.between(lower, upper)]
	if valid_values.empty:
		return None
	return float(valid_values.median())


def calculate_imputation_stats(data: pd.DataFrame) -> dict[str, float]:
	"""Compute imputation medians from a complete source DataFrame.

	Follows DATA_CONTRACT.md: each median covers the whole passed source,
	excluding missing, non-numeric, and out-of-range values for that field,
	so an in-range value contributes regardless of other record problems.
	A field with no valid values is omitted from the result.
	"""
	stats: dict[str, float] = {}
	for column, (lower, upper) in _IMPUTATION_RANGES.items():
		if column in data:
			median = _valid_median(data[column], lower, upper)
			if median is not None:
				stats[column] = median
	return stats


def _validate_imputation_stats(
	imputation_stats: Mapping[str, float],
) -> dict[str, float]:
	"""Return the caller's stats as floats, rejecting unusable values."""
	if not isinstance(imputation_stats, Mapping):
		raise ValueError(
			"imputation_stats must be a mapping of column names to numeric values, "
			f"got {type(imputation_stats).__name__}"
		)
	validated: dict[str, float] = {}
	for column, (lower, upper) in _IMPUTATION_RANGES.items():
		if column not in imputation_stats:
			raise ValueError(f"imputation_stats must provide a '{column}' value")
		value = imputation_stats[column]
		if (
			isinstance(value, bool)
			or not isinstance(value, (int, float))
			or not math.isfinite(value)
		):
			raise ValueError(
				f"imputation_stats['{column}'] must be a finite number, got {value!r}"
			)
		if not lower <= value <= upper:
			raise ValueError(
				f"imputation_stats['{column}'] must be between {lower} and {upper}, "
				f"got {value!r}"
			)
		validated[column] = float(value)
	return validated


def transform_data(
	data: pd.DataFrame,
	*,
	imputation_stats: Mapping[str, float] | None = None,
	logger: logging.Logger | None = None,
) -> pd.DataFrame:
	"""Apply recoverable transformations and add derived performance fields.

	Out-of-range numeric values remain unchanged for the validation layer.

	imputation_stats overrides the medians computed from the passed data, so
	callers can supply statistics from the full raw API source (see
	calculate_imputation_stats). Without it, medians are computed from the
	given DataFrame. The transformation owns no config or logging: pass a
	logger to receive messages; by default nothing is logged.
	"""
	if imputation_stats is not None:
		external_stats = _validate_imputation_stats(imputation_stats)
	else:
		external_stats = None
	if logger is None:
		logger = _NULL_LOGGER
	logger.info("Starting student data transformation for %d records.", len(data))
	transformed = data.copy()

	for column in NUMERIC_COLUMNS:
		if column in transformed:
			transformed[column] = pd.to_numeric(transformed[column], errors="coerce")

	if "major" in transformed:
		missing_major = transformed["major"].isna()
		transformed["major"] = transformed["major"].fillna("Unknown")
		if missing_major.any():
			logger.info("Replaced %d missing major values with Unknown.", missing_major.sum())

	if "gpa" in transformed:
		if external_stats is not None:
			gpa_median = external_stats["gpa"]
		else:
			gpa_median = _valid_median(transformed["gpa"], *_IMPUTATION_RANGES["gpa"])
		if gpa_median is not None:
			missing_gpa = transformed["gpa"].isna()
			transformed.loc[missing_gpa, "gpa"] = gpa_median
			if missing_gpa.any():
				logger.info("Imputed %d missing GPA values with median %.2f.", missing_gpa.sum(), gpa_median)

	if "attendance" in transformed:
		if external_stats is not None:
			attendance_median = external_stats["attendance"]
		else:
			attendance_median = _valid_median(
				transformed["attendance"], *_IMPUTATION_RANGES["attendance"]
			)
		if attendance_median is not None:
			missing_attendance = transformed["attendance"].isna()
			transformed.loc[missing_attendance, "attendance"] = attendance_median
			if missing_attendance.any():
				logger.info(
					"Imputed %d missing attendance values with median %.2f.",
					missing_attendance.sum(),
					attendance_median,
				)

	if "gpa" in transformed:
		performance = pd.Series(pd.NA, index=transformed.index, dtype="string")
		valid_gpa = transformed["gpa"].between(0, 4)
		performance.loc[valid_gpa & (transformed["gpa"] >= 3.5)] = "Excellent"
		performance.loc[valid_gpa & (transformed["gpa"] >= 3.0) & (transformed["gpa"] < 3.5)] = "Very Good"
		performance.loc[valid_gpa & (transformed["gpa"] >= 2.5) & (transformed["gpa"] < 3.0)] = "Good"
		performance.loc[valid_gpa & (transformed["gpa"] >= 2.0) & (transformed["gpa"] < 2.5)] = "Acceptable"
		performance.loc[valid_gpa & (transformed["gpa"] < 2.0)] = "At Risk"
		transformed["performance_level"] = performance

	if "attendance" in transformed:
		attendance_status = pd.Series(pd.NA, index=transformed.index, dtype="string")
		valid_attendance = transformed["attendance"].between(0, 100)
		attendance_status.loc[valid_attendance & (transformed["attendance"] >= 75)] = "Good"
		attendance_status.loc[valid_attendance & (transformed["attendance"] < 75)] = "Low"
		transformed["attendance_status"] = attendance_status

	logger.info("Completed student data transformation for %d records.", len(transformed))
	return transformed


def transform(
	data: pd.DataFrame,
	*,
	imputation_stats: Mapping[str, float] | None = None,
	logger: logging.Logger | None = None,
) -> pd.DataFrame:
	"""Compatibility alias for callers using the shorter transformation name."""
	return transform_data(data, imputation_stats=imputation_stats, logger=logger)
