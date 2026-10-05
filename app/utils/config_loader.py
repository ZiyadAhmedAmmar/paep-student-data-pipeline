"""Load and validate the shared pipeline configuration."""

import json
import math
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PATH_KEYS = (
    "sources.csv.path",
    "sources.database.path",
    "output.processed",
    "output.rejected",
    "logging.path",
    "incremental.state_path",
)


def load_config(config_path: str | Path | None = None) -> dict:
    """Return a validated nested dict with filesystem paths as absolute strings.

    The default is the repository's config.json. Relative explicit config paths
    are also based on the repository root, independent of the working directory.
    Paths inside a config are resolved relative to that config's parent folder.
    API settings and other non-path values are preserved.

    Raises FileNotFoundError for a missing file and ValueError for invalid JSON,
    missing required keys, or invalid required values. Other I/O errors propagate.
    """
    path = Path(config_path) if config_path is not None else Path("config.json")
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    path = path.resolve()
    try:
        with path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Configuration file not found: {path}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid JSON configuration in {path}: {exc}") from exc

    required_keys = _PATH_KEYS + ("sources.api.url", "sources.api.timeout_seconds")
    for dotted_key in required_keys:
        value = config
        for key in dotted_key.split("."):
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object containing {dotted_key}")
            if key not in value:
                raise ValueError(f"Missing required configuration key: {dotted_key}")
            value = value[key]
        if dotted_key == "sources.api.timeout_seconds":
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{dotted_key} must be a positive finite number")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"{dotted_key} must be a non-empty string")

    for dotted_key in _PATH_KEYS:
        keys = dotted_key.split(".")
        section = config
        for key in keys[:-1]:
            section = section[key]
        section[keys[-1]] = str((path.parent / section[keys[-1]]).resolve())

    scraping = config.get("scraping")
    if isinstance(scraping, dict):
        for key in ("output", "logging_path"):
            value = scraping.get(key)
            if isinstance(value, str) and value.strip():
                scraping[key] = str((path.parent / value).resolve())
    return config
