"""HTTP REST API source extraction for academic student records."""

from __future__ import annotations

import logging
import math
from numbers import Real
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import requests

from app.sources.base_source import BaseSource
from app.utils.config_loader import load_config

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"
REQUIRED_FIELDS = {"student_id", "gpa", "attendance", "status"}

logger = logging.getLogger(__name__)


class APISourceError(RuntimeError):
    """Raised when the API source cannot extract a valid transport payload."""


def load_api_config(config_path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    return dict(load_config(config_path)["sources"]["api"])


def _validate_api_config(config: Mapping[str, Any]) -> tuple[str, float]:
    try:
        url = config["url"]
        timeout = config["timeout_seconds"]
    except KeyError as exc:
        raise APISourceError("API configuration requires url and timeout_seconds.") from exc

    if not isinstance(url, str) or not url.strip():
        raise APISourceError("API URL must be a non-empty string.")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, Real)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise APISourceError("API timeout_seconds must be a positive finite number.")

    return url, float(timeout)


class APISource(BaseSource):
    """Extract student records from a configured HTTP API endpoint."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        api_config = dict(config) if config is not None else load_api_config()
        self.url, self.timeout_seconds = _validate_api_config(api_config)

    def extract(self) -> pd.DataFrame:
        try:
            response = requests.get(self.url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.Timeout as exc:
            logger.error(f"API request timed out after {self.timeout_seconds} seconds.")
            raise APISourceError(f"API request timed out after {self.timeout_seconds} seconds.") from exc
        except requests.ConnectionError as exc:
            logger.error(f"API connection error for {self.url}.")
            raise APISourceError(f"API connection error for {self.url}.") from exc
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            logger.error(f"API HTTP error: {status_code}.")
            raise APISourceError(f"API HTTP error: {status_code}.") from exc
        except requests.RequestException as exc:
            logger.error(f"API request failed: {exc}.")
            raise APISourceError(f"API request failed: {exc}.") from exc

        if not response.content:
            logger.error("API returned an empty response.")
            raise APISourceError("API returned an empty response.")

        try:
            payload = response.json()
            logger.info("API response received.")
        except ValueError as exc:
            logger.error("Invalid JSON returned by API.")
            raise APISourceError("Invalid JSON returned by API.") from exc

        if not payload:
            logger.error("API returned an empty response.")
            raise APISourceError("API returned an empty response.")
        if not isinstance(payload, list):
            logger.error("API payload must be a JSON array of records.")
            raise APISourceError("API payload must be a JSON array of records.")
        if not all(isinstance(record, dict) for record in payload):
            logger.error("API payload records must be JSON objects.")
            raise APISourceError("API payload records must be JSON objects.")

        for index, record in enumerate(payload):
            missing_fields = REQUIRED_FIELDS.difference(record)
            if missing_fields:
                fields = ", ".join(sorted(missing_fields))
                raise APISourceError(
                    f"API record {index} is missing required fields: {fields}."
                )

        frame = pd.DataFrame(payload)
        logger.info(f"Extracted {len(frame)} records from API.")

        logger.info("API extraction completed successfully.")
        return frame


def extract_api_data(config: Mapping[str, Any] | None = None) -> pd.DataFrame:
    return APISource(config).extract()
