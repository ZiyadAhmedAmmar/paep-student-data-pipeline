import pandas as pd
import pytest

from app.utils.lineage import add_lineage


DEFAULT_LINEAGE = "CSV|API|DATABASE"


def make_student_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "student_id": [1001, 1002, 1003],
            "student_name": ["Ahmed Ali", "Sara Omar", "Noor Ahmed"],
            "gpa": [3.8, 3.0, 2.4],
        }
    )


def test_adds_source_column_with_default_lineage_value() -> None:
    result = add_lineage(make_student_data())
    assert "source" in result.columns
    assert set(result["source"]) == {DEFAULT_LINEAGE}


def test_all_rows_receive_default_lineage_value() -> None:
    data = make_student_data()
    result = add_lineage(data)
    assert result["source"].tolist() == [DEFAULT_LINEAGE] * len(data)


def test_custom_source_value_is_applied_to_all_rows() -> None:
    data = make_student_data()
    result = add_lineage(data, source="CSV|API")
    assert result["source"].tolist() == ["CSV|API"] * len(data)


def test_original_dataframe_is_not_mutated() -> None:
    data = make_student_data()
    original = data.copy(deep=True)
    add_lineage(data, source="CSV|API")
    pd.testing.assert_frame_equal(data, original)


def test_existing_columns_values_and_order_are_preserved() -> None:
    data = make_student_data()
    result = add_lineage(data)
    assert result.columns.tolist() == data.columns.tolist() + ["source"]
    for column in data.columns:
        pd.testing.assert_series_equal(result[column], data[column])


def test_row_count_is_unchanged() -> None:
    data = make_student_data()
    result = add_lineage(data)
    assert len(result) == len(data)


def test_row_order_is_unchanged() -> None:
    data = make_student_data()
    result = add_lineage(data)
    assert result["student_id"].tolist() == data["student_id"].tolist()


def test_empty_dataframe_gets_source_column() -> None:
    data = pd.DataFrame(columns=["student_id", "student_name"])
    result = add_lineage(data)
    assert result.empty
    assert "source" in result.columns
    assert len(result["source"]) == 0


def test_existing_source_column_is_replaced_in_output_only() -> None:
    data = make_student_data()
    data["source"] = "CSV"
    original = data.copy(deep=True)
    result = add_lineage(data, source="CSV|API")
    assert result["source"].tolist() == ["CSV|API"] * len(data)
    pd.testing.assert_frame_equal(data, original)


@pytest.mark.parametrize("blank_source", ["", "   "])
def test_blank_source_values_raise_value_error(blank_source: str) -> None:
    with pytest.raises(ValueError, match="source must be a non-empty string"):
        add_lineage(make_student_data(), source=blank_source)


@pytest.mark.parametrize(
    "invalid_source",
    [None, 123, 3.5, ["CSV|API"]],
)
def test_non_string_source_values_are_rejected(invalid_source: object) -> None:
    with pytest.raises(ValueError, match="source must be a non-empty string"):
        add_lineage(make_student_data(), source=invalid_source)


def test_existing_duplicate_rows_are_preserved_without_multiplication() -> None:
    data = pd.DataFrame(
        {
            "student_id": [1001, 1001],
            "student_name": ["Ahmed Ali", "Ahmed Ali"],
        }
    )

    result = add_lineage(data)

    assert len(result) == len(data)
    pd.testing.assert_frame_equal(
        result.drop(columns="source"),
        data,
    )
