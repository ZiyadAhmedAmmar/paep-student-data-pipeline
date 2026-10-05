"""Run a separate extract-clean-transform-validate-load web pipeline."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from app.output.csv_writer import write_csv
from app.sources.web_scraping_source import WebScrapingSource
from app.transformation.cleaner import clean_data
from app.transformation.transformer import transform_data
from app.utils.config_loader import load_config
from app.utils.logger import setup_logger


def run_pipeline(config_path: str | Path | None = None) -> pd.DataFrame:
	"""Run the standalone scraper pipeline and return its written records."""
	started = time.perf_counter()
	config = load_config(config_path)
	scraping = config.get("scraping", {})
	logger = setup_logger(scraping.get("logging_path", config["logging"]["path"]))
	logger.info("Web scraping pipeline started.")

	raw = WebScrapingSource(scraping).extract()
	required_columns = scraping.get("required_columns", [])
	if not isinstance(required_columns, list) or not all(
		isinstance(column, str) and column for column in required_columns
	):
		raise ValueError("scraping.required_columns must be a list of column names.")
	missing_columns = sorted(set(required_columns).difference(raw.columns))
	if missing_columns:
		fields = ", ".join(missing_columns)
		raise ValueError(f"Scraped table is missing required columns: {fields}.")

	cleaned = clean_data(raw)
	logger.info("Scraping table cleaned: %d records.", len(cleaned))
	transformed = transform_data(cleaned, logger=logger)
	validated = _validate_scraped_data(transformed, required_columns)
	write_csv(validated, scraping["output"])
	logger.info("Web scraping output written to %s.", scraping["output"])
	logger.info(
		"Web scraping pipeline completed: %d records in %.2f seconds.",
		len(validated),
		time.perf_counter() - started,
	)
	return validated


def _validate_scraped_data(
	data: pd.DataFrame, required_columns: list[str]
) -> pd.DataFrame:
	"""Validate the generic standalone table contract before writing output."""
	if data.empty:
		raise ValueError("Scraped dataset is empty after cleaning.")
	missing_columns = sorted(set(required_columns).difference(data.columns))
	if missing_columns:
		fields = ", ".join(missing_columns)
		raise ValueError(f"Transformed table is missing required columns: {fields}.")
	return data


if __name__ == "__main__":
	run_pipeline()