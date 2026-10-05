import pandas as pd
import pytest

from app.validation.quality import validate_final_data, validate_source_data


def test_valid_csv_rows_pass_source_validation():
    data = pd.DataFrame(
        {
            "student_id": [1001, 1002],
            "student_name": [" Ahmed Ali ", "Sara Mohammed"],
            "age": [21, 22],
            "major": ["Computer Science", "artificial intelligence"],
            "city": [" SANAA ", "ADEN"],
        }
    )

    valid, rejected = validate_source_data(data, "CSV")

    pd.testing.assert_frame_equal(valid, data)
    assert rejected.empty


def test_missing_student_id_is_rejected():
    data = pd.DataFrame({"student_id": [None], "age": [22]})

    valid, rejected = validate_source_data(data, "CSV")

    assert valid.empty
    assert rejected.loc[0, "error_reason"] == "Missing student_id"


def test_blank_student_id_is_rejected():
    data = pd.DataFrame({"student_id": [""], "age": [22]})

    _, rejected = validate_source_data(data, "CSV")

    assert rejected.loc[0, "error_reason"] == "Missing student_id"


def test_age_15_is_rejected_as_invalid_age():
    data = pd.DataFrame({"student_id": [1005], "age": [15]})

    valid, rejected = validate_source_data(data, "CSV")

    assert valid.empty
    assert rejected.loc[0, "error_reason"] == "Invalid Age"


@pytest.mark.parametrize("age", [16, 80])
def test_valid_age_boundaries_pass(age):
    data = pd.DataFrame({"student_id": [1001], "age": [age]})

    valid, rejected = validate_source_data(data, "CSV")

    assert len(valid) == 1
    assert rejected.empty


def test_invalid_gpa_is_rejected():
    data = pd.DataFrame({"student_id": [1004], "gpa": [4.5]})

    valid, rejected = validate_source_data(data, "API")

    assert valid.empty
    assert rejected.loc[0, "error_reason"] == "Invalid GPA"


@pytest.mark.parametrize("gpa", [0, 4])
def test_valid_gpa_boundaries_pass(gpa):
    data = pd.DataFrame({"student_id": [1001], "gpa": [gpa]})

    valid, rejected = validate_source_data(data, "API")

    assert len(valid) == 1
    assert rejected.empty


def test_missing_gpa_is_not_rejected_during_source_validation():
    data = pd.DataFrame({"student_id": [1002], "gpa": [None]})

    valid, rejected = validate_source_data(data, "API")

    assert len(valid) == 1
    assert rejected.empty
    assert pd.isna(valid.loc[0, "gpa"])


def test_invalid_attendance_is_rejected():
    data = pd.DataFrame({"student_id": [1003], "attendance": [105]})

    valid, rejected = validate_source_data(data, "API")

    assert valid.empty
    assert rejected.loc[0, "error_reason"] == "Invalid Attendance"


@pytest.mark.parametrize("attendance", [0, 100])
def test_valid_attendance_boundaries_pass(attendance):
    data = pd.DataFrame({"student_id": [1001], "attendance": [attendance]})

    valid, rejected = validate_source_data(data, "API")

    assert len(valid) == 1
    assert rejected.empty


def test_missing_attendance_is_not_rejected_during_source_validation():
    data = pd.DataFrame({"student_id": [1011], "attendance": [None]})

    valid, rejected = validate_source_data(data, "API")

    assert len(valid) == 1
    assert rejected.empty
    assert pd.isna(valid.loc[0, "attendance"])


def test_invalid_score_is_rejected():
    data = pd.DataFrame({"student_id": [1010], "score": [105]})

    valid, rejected = validate_source_data(data, "DATABASE")

    assert valid.empty
    assert rejected.loc[0, "error_reason"] == "Invalid Score"


@pytest.mark.parametrize("score", [0, 100])
def test_valid_score_boundaries_pass(score):
    data = pd.DataFrame({"student_id": [1001], "score": [score]})

    valid, rejected = validate_source_data(data, "DATABASE")

    assert len(valid) == 1
    assert rejected.empty


def test_missing_major_is_not_rejected():
    data = pd.DataFrame({"student_id": [1006], "age": [23], "major": [None]})

    valid, rejected = validate_source_data(data, "CSV")

    assert len(valid) == 1
    assert rejected.empty
    assert pd.isna(valid.loc[0, "major"])


def test_api_id_1099_is_rejected_as_incompatible_student_id():
    data = pd.DataFrame({"student_id": [1099], "gpa": [3.1], "attendance": [85]})

    valid, rejected = validate_source_data(data, "API", canonical_ids={1001, 1002})

    assert valid.empty
    assert rejected.loc[0, "error_reason"] == "Incompatible student_id"


@pytest.mark.parametrize("student_id", [1001.5, "not-an-id"])
def test_malformed_student_ids_are_rejected_without_crashing(student_id):
    data = pd.DataFrame({"student_id": [student_id], "gpa": [3.1]})

    valid, rejected = validate_source_data(data, "API", canonical_ids={1001, 1002})

    assert valid.empty
    assert rejected.loc[0, "student_id"] == student_id
    assert rejected.loc[0, "error_reason"] == "Incompatible student_id"


def test_compatible_ids_pass():
    data = pd.DataFrame({"student_id": [1001, 1002], "gpa": [3.8, None]})

    valid, rejected = validate_source_data(data, "API", canonical_ids={1001, 1002})

    assert valid["student_id"].tolist() == [1001, 1002]
    assert rejected.empty


def test_rejected_records_have_expected_columns():
    data = pd.DataFrame({"student_id": [1005], "age": [15]})

    _, rejected = validate_source_data(data, "CSV")

    assert rejected.columns.tolist() == ["student_id", "source", "stage", "error_reason"]


def test_source_value_is_preserved_in_rejected_records():
    data = pd.DataFrame({"student_id": [1004], "gpa": [4.5]})

    _, rejected = validate_source_data(data, "API")

    assert rejected.loc[0, "source"] == "API"
    assert rejected.loc[0, "stage"] == "SOURCE_VALIDATION"


def test_source_validation_does_not_perform_cleaning():
    data = pd.DataFrame(
        {
            "student_id": [1001],
            "student_name": [" Ahmed   Ali "],
            "city": [" SANAA "],
            "age": [21],
        }
    )

    valid, _ = validate_source_data(data, "CSV")

    assert valid.loc[0, "student_name"] == " Ahmed   Ali "
    assert valid.loc[0, "city"] == " SANAA "


def test_source_validation_does_not_perform_imputation():
    data = pd.DataFrame(
        {"student_id": [1002, 1011], "gpa": [None, 2.7], "attendance": [88, None]}
    )

    valid, rejected = validate_source_data(data, "API")

    assert rejected.empty
    assert pd.isna(valid.loc[0, "gpa"])
    assert pd.isna(valid.loc[1, "attendance"])


def test_valid_and_rejected_records_are_separated_correctly():
    data = pd.DataFrame({"student_id": [1001, 1005], "age": [21, 15]})

    valid, rejected = validate_source_data(data, "CSV")

    assert valid["student_id"].tolist() == [1001]
    assert rejected["student_id"].tolist() == [1005]
    assert rejected["error_reason"].tolist() == ["Invalid Age"]


def test_input_dataframe_is_not_mutated():
    data = pd.DataFrame(
        {"student_id": ["1001", ""], "age": ["21", "15"], "major": [None, "CS"]}
    )
    original = data.copy(deep=True)

    validate_source_data(data, "CSV", canonical_ids={1001})

    pd.testing.assert_frame_equal(data, original)


def test_exact_duplicate_is_not_rejected_by_source_validation():
    data = pd.DataFrame(
        {
            "student_id": [1007, 1007],
            "student_name": ["Yousef Ali", "Yousef Ali"],
            "age": [24, 24],
        }
    )

    valid, rejected = validate_source_data(data, "CSV")

    assert len(valid) == 2
    assert rejected.empty


def test_conflicting_duplicate_student_id_is_rejected_by_source_validation():
    data = pd.DataFrame(
        {
            "student_id": [1007, 1007],
            "student_name": ["Yousef Ali", "Different Name"],
            "age": [24, 24],
        }
    )

    valid, rejected = validate_source_data(data, "CSV")

    assert valid.empty
    assert rejected["error_reason"].tolist() == [
        "Conflicting duplicate student_id",
        "Conflicting duplicate student_id",
    ]


def test_final_validation_rejects_invalid_final_ranges():
    data = pd.DataFrame(
        {
            "student_id": [1001, 1002, 1003, 1004],
            "age": [15, 21, 21, 21],
            "gpa": [3.0, 4.5, 3.0, 3.0],
            "attendance": [90, 90, 105, 90],
            "score": [88, 88, 88, 105],
            "source": ["CSV|API|DATABASE"] * 4,
        }
    )

    valid, rejected = validate_final_data(data)

    assert valid.empty
    assert rejected["stage"].tolist() == ["FINAL_VALIDATION"] * 4
    assert rejected["error_reason"].tolist() == [
        "Invalid Age",
        "Invalid GPA",
        "Invalid Attendance",
        "Invalid Score",
    ]


def test_final_validation_checks_duplicate_student_id():
    data = pd.DataFrame(
        {
            "student_id": [1001, 1001],
            "age": [21, 21],
            "gpa": [3.0, 3.0],
            "attendance": [90, 90],
            "score": [88, 88],
            "source": ["CSV|API|DATABASE", "CSV|API|DATABASE"],
        }
    )

    valid, rejected = validate_final_data(data)

    assert valid.empty
    assert rejected["error_reason"].tolist() == [
        "Duplicate student_id",
        "Duplicate student_id",
    ]


def test_final_validation_rejects_missing_required_columns():
    data = pd.DataFrame(
        {
            "student_id": [1001],
            "age": [21],
            "gpa": [3.8],
            "score": [93],
        }
    )

    with pytest.raises(ValueError, match="Missing required final columns: attendance"):
        validate_final_data(data)


def test_final_validation_accepts_valid_final_dataframe():
    data = pd.DataFrame(
        {
            "student_id": [1001, 1002],
            "age": [21, 22],
            "gpa": [3.8, 3.0],
            "attendance": [95, 88],
            "score": [93, 88],
            "source": ["CSV|API|DATABASE", "CSV|API|DATABASE"],
        }
    )

    valid, rejected = validate_final_data(data)

    pd.testing.assert_frame_equal(valid, data)
    assert rejected.empty


def test_empty_dataframe_behavior_is_explicit():
    data = pd.DataFrame(columns=["student_id", "age", "gpa", "attendance", "score"])

    valid, rejected = validate_source_data(data, "CSV")

    assert valid.empty
    assert rejected.empty
    assert rejected.columns.tolist() == ["student_id", "source", "stage", "error_reason"]


def test_canonical_expected_rejected_cases_total_six():
    canonical_ids = set(range(1001, 1013))

    csv_data = pd.DataFrame(
        {
            "student_id": [1005, None, 1006, 1007, 1007],
            "age": [15, 22, 23, 24, 24],
            "major": [
                "Data Science",
                "Computer Science",
                None,
                "Cyber Security",
                "Cyber Security",
            ],
        }
    )
    api_data = pd.DataFrame(
        {
            "student_id": [1002, 1003, 1004, 1011, 1099],
            "gpa": [None, 3.2, 4.5, 2.7, 3.1],
            "attendance": [88, 105, 90, None, 85],
        }
    )
    database_data = pd.DataFrame(
        {
            "student_id": [1010],
            "score": [105],
        }
    )

    _, csv_rejected = validate_source_data(csv_data, "CSV")
    _, api_rejected = validate_source_data(
        api_data, "API", canonical_ids=canonical_ids
    )
    _, database_rejected = validate_source_data(
        database_data, "DATABASE", canonical_ids=canonical_ids
    )

    rejected = pd.concat(
        [csv_rejected, api_rejected, database_rejected], ignore_index=True
    )

    assert len(rejected) == 6
    assert rejected["error_reason"].tolist() == [
        "Invalid Age",
        "Missing student_id",
        "Invalid Attendance",
        "Invalid GPA",
        "Incompatible student_id",
        "Invalid Score",
    ]

    student_ids = rejected["student_id"]
    assert student_ids.iloc[0] == 1005
    assert pd.isna(student_ids.iloc[1])
    assert student_ids.iloc[2:].tolist() == [1003, 1004, 1099, 1010]
