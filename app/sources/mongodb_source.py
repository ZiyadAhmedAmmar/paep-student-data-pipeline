"""Extract database-shaped student records from MongoDB."""

from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Any

import pandas as pd

from app.sources.base_source import BaseSource
from app.utils.config_loader import load_config


DATABASE_COLUMNS = [
	"student_id",
	"course_name",
	"credit_hours",
	"semester",
	"score",
]


class MongoDBSourceError(RuntimeError):
	"""MongoDB configuration or extraction failure."""


def _load_mongodb_driver():
	try:
		from pymongo import MongoClient
		from pymongo.errors import PyMongoError
	except ImportError as exc:
		raise MongoDBSourceError(
			"MongoDB support requires pymongo; install the project requirements."
		) from exc
	return MongoClient, PyMongoError


class MongoDBSource(BaseSource):
	"""Read flattened enrollment documents from a configured collection."""

	def __init__(self, config: Mapping[str, Any] | None = None) -> None:
		if config is None:
			config = load_config()

		try:
			settings = config["sources"]["mongodb"]
			configured_uri = settings.get("uri", "")
			self.uri_env = settings.get("uri_env", "MONGODB_URI")
			self.database_name = settings["database"]
			self.collection_name = settings["collection"]
			self.timeout_ms = settings.get("server_selection_timeout_ms", 5000)
		except (KeyError, TypeError) as exc:
			raise MongoDBSourceError(
				"MongoDB configuration requires uri, database, and collection."
			) from exc

		if not isinstance(self.uri_env, str) or not self.uri_env.strip():
			raise MongoDBSourceError("sources.mongodb.uri_env must be a non-empty string.")
		environment_uri = os.environ.get(self.uri_env)
		self.uri = environment_uri or configured_uri
		if not isinstance(self.uri, str) or not self.uri.strip():
			raise MongoDBSourceError(
				"Set sources.mongodb.uri or the configured MongoDB URI environment variable."
			)
		for name, value in (
			("database", self.database_name),
			("collection", self.collection_name),
		):
			if not isinstance(value, str) or not value.strip():
				raise MongoDBSourceError(
					f"sources.mongodb.{name} must be a non-empty string."
				)
		if (
			isinstance(self.timeout_ms, bool)
			or not isinstance(self.timeout_ms, int)
			or self.timeout_ms <= 0
		):
			raise MongoDBSourceError(
				"sources.mongodb.server_selection_timeout_ms must be a positive integer."
			)

	def extract(self) -> pd.DataFrame:
		mongo_client, mongo_error = _load_mongodb_driver()
		client = None
		try:
			client = mongo_client(
				self.uri,
				serverSelectionTimeoutMS=self.timeout_ms,
			)
			documents = list(
				client[self.database_name][self.collection_name].find({}, {"_id": 0})
			)
		except mongo_error as exc:
			raise MongoDBSourceError(f"Cannot extract records from MongoDB: {exc}") from exc
		finally:
			if client is not None:
				client.close()

		if not documents:
			return pd.DataFrame(columns=DATABASE_COLUMNS)

		frame = pd.DataFrame.from_records(documents)
		missing_columns = sorted(set(DATABASE_COLUMNS).difference(frame.columns))
		if missing_columns:
			fields = ", ".join(missing_columns)
			raise MongoDBSourceError(
				f"MongoDB documents are missing required fields: {fields}."
			)
		return frame.loc[:, DATABASE_COLUMNS]


def extract_mongodb(config: Mapping[str, Any] | None = None) -> pd.DataFrame:
	"""Return MongoDB records in the same schema as the SQLite source."""
	return MongoDBSource(config).extract()