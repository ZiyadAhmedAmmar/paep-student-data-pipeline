from pathlib import Path

import pandas as pd

from app.sources.csv_source import load_data
from app.transformation.cleaner import clean_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CSV = PROJECT_ROOT / "data" / "raw" / "students.csv"


def test_clean_data_removes_exact_duplicates_and_preserves_other_rows() -> None:
    data = pd.DataFrame(
        {
            "student_id": [1001, 1001, 1002],
            "student_name": ["Alice", "Alice", "Bob"],
        }
    )

    result = clean_data(data)

    expected = pd.DataFrame(
        {
            "student_id": [1001, 1002],
            "student_name": ["Alice", "Bob"],
        }
    )
    pd.testing.assert_frame_equal(result, expected)


def test_clean_data_normalizes_whitespace_and_title_case() -> None:
    data = pd.DataFrame(
        {
            "student_name": ["  Noor   Ahmed  "],
            "major": [" artificial   intelligence "],
            "city": [" SANAA "],
            "status": ["  active   student "],
            "course_name": [" data   structures "],
        }
    )

    result = clean_data(data)

    assert result.iloc[0].to_dict() == {
        "student_name": "Noor Ahmed",
        "major": "Artificial Intelligence",
        "city": "Sanaa",
        "status": "Active Student",
        "course_name": "Data Structures",
    }


def test_clean_data_preserves_missing_values() -> None:
    data = pd.DataFrame({"major": [None], "student_name": [pd.NA]})

    result = clean_data(data)

    assert pd.isna(result.loc[0, "major"])
    assert pd.isna(result.loc[0, "student_name"])


def test_clean_data_preserves_invalid_numeric_values() -> None:
    data = pd.DataFrame({"age": [15], "gpa": [4.5], "attendance": [105], "score": [-1]})

    result = clean_data(data)

    pd.testing.assert_frame_equal(result, data)


def test_clean_data_does_not_modify_canonical_raw_file() -> None:
    before = CANONICAL_CSV.read_bytes()
    raw_data = load_data(CANONICAL_CSV)

    result = clean_data(raw_data)

    assert len(result) == 13
    assert (result["student_id"] == 1007).sum() == 1
    assert result.loc[result["student_id"] == 1001, "student_name"].iloc[0] == "Ahmed Ali"
    assert result.loc[result["student_id"] == 1006, "student_name"].iloc[0] == "Noor Ahmed"
    assert result.loc[result["student_id"] == 1001, "city"].iloc[0] == "Sanaa"
    assert result.loc[result["student_id"] == 1006, "major"].isna().all()
    assert CANONICAL_CSV.read_bytes() == before