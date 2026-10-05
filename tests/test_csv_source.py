import json
from pathlib import Path

import pandas as pd
import pytest

from app.sources.csv_source import load_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_data_returns_dataframe(tmp_path: Path) -> None:
    csv_path = tmp_path / "students.csv"
    csv_path.write_text("student_id,name\n1,Alice\n2,Bob\n", encoding="utf-8")

    result = load_data(csv_path)

    expected = pd.DataFrame(
        {
            "student_id": [1, 2],
            "name": ["Alice", "Bob"],
        }
    )
    pd.testing.assert_frame_equal(result, expected)


def test_load_data_raises_when_file_does_not_exist(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="Input file does not exist"):
        load_data(missing_path)


def test_load_data_raises_when_dataset_is_empty(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("student_id,name\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Input dataset is empty"):
        load_data(csv_path)


def test_load_data_reads_the_configured_canonical_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    config = json.loads((PROJECT_ROOT / "config.json").read_text(encoding="utf-8"))
    monkeypatch.chdir(PROJECT_ROOT)

    result = load_data(config["sources"]["csv"]["path"])

    assert len(result) == 14
    assert list(result.columns) == ["student_id", "student_name", "age", "major", "city"]
    assert (result["student_id"] == 1007).sum() == 2
    assert result["student_id"].isna().sum() == 1
    assert result.loc[result["student_id"] == 1006, "major"].isna().all()
    assert result.loc[result["student_id"] == 1005, "age"].iloc[0] == 15
    assert result.loc[result["student_id"] == 1001, "student_name"].iloc[0] == " Ahmed Ali "
    assert result.loc[result["student_id"] == 1002, "major"].iloc[0] == "artificial intelligence"
    assert result.loc[result["student_id"] == 1003, "city"].iloc[0] == "taiz"
    assert result.loc[result["student_id"] == 1006, "student_name"].iloc[0] == "  Noor   Ahmed  "


def test_load_data_propagates_unreadable_source_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path = tmp_path / "students.csv"
    csv_path.write_text("student_id,name\n1,Alice\n", encoding="utf-8")

    def raise_permission_error(*args: object, **kwargs: object) -> None:
        raise PermissionError("permission denied")

    monkeypatch.setattr(pd, "read_csv", raise_permission_error)

    with pytest.raises(PermissionError, match="permission denied"):
        load_data(csv_path)
