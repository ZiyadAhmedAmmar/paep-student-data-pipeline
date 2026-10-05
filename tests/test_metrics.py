import pandas as pd
import pytest

from app.utils.metrics import (
    PipelineMetrics,
    count_duplicate_records,
    count_missing_values,
)


def test_metrics_default_values() -> None:
    metrics = PipelineMetrics()

    assert metrics.as_dict() == {
        "csv_records": 0,
        "api_records": 0,
        "database_records": 0,
        "integrated_records": 0,
        "valid_records": 0,
        "rejected_records": 0,
        "duplicate_records": 0,
        "missing_values": 0,
        "processing_time": 0.0,
    }


def test_metrics_updates_source_and_pipeline_counts() -> None:
    metrics = PipelineMetrics()
    metrics.update_source_counts(csv_records=14, api_records=13, database_records=12)
    metrics.integrated_records = 8
    metrics.valid_records = 8
    metrics.rejected_records = 6

    assert metrics.csv_records == 14
    assert metrics.api_records == 13
    assert metrics.database_records == 12
    assert metrics.integrated_records == 8
    assert metrics.valid_records == 8
    assert metrics.rejected_records == 6


def test_count_duplicate_records_counts_only_extra_copies() -> None:
    data = pd.DataFrame({"student_id": [1001, 1001, 1002, 1002, 1002]})

    assert count_duplicate_records(data, subset="student_id") == 3


def test_count_duplicate_records_accepts_iterable_subset() -> None:
    data = pd.DataFrame(
        {
            "student_id": [1001, 1001, 1002],
            "term": ["fall", "fall", "spring"],
        }
    )

    subset = (name for name in ["student_id", "term"])

    assert count_duplicate_records(data, subset=subset) == 1


def test_count_missing_values_counts_missing_cells() -> None:
    data = pd.DataFrame({"name": ["A", None], "score": [pd.NA, 90]})

    assert count_missing_values(data) == 2


def test_metric_utilities_do_not_mutate_input() -> None:
    data = pd.DataFrame({"student_id": [1001, 1001], "score": [None, 90]})
    before = data.copy(deep=True)

    count_duplicate_records(data)
    count_missing_values(data)

    pd.testing.assert_frame_equal(data, before)


def test_processing_time_and_dictionary_representation() -> None:
    metrics = PipelineMetrics()
    metrics.record_processing_time(1.25)

    assert metrics.processing_time == 1.25
    assert metrics.as_dict()["processing_time"] == 1.25


def test_processing_time_cannot_be_negative() -> None:
    with pytest.raises(ValueError):
        PipelineMetrics().record_processing_time(-1)


def test_summary_is_readable() -> None:
    metrics = PipelineMetrics(csv_records=14, valid_records=8, processing_time=1.25)

    summary = metrics.summary()

    assert "PIPELINE EXECUTION SUMMARY" in summary
    assert "CSV Records : 14" in summary
    assert "Valid Records : 8" in summary
    assert "Processing Time : 1.25 seconds" in summary