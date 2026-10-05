import json

import pandas as pd
import pytest

from app.utils.incremental import (
    IncrementalStateError,
    build_state,
    fingerprint_record,
    identify_changes,
    load_state,
    save_state,
)


def make_students(rows, columns=("student_id", "name", "gpa")):
    return pd.DataFrame(rows, columns=list(columns))


def test_same_record_produces_same_fingerprint() -> None:
    as_dict = {"student_id": 1001, "name": "Ahmed", "gpa": 3.5}
    as_series = pd.Series(as_dict)

    assert fingerprint_record(as_dict) == fingerprint_record(as_series)
    assert fingerprint_record({"gpa": 3.5, "name": "Ahmed", "student_id": 1001}) == (
        fingerprint_record(as_dict)
    )


def test_changed_field_produces_different_fingerprint() -> None:
    original = {"student_id": 1001, "name": "Ahmed", "gpa": 3.5}
    changed = {"student_id": 1001, "name": "Ahmed", "gpa": 3.6}

    assert fingerprint_record(original) != fingerprint_record(changed)


def test_fingerprint_is_deterministic_across_repeated_calls() -> None:
    record = {"student_id": 1002, "name": "Sara", "gpa": None}

    fingerprints = {fingerprint_record(record) for _ in range(5)}

    assert len(fingerprints) == 1


def test_fingerprint_does_not_mutate_input() -> None:
    record = {"student_id": 1003, "name": "Lina", "gpa": 2.8}
    record_before = dict(record)
    series = pd.Series({"student_id": 1003, "name": "Lina", "gpa": 2.8})
    series_before = series.copy(deep=True)

    fingerprint_record(record)
    fingerprint_record(series)

    assert record == record_before
    pd.testing.assert_series_equal(series, series_before)


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA])
def test_missing_value_variants_share_one_fingerprint(missing) -> None:
    with_missing = {"student_id": 1004, "name": "Omar", "gpa": missing}
    with_none = {"student_id": 1004, "name": "Omar", "gpa": None}
    with_value = {"student_id": 1004, "name": "Omar", "gpa": 0.0}

    assert fingerprint_record(with_missing) == fingerprint_record(with_none)
    assert fingerprint_record(with_missing) != fingerprint_record(with_value)


def test_numeric_values_are_normalized_before_hashing() -> None:
    as_int = {"student_id": 1001, "gpa": 3}
    as_float = {"student_id": 1001, "gpa": 3.0}

    assert fingerprint_record(as_int) == fingerprint_record(as_float)


def test_fingerprint_rejects_unsupported_record_types() -> None:
    with pytest.raises(TypeError, match="Series or a Mapping"):
        fingerprint_record([(1001, "Ahmed")])


def test_load_state_missing_file_returns_empty_first_run_state(tmp_path) -> None:
    state = load_state(tmp_path / "missing" / "pipeline_state.json")

    assert state == {"version": 1, "records": {}}


def test_state_save_and_load_round_trip(tmp_path) -> None:
    state_path = tmp_path / "state" / "pipeline_state.json"
    state = build_state(make_students([(1001, "Ahmed", 3.5), (1002, "Sara", 2.0)]))

    save_state(state, state_path)

    assert load_state(state_path) == state


def test_save_state_creates_parent_directory(tmp_path) -> None:
    state_path = tmp_path / "a" / "b" / "pipeline_state.json"

    save_state({"version": 1, "records": {"1001": "abc123"}}, state_path)

    assert state_path.exists()


def test_save_state_writes_readable_and_deterministic_json(tmp_path) -> None:
    state = build_state(make_students([(1001, "Ahmed", 3.5), (1002, "Sara", 2.0)]))
    first_path = tmp_path / "one.json"
    second_path = tmp_path / "two.json"

    save_state(state, first_path)
    save_state(state, second_path)

    assert first_path.read_text(encoding="utf-8") == second_path.read_text(encoding="utf-8")
    saved = json.loads(first_path.read_text(encoding="utf-8"))
    assert saved == {"version": 1, "records": state["records"]}


def test_load_state_corrupted_json_raises_clear_error(tmp_path) -> None:
    state_path = tmp_path / "pipeline_state.json"
    state_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(IncrementalStateError, match="Invalid JSON"):
        load_state(state_path)


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ('{"version": 2, "records": {}}', "unsupported schema version"),
        ('{"version": 1}', "'records'"),
        ('{"version": 1, "records": []}', "'records'"),
        ('{"version": 1, "records": {"1001": 42}}', "non-string fingerprint"),
        ('"just a string"', "JSON object"),
    ],
)
def test_load_state_invalid_schema_raises_clear_error(tmp_path, content, match) -> None:
    state_path = tmp_path / "pipeline_state.json"
    state_path.write_text(content, encoding="utf-8")

    with pytest.raises(IncrementalStateError, match=match):
        load_state(state_path)


def test_first_run_identifies_all_records_as_new() -> None:
    data = make_students([(1001, "Ahmed", 3.0), (1002, "Sara", 2.0), (1003, "Lina", 3.5)])

    new_or_changed, unchanged = identify_changes(data, {})
    assert list(new_or_changed["student_id"]) == [1001, 1002, 1003]
    assert unchanged.empty

    full_empty_state, unchanged_full = identify_changes(data, {"version": 1, "records": {}})
    assert list(full_empty_state["student_id"]) == [1001, 1002, 1003]
    assert unchanged_full.empty


def test_second_identical_run_identifies_all_as_unchanged(tmp_path) -> None:
    data = make_students([(1001, "Ahmed", 3.0), (1002, "Sara", 2.0), (1003, "Lina", 3.5)])
    state_path = tmp_path / "pipeline_state.json"
    save_state(build_state(data), state_path)

    previous_state = load_state(state_path)
    new_or_changed, unchanged = identify_changes(data, previous_state)

    assert new_or_changed.empty
    assert list(unchanged["student_id"]) == [1001, 1002, 1003]


def test_only_modified_student_is_detected_as_changed() -> None:
    first_run = make_students([(1001, "Ahmed", 3.0), (1002, "Sara", 2.0), (1003, "Lina", 3.5)])
    state = build_state(first_run)
    second_run = make_students([(1001, "Ahmed", 3.0), (1002, "Sara", 2.5), (1003, "Lina", 3.5)])

    new_or_changed, unchanged = identify_changes(second_run, state)

    assert list(new_or_changed["student_id"]) == [1002]
    assert list(unchanged["student_id"]) == [1001, 1003]


def test_newly_added_student_is_detected_as_new() -> None:
    state = build_state(make_students([(1001, "Ahmed", 3.0)]))
    second_run = make_students([(1001, "Ahmed", 3.0), (1004, "Omar", 2.9)])

    new_or_changed, unchanged = identify_changes(second_run, state)

    assert list(new_or_changed["student_id"]) == [1004]
    assert list(unchanged["student_id"]) == [1001]


def test_combined_changed_new_and_unchanged_records(tmp_path) -> None:
    state_path = tmp_path / "pipeline_state.json"
    first_run = make_students([(1001, "Ahmed", 3.0), (1002, "Sara", 2.0), (1003, "Lina", 3.5)])
    save_state(build_state(first_run), state_path)
    second_run = make_students(
        [
            (1001, "Ahmed", 3.0),
            (1002, "Sara", 2.5),
            (1003, "Lina", 3.5),
            (1004, "Omar", 2.9),
        ]
    )

    new_or_changed, unchanged = identify_changes(second_run, load_state(state_path))

    assert list(new_or_changed["student_id"]) == [1002, 1004]
    assert list(unchanged["student_id"]) == [1001, 1003]


def test_identify_changes_and_build_state_do_not_mutate_input() -> None:
    data = make_students([(1001, "Ahmed", 3.0), (1002, "Sara", 2.0)])
    before = data.copy(deep=True)

    state = build_state(data)
    identify_changes(data, state)

    pd.testing.assert_frame_equal(data, before)


def test_output_row_order_follows_input_order() -> None:
    first_run = make_students([(1001, "Ahmed", 3.0), (1002, "Sara", 2.0), (1003, "Lina", 3.5)])
    state = build_state(first_run)
    second_run = make_students(
        [
            (1003, "Lina", 3.9),
            (1001, "Ahmed", 3.0),
            (1004, "Omar", 2.9),
            (1002, "Sara", 2.0),
        ]
    )

    new_or_changed, unchanged = identify_changes(second_run, state)

    assert list(new_or_changed["student_id"]) == [1003, 1004]
    assert list(unchanged["student_id"]) == [1001, 1002]


def test_missing_key_column_raises_value_error() -> None:
    data = pd.DataFrame({"name": ["Ahmed"], "gpa": [3.0]})

    with pytest.raises(ValueError, match="student_id"):
        identify_changes(data, {"version": 1, "records": {}})
    with pytest.raises(ValueError, match="student_id"):
        build_state(data)


def test_duplicate_student_ids_are_rejected_when_building_state() -> None:
    data = make_students([(1001, "Ahmed", 3.0), (1001, "Ahmed", 4.0)])

    with pytest.raises(ValueError, match="duplicate"):
        build_state(data)


def test_duplicate_student_ids_are_rejected_by_identify_changes() -> None:
    data = make_students([(1001, "Ahmed", 3.0), (1001, "Ahmed", 4.0)])

    with pytest.raises(ValueError, match="duplicate"):
        identify_changes(data, {"version": 1, "records": {}})


def test_duplicate_keys_across_representations_are_rejected() -> None:
    data = make_students([(1001, "Ahmed", 3.0), (1001.0, "Ahmed", 3.0)])

    with pytest.raises(ValueError, match="duplicate"):
        build_state(data)
    with pytest.raises(ValueError, match="duplicate"):
        identify_changes(data, {"version": 1, "records": {}})


def test_integer_and_float_keys_produce_identical_canonical_state() -> None:
    from_int = build_state(make_students([(1001, "Ahmed", 3.0)]))
    from_float = build_state(make_students([(1001.0, "Ahmed", 3.0)]))

    assert list(from_float["records"]) == ["1001"]
    assert from_float == from_int


def test_float_typed_keys_match_integer_state_as_unchanged() -> None:
    state = build_state(make_students([(1001, "Ahmed", 3.0)]))
    retyped = make_students([(1001.0, "Ahmed", 3.0)])

    new_or_changed, unchanged = identify_changes(retyped, state)

    assert new_or_changed.empty
    assert list(unchanged["student_id"]) == [1001.0]


def test_string_keys_are_rejected_instead_of_colliding() -> None:
    data = make_students([("1001", "Ahmed", 3.0)])

    with pytest.raises(ValueError, match="non-numeric"):
        build_state(data)
    with pytest.raises(ValueError, match="non-numeric"):
        identify_changes(data, {"version": 1, "records": {}})


def test_non_integer_numeric_keys_are_rejected_clearly() -> None:
    data = make_students([(1001.5, "Ahmed", 3.0)])

    with pytest.raises(ValueError, match="non-integer"):
        build_state(data)
    with pytest.raises(ValueError, match="non-integer"):
        identify_changes(data, {"version": 1, "records": {}})


def test_missing_student_id_values_are_rejected() -> None:
    data = make_students([(1001, "Ahmed", 3.0), (None, "Sara", 2.0)])

    with pytest.raises(ValueError, match="missing"):
        build_state(data)
    with pytest.raises(ValueError, match="missing"):
        identify_changes(data, {"version": 1, "records": {}})


def test_empty_dataframe_behavior_is_explicit() -> None:
    data = make_students([])

    state = build_state(data)
    new_or_changed, unchanged = identify_changes(data, state)

    assert state == {"version": 1, "records": {}}
    assert new_or_changed.empty
    assert unchanged.empty


def test_build_state_is_deterministic_regardless_of_column_order() -> None:
    data = make_students([(1001, "Ahmed", 3.0), (1002, "Sara", 2.0)])
    reordered = data[["gpa", "name", "student_id"]]

    assert build_state(data) == build_state(reordered)


@pytest.mark.parametrize(
    ("previous_state", "match"),
    [
        ({"version": 2, "records": {}}, "unsupported schema version"),
        ({"version": 1}, "'records'"),
        ({"version": 1, "records": []}, "'records'"),
        ({"version": 1, "records": {"1001": 42}}, "non-string fingerprint"),
        ({"fingerprints": {}}, "unsupported schema version"),
    ],
)
def test_identify_changes_rejects_malformed_previous_state(
    previous_state, match
) -> None:
    data = make_students([(1001, "Ahmed", 3.0)])

    with pytest.raises(IncrementalStateError, match=match):
        identify_changes(data, previous_state)


def test_identify_changes_rejects_non_mapping_previous_state() -> None:
    data = make_students([(1001, "Ahmed", 3.0)])

    with pytest.raises(TypeError, match="Mapping"):
        identify_changes(data, "not a state")


def test_save_state_rejects_invalid_state_without_writing(tmp_path) -> None:
    state_path = tmp_path / "pipeline_state.json"

    with pytest.raises(IncrementalStateError):
        save_state({"version": 9, "records": {}}, state_path)

    assert not state_path.exists()
