"""Persist independent pipeline snapshots to configured MongoDB collections."""

from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Any

import pandas as pd


class MongoDBOutputError(RuntimeError):
	"""MongoDB output configuration or persistence failure."""


def _load_mongodb_driver():
	try:
		from pymongo import MongoClient
		from pymongo.errors import PyMongoError
	except ImportError as exc:
		raise MongoDBOutputError(
			"MongoDB output requires pymongo; install the project requirements."
		) from exc
	return MongoClient, PyMongoError


def write_mongodb_snapshot(
	data: pd.DataFrame,
	config: Mapping[str, Any],
	*,
	collection_key: str,
) -> int:
	"""Atomically replace one configured output collection with a DataFrame.

	Dotted column names such as ``address.city`` are converted into nested BSON
	documents. Each collection represents a current snapshot, not run history.
	"""
	output_settings = config.get("output", {}).get("mongodb", {})
	if not output_settings.get("enabled", False):
		return 0

	try:
		connection = config["sources"]["mongodb"]
		uri = connection.get("uri", "")
		uri_env = connection.get("uri_env", "MONGODB_URI")
		database_name = connection["database"]
		timeout_ms = connection.get("server_selection_timeout_ms", 5000)
		collection_name = output_settings["collections"][collection_key]
	except (KeyError, AttributeError, TypeError) as exc:
		raise MongoDBOutputError(
			"MongoDB output requires sources.mongodb connection settings and "
			f"output.mongodb.collections.{collection_key}."
		) from exc

	if not isinstance(collection_name, str) or not collection_name.strip():
		raise MongoDBOutputError(
			f"MongoDB output collection '{collection_key}' must be a non-empty string."
		)

	uri = os.environ.get(uri_env, "") or uri
	if not isinstance(uri, str) or not uri.strip():
		raise MongoDBOutputError(
			"Set sources.mongodb.uri or its configured MongoDB URI environment variable."
		)

	staging_name = f"_{collection_name}_staging"
	client = None
	mongo_client, mongo_error = _load_mongodb_driver()
	try:
		client = mongo_client(uri, serverSelectionTimeoutMS=timeout_ms)
		client.admin.command("ping")
		database = client[database_name]
		database.drop_collection(staging_name)
		staging = database.create_collection(staging_name)
		documents = [_to_document(record) for record in data.to_dict(orient="records")]
		if documents:
			staging.insert_many(documents)
		staging.rename(collection_name, dropTarget=True)
		return len(documents)
	except mongo_error as exc:
		raise MongoDBOutputError(
			f"Cannot replace MongoDB output collection '{collection_name}': {exc}"
		) from exc
	finally:
		if client is not None:
			client.close()


def _to_document(record: Mapping[str, Any]) -> dict[str, Any]:
	document: dict[str, Any] = {}
	for key, value in record.items():
		parts = str(key).split(".")
		current = document
		for part in parts[:-1]:
			child = current.setdefault(part, {})
			if not isinstance(child, dict):
				raise MongoDBOutputError(
					f"Cannot convert conflicting dotted MongoDB field '{key}'."
				)
			current = child
		current[parts[-1]] = _native_value(value)
	return document


def _native_value(value: Any) -> Any:
	if not pd.api.types.is_scalar(value):
		return value
	if pd.isna(value):
		return None
	if hasattr(value, "item"):
		return value.item()
	return value