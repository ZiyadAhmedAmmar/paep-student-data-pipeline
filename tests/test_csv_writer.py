"""CSV output round trips and input errors, using temporary destinations only."""

import pandas as pd
import pytest

from app.output.csv_writer import write_csv


@pytest.mark.parametrize("destination", ["processed/final_dataset.csv", "rejected/rejected_records.csv"])
def test_write_csv_round_trip_without_index(tmp_path, destination):
    dataframe = pd.DataFrame({
        "student_id": [1, 2],
        "name": ["لؤي", 'Name, with "quotes"'],
        "score": [92.5, 81.0],
    }, index=[10, 20])
    path = tmp_path / destination
    write_csv(dataframe, path)
    restored = pd.read_csv(path)
    assert restored.columns.tolist() == dataframe.columns.tolist()
    pd.testing.assert_frame_equal(restored, dataframe.reset_index(drop=True))


def test_empty_dataframe_preserves_headers(tmp_path):
    path = tmp_path / "empty.csv"
    write_csv(pd.DataFrame(columns=["student_id", "name"]), str(path))
    restored = pd.read_csv(path)
    assert restored.empty
    assert restored.columns.tolist() == ["student_id", "name"]


def test_existing_file_is_overwritten(tmp_path):
    path = tmp_path / "output.csv"
    write_csv(pd.DataFrame({"value": [1, 2]}), path)
    write_csv(pd.DataFrame({"value": [3]}), path)
    assert pd.read_csv(path)["value"].tolist() == [3]


@pytest.mark.parametrize("data", [None, [], {"student_id": [1]}])
def test_invalid_dataframe_has_no_filesystem_side_effects(tmp_path, data):
    path = tmp_path / "unused" / "output.csv"
    with pytest.raises(TypeError, match="pandas DataFrame"):
        write_csv(data, path)
    assert not path.parent.exists()


@pytest.mark.parametrize("path,error", [(None, TypeError), (42, TypeError), ("", ValueError), (" ", ValueError)])
def test_invalid_output_path(path, error):
    with pytest.raises(error):
        write_csv(pd.DataFrame(), path)


def test_directory_output_path(tmp_path):
    with pytest.raises(IsADirectoryError, match="CSV output path is a directory"):
        write_csv(pd.DataFrame(), tmp_path)


def test_parent_is_a_file(tmp_path):
    parent = tmp_path / "file"
    parent.write_text("keep", encoding="utf-8")
    with pytest.raises(OSError):
        write_csv(pd.DataFrame(), parent / "output.csv")
    assert parent.read_text(encoding="utf-8") == "keep"
