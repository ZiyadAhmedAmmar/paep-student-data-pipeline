"""End-to-end orchestration for the student data pipeline.

main() composes the existing reusable modules only: extraction, source
validation, cleaning, integration, transformation, lineage, final
validation, incremental processing, metrics, logging, and output writing.
No ETL business logic lives here.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from app.output.csv_writer import write_csv
from app.output.mongodb_writer import write_mongodb_snapshot
from app.sources.api_source import extract_api_data
from app.sources.csv_source import load_data
from app.sources.database_source import extract_database
from app.sources.mongodb_source import extract_mongodb
from app.transformation.cleaner import clean_data
from app.transformation.integration import OUTPUT_COLUMNS, integrate_data
from app.transformation.transformer import (
	calculate_imputation_stats,
	transform_data,
)
from app.utils.config_loader import load_config
from app.utils.incremental import (
	build_state,
	identify_changes,
	load_state,
	save_state,
)
from app.utils.lineage import add_lineage
from app.utils.logger import setup_logger
from app.utils.metrics import (
	PipelineMetrics,
	count_duplicate_records,
	count_missing_values,
)
from app.validation.quality import validate_final_data, validate_source_data

FINAL_COLUMNS = OUTPUT_COLUMNS + [
	"performance_level",
	"attendance_status",
	"source",
]


def main(config_path: str | Path | None = None) -> None:
	"""Run the full pipeline using one configuration file."""
	started = time.perf_counter()
	config = load_config(config_path)
	logger = setup_logger(config["logging"]["path"])
	logger.info("Pipeline started.")
	logger.info("Config loaded.")

	try:
		metrics = PipelineMetrics()

		csv_raw = load_data(config["sources"]["csv"]["path"])
		api_raw = extract_api_data(config["sources"]["api"])
		database_backend = config["sources"].get("database", {}).get(
			"backend", "sqlite"
		).lower()
		if database_backend == "sqlite":
			database_raw = extract_database(config)
		elif database_backend == "mongodb":
			database_raw = extract_mongodb(config)
		else:
			raise ValueError(
				"sources.database.backend must be either 'sqlite' or 'mongodb'."
			)
		logger.info(
			"Sources extracted: CSV=%d, API=%d, DATABASE=%d records.",
			len(csv_raw),
			len(api_raw),
			len(database_raw),
		)

		raw_api_stats = calculate_imputation_stats(api_raw)

		metrics.update_source_counts(
			csv_records=len(csv_raw),
			api_records=len(api_raw),
			database_records=len(database_raw),
		)
		metrics.duplicate_records = count_duplicate_records(csv_raw)
		metrics.missing_values = (
			count_missing_values(csv_raw)
			+ count_missing_values(api_raw)
			+ count_missing_values(database_raw)
		)

		canonical_ids = _derive_canonical_ids(csv_raw)

		csv_valid, csv_rejected = validate_source_data(csv_raw, "CSV")
		api_valid, api_rejected = validate_source_data(
			api_raw, "API", canonical_ids=canonical_ids
		)
		database_valid, database_rejected = validate_source_data(
			database_raw, "DATABASE", canonical_ids=canonical_ids
		)
		rejections = pd.concat(
			[csv_rejected, api_rejected, database_rejected],
			ignore_index=True,
		)
		logger.info(
			"Source validation completed: %d rejected records collected.",
			len(rejections),
		)

		csv_clean = clean_data(csv_valid)
		api_clean = clean_data(api_valid)
		database_clean = clean_data(database_valid)
		logger.info("Cleaning completed.")

		integrated = integrate_data(csv_clean, api_clean, database_clean)
		metrics.integrated_records = len(integrated)
		logger.info("Integration completed: %d integrated records.", len(integrated))

		change_snapshot = _build_change_snapshot(integrated, raw_api_stats)
		new_or_changed, unchanged, reused = _apply_incremental_policy(
			config, integrated, change_snapshot, logger
		)
		logger.info(
			"Incremental comparison completed: %d new/changed, %d unchanged, "
			"%d reused rows.",
			len(new_or_changed),
			len(unchanged),
			len(reused),
		)

		transformed_new = transform_data(
			new_or_changed,
			imputation_stats=raw_api_stats,
			logger=logger,
		)
		transformed_new = add_lineage(transformed_new)
		logger.info("Transformation completed.")

		valid_new, final_rejected = validate_final_data(transformed_new)
		rejections = pd.concat([rejections, final_rejected], ignore_index=True)
		logger.info("Final validation completed.")

		final_data = pd.concat([reused, valid_new], ignore_index=True)
		final_data = _finalize_snapshot(final_data)
		metrics.valid_records = len(final_data)
		metrics.rejected_records = len(rejections)

		# Rejected output is written before the reusable final snapshot: if
		# either write fails, the final output and the saved state stay
		# consistent, so a later unchanged run can never reuse a stale value.
		# With incremental processing the current final and state files are
		# snapshotted first, so a failed state save restores that exact pair.
		incremental_enabled = config.get("incremental", {}).get("enabled", False)
		if incremental_enabled:
			state_path = Path(config["incremental"]["state_path"])
			previous_final = _read_file_snapshot(Path(config["output"]["processed"]))
			previous_state = _read_file_snapshot(state_path)
		else:
			state_path = None

		write_csv(rejections, config["output"]["rejected"])
		write_csv(final_data, config["output"]["processed"])
		logger.info("Outputs written.")

		if incremental_enabled:
			try:
				save_state(build_state(change_snapshot), state_path)
			except Exception:
				logger.exception(
					"Failed to save incremental state; restoring the previous "
					"final output and state."
				)
				try:
					_restore_file_snapshot(
						Path(config["output"]["processed"]), previous_final
					)
					_restore_file_snapshot(state_path, previous_state)
				except Exception:
					logger.exception(
						"Failed to restore the previous final output and state "
						"after the state-save failure; they may be inconsistent."
					)
				raise
			logger.info("Incremental state saved.")

		if config.get("output", {}).get("mongodb", {}).get("enabled", False):
			student_count = write_mongodb_snapshot(
				final_data, config, collection_key="students"
			)
			rejected_count = write_mongodb_snapshot(
				rejections, config, collection_key="rejected"
			)
			logger.info(
				"MongoDB snapshots saved: %d students, %d rejected records.",
				student_count,
				rejected_count,
			)

		metrics.record_processing_time(time.perf_counter() - started)
		logger.info(metrics.summary())
		logger.info("Pipeline completed.")
	except Exception:
		logger.exception("Pipeline failed.")
		raise


def _derive_canonical_ids(csv_raw: pd.DataFrame) -> set[int]:
	"""Return raw non-null CSV student IDs before any rejection rules."""
	if "student_id" not in csv_raw.columns:
		return set()
	numeric_ids = pd.to_numeric(csv_raw["student_id"], errors="coerce").dropna()
	return {int(value) for value in numeric_ids}


def _build_change_snapshot(
	integrated: pd.DataFrame, raw_api_stats: dict[str, float]
) -> pd.DataFrame:
	"""Return the frame used for incremental fingerprints and state.

	The snapshot is the integrated data plus the transformation context
	(raw-API imputation medians) as extra per-row columns, so a changed
	median changes every fingerprint and affected rows are reprocessed
	instead of reusing stale final values. The context columns never reach
	transform_data or the final output: changed IDs are mapped back to rows
	of the original integrated frame only.
	"""
	snapshot = integrated.copy()
	snapshot["__imputation_gpa"] = raw_api_stats["gpa"]
	snapshot["__imputation_attendance"] = raw_api_stats["attendance"]
	return snapshot


def _student_ids(frame: pd.DataFrame) -> set[int]:
	"""Return the normalized integer student IDs present in frame."""
	return set(pd.to_numeric(frame["student_id"]).astype("int64"))


def _rows_for_ids(integrated: pd.DataFrame, ids: set[int]) -> pd.DataFrame:
	"""Select the original integrated rows for the given student IDs."""
	mask = pd.to_numeric(integrated["student_id"]).astype("int64").isin(ids)
	return integrated.loc[mask]


def _apply_incremental_policy(
	config: dict,
	integrated: pd.DataFrame,
	change_snapshot: pd.DataFrame,
	logger: logging.Logger,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
	"""Split integrated records into rows to process and rows to reuse.

	Change detection runs against change_snapshot (integrated data plus the
	transformation-context columns), while both returned processing frames
	always come from the original integrated data and never carry the
	context columns.

	Returns (new_or_changed, unchanged, reused). Without incremental
	processing every integrated row is processed and nothing is reused.
	Unchanged rows are only reused from a previous final output whose
	student IDs are unique and contain exactly one row per unchanged ID;
	otherwise the pipeline falls back to full processing so the snapshot
	can never become silently incomplete or duplicated.
	"""
	if not config.get("incremental", {}).get("enabled", False):
		return integrated, integrated.iloc[0:0], integrated.iloc[0:0]

	previous_state = load_state(config["incremental"]["state_path"])
	changed, unchanged = identify_changes(change_snapshot, previous_state)
	new_or_changed = _rows_for_ids(integrated, _student_ids(changed))
	unchanged = _rows_for_ids(integrated, _student_ids(unchanged))
	if unchanged.empty:
		return new_or_changed, unchanged, integrated.iloc[0:0]

	reused = _load_reusable_rows(
		Path(config["output"]["processed"]), unchanged
	)
	if reused is None:
		logger.warning(
			"Previous final output is missing or unusable for %d unchanged "
			"records; falling back to full processing.",
			len(unchanged),
		)
		return integrated, unchanged, integrated.iloc[0:0]
	return new_or_changed, unchanged, reused


def _load_reusable_rows(
	previous_path: Path, unchanged: pd.DataFrame
) -> pd.DataFrame | None:
	"""Return previous final rows for the unchanged IDs, or None if unusable.

	The previous snapshot is only usable when required columns are present
	and its student IDs are finite exact integers and unique after normalization
	across the whole file, with exactly one row for every unchanged ID. Any
	violation returns None so the caller falls back to full processing
	instead of partially repairing a malformed snapshot. Rows for IDs that
	are no longer in the current integrated snapshot are never reused, so
	deleted records cannot survive in the new snapshot.
	"""
	if not previous_path.exists():
		return None
	try:
		previous_final = pd.read_csv(previous_path)
	except (OSError, ValueError):
		return None
	if not set(FINAL_COLUMNS).issubset(previous_final.columns):
		return None

	previous_ids = _normalize_integer_student_ids(previous_final["student_id"])
	if previous_ids is None or previous_ids.duplicated().any():
		return None

	unchanged_ids = _student_ids(unchanged)
	mask = previous_ids.isin(unchanged_ids)
	reusable = previous_final.loc[mask].copy()
	reusable["student_id"] = previous_ids.loc[mask]
	if len(reusable) != len(unchanged_ids) or set(reusable["student_id"]) != unchanged_ids:
		return None
	return reusable


def _normalize_integer_student_ids(values: pd.Series) -> pd.Series | None:
	"""Normalize exact, finite integer IDs without silently truncating them."""
	int64_min = -(2**63)
	int64_max = 2**63 - 1
	normalized: list[int] = []

	for value in values:
		if pd.isna(value):
			return None
		try:
			numeric = Decimal(str(value))
		except (InvalidOperation, ValueError):
			return None
		if not numeric.is_finite() or numeric != numeric.to_integral_value():
			return None

		integer = int(numeric)
		if integer < int64_min or integer > int64_max:
			return None
		normalized.append(integer)

	return pd.Series(normalized, index=values.index, dtype="int64")


def _finalize_snapshot(final_data: pd.DataFrame) -> pd.DataFrame:
	"""Order the final snapshot deterministically with the project columns.

	student_id is normalized to integers so fresh rows (typed float by the
	raw CSV blank-ID row) and reused rows (read back as integers) always
	produce identical output files. Assembly problems surface here as
	errors: missing or duplicate IDs raise ValueError before anything is
	written rather than being truncated or silently dropped from the snapshot.
	"""
	ids = _normalize_integer_student_ids(final_data["student_id"])
	if ids is None:
		raise ValueError("Final snapshot contains invalid student_id values.")
	if ids.duplicated().any():
		raise ValueError("Final snapshot contains duplicate student_id values.")
	ordered = final_data.sort_values("student_id", kind="mergesort")
	ordered["student_id"] = ids
	columns = [column for column in FINAL_COLUMNS if column in ordered]
	return ordered.loc[:, columns].reset_index(drop=True)


def _read_file_snapshot(path: Path) -> bytes | None:
	"""Return a file's exact bytes, or None when it does not exist as a file."""
	if not path.is_file():
		return None
	return path.read_bytes()


def _restore_file_snapshot(path: Path, snapshot: bytes | None) -> None:
	"""Return a file to its snapshotted bytes, deleting it when it had none.

	snapshot=None means the file did not exist before the run, so any file
	created by the failed run is removed; otherwise the previous bytes are
	written back verbatim, preserving formatting and content exactly.
	"""
	if snapshot is None:
		path.unlink(missing_ok=True)
		return
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_bytes(snapshot)


if __name__ == "__main__":
	main()
