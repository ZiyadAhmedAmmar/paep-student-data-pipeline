"""Reusable cleaning functions for extracted student data."""

import pandas as pd


TITLE_CASE_COLUMNS = {
	"student_name",
	"major",
	"city",
	"status",
	"course_name",
}


def _normalize_text(value: object, title_case: bool) -> object:
	if pd.isna(value) or not isinstance(value, str):
		return value

	normalized = " ".join(value.split())
	return normalized.title() if title_case else normalized


def clean_data(data: pd.DataFrame) -> pd.DataFrame:
	"""Clean textual values and remove exact duplicate records."""
	cleaned = data.drop_duplicates().reset_index(drop=True).copy()

	for column in cleaned.columns:
		if not pd.api.types.is_string_dtype(cleaned[column].dtype):
			continue

		cleaned[column] = cleaned[column].map(
			lambda value: _normalize_text(value, column in TITLE_CASE_COLUMNS)
		)

	return cleaned
