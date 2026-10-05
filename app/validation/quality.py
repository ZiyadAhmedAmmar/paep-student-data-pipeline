"""Data validation and rejected-record classification."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


SOURCE_VALIDATION_STAGE = "SOURCE_VALIDATION"
FINAL_VALIDATION_STAGE = "FINAL_VALIDATION"

REJECTED_COLUMNS = ["student_id", "source", "stage", "error_reason"]
REQUIRED_FINAL_COLUMNS = {"student_id", "age", "gpa", "attendance", "score"}

RANGE_RULES = {
    "age": (16, 80, "Invalid Age"),
    "gpa": (0, 4, "Invalid GPA"),
    "attendance": (0, 100, "Invalid Attendance"),
    "score": (0, 100, "Invalid Score"),
}


def validate_source_data(
    data: pd.DataFrame,
    source: str,
    canonical_ids: set[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate one raw source and separate valid rows from rejected rows."""
    frame = data.copy(deep=True)
    reasons = _empty_reasons(frame.index)

    _mark_missing_student_ids(frame, reasons)
    _mark_incompatible_student_ids(frame, reasons, canonical_ids)
    _mark_conflicting_duplicates(frame, reasons)

    for column, (lower, upper, reason) in RANGE_RULES.items():
        if column in frame.columns:
            allow_missing = column in {"gpa", "attendance"}
            _mark_out_of_range(
                frame, reasons, column, lower, upper, reason, allow_missing
            )

    return _split_validation_result(frame, reasons, source, SOURCE_VALIDATION_STAGE)


def validate_final_data(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate final integrated data before load."""
    _validate_final_schema(data)

    frame = data.copy(deep=True)
    reasons = _empty_reasons(frame.index)

    _mark_missing_student_ids(frame, reasons)
    _mark_duplicate_student_ids(frame, reasons)

    for column, (lower, upper, reason) in RANGE_RULES.items():
        _mark_out_of_range(frame, reasons, column, lower, upper, reason, False)

    source_values = (
        frame["source"].astype("object")
        if "source" in frame.columns
        else pd.Series("FINAL", index=frame.index, dtype="object")
    )

    return _split_validation_result(
        frame,
        reasons,
        source_values,
        FINAL_VALIDATION_STAGE,
    )


def _validate_final_schema(frame: pd.DataFrame) -> None:
    missing_columns = sorted(REQUIRED_FINAL_COLUMNS.difference(frame.columns))
    if missing_columns:
        columns = ", ".join(missing_columns)
        raise ValueError(f"Missing required final columns: {columns}")


def _empty_reasons(index: Iterable) -> pd.Series:
    return pd.Series(pd.NA, index=index, dtype="object")


def _student_id_series(frame: pd.DataFrame) -> pd.Series:
    if "student_id" not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="object")
    return frame["student_id"]


def _is_missing(series: pd.Series) -> pd.Series:
    as_text = series.astype("string")
    return series.isna() | as_text.str.strip().eq("").fillna(False)


def _numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _mark_reason(reasons: pd.Series, mask: pd.Series, reason: str) -> None:
    unset = reasons.isna()
    reasons.loc[mask & unset] = reason


def _mark_missing_student_ids(frame: pd.DataFrame, reasons: pd.Series) -> None:
    student_ids = _student_id_series(frame)
    _mark_reason(reasons, _is_missing(student_ids), "Missing student_id")


def _mark_incompatible_student_ids(
    frame: pd.DataFrame,
    reasons: pd.Series,
    canonical_ids: set[int] | None,
) -> None:
    if canonical_ids is None:
        return

    student_ids = _student_id_series(frame)
    missing = _is_missing(student_ids)
    numeric_ids = _numeric_series(student_ids)
    whole_numbers = numeric_ids.notna() & numeric_ids.mod(1).eq(0)
    compatible = whole_numbers & numeric_ids.isin(canonical_ids)
    _mark_reason(reasons, ~missing & ~compatible, "Incompatible student_id")


def _mark_conflicting_duplicates(frame: pd.DataFrame, reasons: pd.Series) -> None:
    if "student_id" not in frame.columns or frame.empty:
        return

    student_ids = frame["student_id"]
    missing = _is_missing(student_ids)
    duplicate_ids = student_ids[~missing & student_ids.duplicated(keep=False)].unique()

    conflict_mask = pd.Series(False, index=frame.index)
    for student_id in duplicate_ids:
        rows = frame.loc[student_ids.eq(student_id)]
        if len(rows.drop_duplicates()) > 1:
            conflict_mask.loc[rows.index] = True

    _mark_reason(reasons, conflict_mask, "Conflicting duplicate student_id")


def _mark_duplicate_student_ids(frame: pd.DataFrame, reasons: pd.Series) -> None:
    student_ids = _student_id_series(frame)
    missing = _is_missing(student_ids)
    duplicate_mask = ~missing & student_ids.duplicated(keep=False)
    _mark_reason(reasons, duplicate_mask, "Duplicate student_id")


def _mark_out_of_range(
    frame: pd.DataFrame,
    reasons: pd.Series,
    column: str,
    lower: float,
    upper: float,
    reason: str,
    allow_missing: bool,
) -> None:
    values = frame[column]
    numeric_values = _numeric_series(values)
    missing = _is_missing(values)

    invalid = numeric_values.isna() | ~numeric_values.between(lower, upper)
    if allow_missing:
        invalid = invalid & ~missing

    _mark_reason(reasons, invalid, reason)


def _split_validation_result(
    frame: pd.DataFrame,
    reasons: pd.Series,
    source: str | pd.Series,
    stage: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rejected_mask = reasons.notna()
    valid_data = frame.loc[~rejected_mask].copy(deep=True)

    if isinstance(source, pd.Series):
        rejected_source = source.loc[rejected_mask].to_list()
    else:
        rejected_source = [source] * int(rejected_mask.sum())

    rejected_data = pd.DataFrame(
        {
            "student_id": _student_id_series(frame).loc[rejected_mask].to_list(),
            "source": rejected_source,
            "stage": [stage] * int(rejected_mask.sum()),
            "error_reason": reasons.loc[rejected_mask].to_list(),
        },
        columns=REJECTED_COLUMNS,
        index=frame.loc[rejected_mask].index,
    ).reset_index(drop=True)

    return valid_data.reset_index(drop=True), rejected_data
