import pandas as pd
import pytest

from app.transformation.integration import (
    OUTPUT_COLUMNS,
    DataIntegrationError,
    integrate_data,
)


def make_csv_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "student_id": [1001, 1002, 1003],
            "student_name": [" Ahmed Ali ", "Sara Omar", "Noor Ahmed"],
            "age": [20, 21, 22],
            "major": ["Computer Science", "artificial intelligence", "Data Science"],
            "city": [" SANAA ", "Aden", "taiz"],
        }
    )


def make_api_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "student_id": [1001, 1002, 1003],
            "gpa": [3.8, None, 4.5],
            "attendance": [95, 88, 105],
            "status": [" Active ", "active", "inactive"],
        }
    )


def make_database_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "student_id": [1001, 1002, 1003],
            "course_name": [
                "Data Engineering",
                "Database Systems",
                "Machine Learning",
            ],
            "credit_hours": [3, 3, 4],
            "semester": ["2026-Fall", "2026-Fall", "2026-Fall"],
            "score": [93, 88, 77],
        }
    )


def test_successful_integration_returns_one_row_per_matching_student() -> None:
    result = integrate_data(make_csv_data(), make_api_data(), make_database_data())

    assert isinstance(result, pd.DataFrame)
    assert result["student_id"].tolist() == [1001, 1002, 1003]
    assert len(result) == 3


def test_required_output_columns_are_returned_in_expected_order() -> None:
    result = integrate_data(make_csv_data(), make_api_data(), make_database_data())

    assert result.columns.tolist() == OUTPUT_COLUMNS


def test_values_from_all_sources_are_combined_for_same_student_id() -> None:
    result = integrate_data(make_csv_data(), make_api_data(), make_database_data())
    row = result.set_index("student_id").loc[1001]

    assert row["student_name"] == " Ahmed Ali "
    assert row["gpa"] == 3.8
    assert row["course_name"] == "Data Engineering"
    assert row["score"] == 93


def test_missing_values_remain_missing_after_integration() -> None:
    result = integrate_data(make_csv_data(), make_api_data(), make_database_data())

    assert pd.isna(result.loc[result["student_id"] == 1002, "gpa"].item())


def test_integration_does_not_clean_text_values() -> None:
    result = integrate_data(make_csv_data(), make_api_data(), make_database_data())
    row = result.set_index("student_id").loc[1001]

    assert row["student_name"] == " Ahmed Ali "
    assert row["city"] == " SANAA "
    assert row["status"] == " Active "


def test_integration_does_not_create_transformation_columns() -> None:
    result = integrate_data(make_csv_data(), make_api_data(), make_database_data())

    assert "performance_level" not in result.columns
    assert "attendance_status" not in result.columns


def test_integration_does_not_reject_out_of_range_values() -> None:
    result = integrate_data(make_csv_data(), make_api_data(), make_database_data())

    row = result.set_index("student_id").loc[1003]
    assert row["gpa"] == 4.5
    assert row["attendance"] == 105


@pytest.mark.parametrize(
    ("source_name", "csv_data", "api_data", "database_data"),
    [
        (
            "CSV",
            pd.concat([make_csv_data(), make_csv_data().iloc[[0]]], ignore_index=True),
            make_api_data(),
            make_database_data(),
        ),
        (
            "API",
            make_csv_data(),
            pd.concat([make_api_data(), make_api_data().iloc[[0]]], ignore_index=True),
            make_database_data(),
        ),
        (
            "database",
            make_csv_data(),
            make_api_data(),
            pd.concat(
                [make_database_data(), make_database_data().iloc[[0]]],
                ignore_index=True,
            ),
        ),
    ],
)
def test_duplicate_student_ids_raise_clear_exception(
    source_name: str,
    csv_data: pd.DataFrame,
    api_data: pd.DataFrame,
    database_data: pd.DataFrame,
) -> None:
    with pytest.raises(
        DataIntegrationError,
        match=f"{source_name} data contains duplicate student_id",
    ):
        integrate_data(csv_data, api_data, database_data)


def test_integration_does_not_multiply_rows_for_unique_inputs() -> None:
    result = integrate_data(make_csv_data(), make_api_data(), make_database_data())

    assert len(result) == result["student_id"].nunique()


def test_input_dataframes_are_not_mutated() -> None:
    csv_data = make_csv_data()
    api_data = make_api_data()
    database_data = make_database_data()
    original_csv = csv_data.copy(deep=True)
    original_api = api_data.copy(deep=True)
    original_database = database_data.copy(deep=True)

    integrate_data(csv_data, api_data, database_data)

    pd.testing.assert_frame_equal(csv_data, original_csv)
    pd.testing.assert_frame_equal(api_data, original_api)
    pd.testing.assert_frame_equal(database_data, original_database)


def test_no_common_student_ids_returns_empty_frame_with_output_columns() -> None:
    csv_data = make_csv_data()
    api_data = make_api_data()
    database_data = make_database_data()
    api_data["student_id"] = [2001, 2002, 2003]

    result = integrate_data(csv_data, api_data, database_data)

    assert result.empty
    assert result.columns.tolist() == OUTPUT_COLUMNS


def test_unmatched_ids_are_excluded_from_integrated_output() -> None:
    api_data = pd.concat(
        [
            make_api_data(),
            pd.DataFrame(
                {
                    "student_id": [1099],
                    "gpa": [3.0],
                    "attendance": [80],
                    "status": ["active"],
                }
            ),
        ],
        ignore_index=True,
    )

    result = integrate_data(make_csv_data(), api_data, make_database_data())

    assert result["student_id"].tolist() == [1001, 1002, 1003]
    assert 1099 not in result["student_id"].tolist()
