"""Extract a selected HTML table from a configured web page."""

from __future__ import annotations

from collections.abc import Mapping
from html.parser import HTMLParser
from numbers import Real
from typing import Any

import pandas as pd
import requests

from app.sources.base_source import BaseSource


class WebScrapingSourceError(RuntimeError):
	"""Web page request or table extraction failure."""


class _HTMLTableParser(HTMLParser):
	"""Collect rows and header cells from HTML tables."""

	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.tables: list[list[tuple[bool, list[str]]]] = []
		self._table: list[tuple[bool, list[str]]] | None = None
		self._row: list[str] | None = None
		self._cell: list[str] | None = None
		self._header_cell = False

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag == "table" and self._table is None:
			self._table = []
		elif tag == "tr" and self._table is not None:
			self._row = []
		elif tag in {"th", "td"} and self._row is not None:
			self._cell = []
			self._header_cell = tag == "th"

	def handle_data(self, data: str) -> None:
		if self._cell is not None:
			self._cell.append(data)

	def handle_endtag(self, tag: str) -> None:
		if tag in {"th", "td"} and self._cell is not None and self._row is not None:
			self._row.append(" ".join("".join(self._cell).split()))
			self._cell = None
		elif tag == "tr" and self._row is not None and self._table is not None:
			self._table.append((self._header_cell, self._row))
			self._row = None
			self._header_cell = False
		elif tag == "table" and self._table is not None:
			self.tables.append(self._table)
			self._table = None


class WebScrapingSource(BaseSource):
	"""Fetch one HTML table and optionally rename its columns."""

	def __init__(self, config: Mapping[str, Any]) -> None:
		try:
			self.url = config["url"]
			self.timeout_seconds = config.get("timeout_seconds", 10)
			self.table_index = config.get("table_index", 0)
			self.column_mapping = config.get("column_mapping", {})
		except (KeyError, TypeError) as exc:
			raise WebScrapingSourceError(
				"Scraping configuration requires a url."
			) from exc

		if not isinstance(self.url, str) or not self.url.strip():
			raise WebScrapingSourceError("scraping.url must be a non-empty string.")
		if (
			isinstance(self.timeout_seconds, bool)
			or not isinstance(self.timeout_seconds, Real)
			or self.timeout_seconds <= 0
		):
			raise WebScrapingSourceError(
				"scraping.timeout_seconds must be a positive number."
			)
		if (
			isinstance(self.table_index, bool)
			or not isinstance(self.table_index, int)
			or self.table_index < 0
		):
			raise WebScrapingSourceError(
				"scraping.table_index must be a non-negative integer."
			)
		if not isinstance(self.column_mapping, Mapping) or not all(
			isinstance(source, str) and isinstance(target, str)
			for source, target in self.column_mapping.items()
		):
			raise WebScrapingSourceError(
				"scraping.column_mapping must map column names to column names."
			)

	def extract(self) -> pd.DataFrame:
		try:
			response = requests.get(self.url, timeout=float(self.timeout_seconds))
			response.raise_for_status()
		except requests.RequestException as exc:
			raise WebScrapingSourceError(
				f"Cannot fetch scraping page '{self.url}': {exc}"
			) from exc

		parser = _HTMLTableParser()
		parser.feed(response.text)
		tables = parser.tables

		if self.table_index >= len(tables):
			raise WebScrapingSourceError(
				f"HTML table index {self.table_index} is unavailable; "
				f"the page contains {len(tables)} table(s)."
			)

		rows = list(tables[self.table_index])
		if not rows:
			raise WebScrapingSourceError("The selected HTML table is empty.")
		header_index = next(
			(index for index, (is_header, _) in enumerate(rows) if is_header), None
		)
		if header_index is None:
			columns = [f"column_{index}" for index in range(len(rows[0][1]))]
		else:
			_, columns = rows.pop(header_index)
		values = [row for _, row in rows]
		values = [row[: len(columns)] + [""] * max(0, len(columns) - len(row)) for row in values]
		frame = pd.DataFrame(values, columns=columns).rename(
			columns=dict(self.column_mapping)
		)
		if frame.empty:
			raise WebScrapingSourceError("The selected HTML table is empty.")
		return frame