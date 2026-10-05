"""Integrate source-validated student data from the pipeline sources."""

from __future__ import annotations

import pandas as pd


OUTPUT_COLUMNS = [
    "student_id",
    "student_name",
    "age",
    "major",
    "city",
    "gpa",
    "attendance",
    "status",
    "course_name",
    "credit_hours",
    "semester",
    "score",
]


class DataIntegrationError(ValueError):
    """Raised when integration cannot safely combine source data."""


def _ensure_unique_student_ids(data: pd.DataFrame, source_name: str) -> None:
    duplicate_mask = data["student_id"].duplicated(keep=False)
    if not duplicate_mask.any():
        return

    duplicates = data.loc[duplicate_mask, "student_id"].tolist()
    raise DataIntegrationError(
        f"{source_name} data contains duplicate student_id values that would "
        f"multiply rows during integration: {duplicates}"
    )


def integrate_data(
    csv_data: pd.DataFrame,
    api_data: pd.DataFrame,
    database_data: pd.DataFrame,
) -> pd.DataFrame:
    """Return records shared by CSV, API, and database sources.

    Inputs are expected to have already passed source validation and cleaning.
    Integration only joins records by ``student_id`` and preserves source
    values as received.
    """
    for source_name, data in (
        ("CSV", csv_data),
        ("API", api_data),
        ("database", database_data),
    ):
        _ensure_unique_student_ids(data, source_name)

    integrated = (
        csv_data.copy()
        .merge(api_data.copy(), on="student_id", how="inner", validate="one_to_one")
        .merge(
            database_data.copy(),
            on="student_id",
            how="inner",
            validate="one_to_one",
        )
    )

    return integrated.loc[:, OUTPUT_COLUMNS]
