"""Configuration contract and portable path resolution tests."""

import json
from pathlib import Path, PureWindowsPath

import pytest

from app.utils.config_loader import load_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATH_KEYS = (
    "sources.csv.path",
    "sources.database.path",
    "output.processed",
    "output.rejected",
    "logging.path",
    "incremental.state_path",
)


@pytest.fixture
def config_data():
    return json.loads((PROJECT_ROOT / "config.json").read_text(encoding="utf-8"))


def value_at(config, dotted_key):
    for key in dotted_key.split("."):
        config = config[key]
    return config


def test_official_config_is_portable_and_independent_of_cwd(tmp_path, monkeypatch, config_data):
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert load_config("config.json") == config
    assert config["sources"]["api"] == {
        "url": "http://localhost:8000/students", "timeout_seconds": 5
    }
    assert config["incremental"]["enabled"] is True
    for dotted_key in PATH_KEYS:
        raw_path = value_at(config_data, dotted_key)
        assert not Path(raw_path).is_absolute()
        assert not PureWindowsPath(raw_path).drive
        assert value_at(config, dotted_key) == str((PROJECT_ROOT / raw_path).resolve())


def test_alternate_config_resolves_paths_from_its_own_directory(tmp_path, monkeypatch, config_data):
    config_path = tmp_path / "settings" / "custom.json"
    config_path.parent.mkdir()
    config_data["sources"]["csv"]["path"] = str(tmp_path / "absolute.csv")
    config_path.write_text(json.dumps(config_data), encoding="utf-8")
    monkeypatch.chdir(PROJECT_ROOT / "app")
    config = load_config(config_path)
    for dotted_key in PATH_KEYS:
        expected = (config_path.parent / value_at(config_data, dotted_key)).resolve()
        assert value_at(config, dotted_key) == str(expected)
    assert config["sources"]["api"] == config_data["sources"]["api"]


def test_missing_config(tmp_path):
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config(tmp_path / "missing.json")


def test_malformed_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"sources":', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON configuration"):
        load_config(path)


@pytest.mark.parametrize("dotted_key", (
    "sources", "output", "logging", "incremental",
    "sources.csv", "sources.api", "sources.database",
    *PATH_KEYS, "sources.api.url", "sources.api.timeout_seconds",
))
def test_missing_required_section_or_key(tmp_path, config_data, dotted_key):
    keys = dotted_key.split(".")
    section = config_data
    for key in keys[:-1]:
        section = section[key]
    del section[keys[-1]]
    path = tmp_path / "missing_key.json"
    path.write_text(json.dumps(config_data), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required configuration key") as error:
        load_config(path)
    assert dotted_key in str(error.value)


@pytest.mark.parametrize("value", [None, [], "config", 1])
def test_config_must_be_an_object(tmp_path, value):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="Expected a JSON object"):
        load_config(path)


@pytest.mark.parametrize("dotted_key,value", [
    ("sources.csv", []),
    ("logging", None),
    ("output.processed", " "),
    ("incremental.state_path", 42),
    ("sources.api.url", ""),
    ("sources.api.timeout_seconds", 0),
    ("sources.api.timeout_seconds", -1),
    ("sources.api.timeout_seconds", True),
    ("sources.api.timeout_seconds", "5"),
    ("sources.api.timeout_seconds", float("inf")),
    ("sources.api.timeout_seconds", float("nan")),
])
def test_invalid_required_values(tmp_path, config_data, dotted_key, value):
    keys = dotted_key.split(".")
    section = config_data
    for key in keys[:-1]:
        section = section[key]
    section[keys[-1]] = value
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(config_data), encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_config(path)
    assert dotted_key in str(error.value)
