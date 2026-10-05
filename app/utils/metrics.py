"""Reusable metrics for a pipeline execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd


def count_duplicate_records(
	data: pd.DataFrame,
	subset: str | Iterable[str] | None = None,
) -> int:
	"""Return the number of duplicate rows beyond the first copy."""
	if subset is not None and not isinstance(subset, str):
		subset = list(subset)
	return int(data.duplicated(subset=subset, keep="first").sum())


def count_missing_values(data: pd.DataFrame) -> int:
	"""Return the total number of missing cells in a DataFrame."""
	return int(data.isna().sum().sum())


@dataclass
class PipelineMetrics:
	"""Counters and runtime information collected during one pipeline run."""

	csv_records: int = 0
	api_records: int = 0
	database_records: int = 0
	integrated_records: int = 0
	valid_records: int = 0
	rejected_records: int = 0
	duplicate_records: int = 0
	missing_values: int = 0
	processing_time: float = 0.0

	def update_source_counts(
		self,
		*,
		csv_records: int | None = None,
		api_records: int | None = None,
		database_records: int | None = None,
	) -> None:
		"""Update any supplied source record counts."""
		for name, value in (
			("csv_records", csv_records),
			("api_records", api_records),
			("database_records", database_records),
		):
			if value is not None:
				self._set_non_negative(name, value)
				setattr(self, name, int(value))

	def record_processing_time(self, seconds: float) -> None:
		"""Store elapsed processing time in seconds."""
		if seconds < 0:
			raise ValueError("processing time cannot be negative")
		self.processing_time = float(seconds)

	def as_dict(self) -> dict[str, int | float]:
		"""Return all metrics as a dictionary suitable for logging or JSON."""
		return asdict(self)

	def summary(self) -> str:
		"""Return a readable summary of this pipeline execution."""
		return "\n".join(
			[
				"---",
				"## PIPELINE EXECUTION SUMMARY",
				"",
				f"CSV Records : {self.csv_records}",
				f"API Records : {self.api_records}",
				f"Database Records : {self.database_records}",
				f"Integrated Records : {self.integrated_records}",
				f"Valid Records : {self.valid_records}",
				f"Rejected Records : {self.rejected_records}",
				f"Duplicate Records : {self.duplicate_records}",
				f"Missing Values : {self.missing_values}",
				f"Processing Time : {self.processing_time:.2f} seconds",
			]
		)

	@staticmethod
	def _set_non_negative(name: str, value: int) -> None:
		if value < 0:
			raise ValueError(f"{name} cannot be negative")
