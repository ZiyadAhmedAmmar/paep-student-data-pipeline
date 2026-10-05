from __future__ import annotations

import pandas as pd
import pytest

from app.sources.mongodb_source import (
	MongoDBSource,
	MongoDBSourceError,
	extract_mongodb,
)


def _config():
	return {
		"sources": {
			"mongodb": {
				"uri": "mongodb://localhost:27017",
				"database": "student_pipeline",
				"collection": "enrollments",
			}
		}
	}


def test_extract_returns_sqlite_compatible_columns_and_closes_client(monkeypatch):
	documents = [
		{
			"_id": "internal-id",
			"student_id": 1001,
			"course_name": "Data Engineering",
			"credit_hours": 3,
			"semester": "2026-Fall",
			"score": 93,
		}
	]
	client = _FakeClient(documents)

	monkeypatch.setattr(
		"app.sources.mongodb_source._load_mongodb_driver",
		lambda: (_FakeClientFactory(client), RuntimeError),
	)

	result = extract_mongodb(_config())

	assert result.to_dict("records") == [
		{
			"student_id": 1001,
			"course_name": "Data Engineering",
			"credit_hours": 3,
			"semester": "2026-Fall",
			"score": 93,
		}
	]
	assert result.columns.tolist() == [
		"student_id", "course_name", "credit_hours", "semester", "score"
	]
	assert client.closed


def test_empty_collection_preserves_sqlite_compatible_schema(monkeypatch):
	client = _FakeClient([])
	monkeypatch.setattr(
		"app.sources.mongodb_source._load_mongodb_driver",
		lambda: (_FakeClientFactory(client), RuntimeError),
	)

	result = MongoDBSource(_config()).extract()

	assert result.empty
	assert result.columns.tolist() == [
		"student_id", "course_name", "credit_hours", "semester", "score"
	]
	assert client.closed


def test_missing_document_fields_are_reported_and_client_is_closed(monkeypatch):
	client = _FakeClient([{"student_id": 1001}])
	monkeypatch.setattr(
		"app.sources.mongodb_source._load_mongodb_driver",
		lambda: (_FakeClientFactory(client), RuntimeError),
	)

	with pytest.raises(MongoDBSourceError, match="course_name"):
		MongoDBSource(_config()).extract()

	assert client.closed


def test_invalid_mongodb_configuration_is_rejected():
	with pytest.raises(MongoDBSourceError, match="uri"):
		MongoDBSource({"sources": {"mongodb": {"uri": ""}}})


def test_mongodb_uri_environment_variable_overrides_configured_uri(monkeypatch):
	monkeypatch.setenv("MONGODB_URI", "mongodb://secure-host:27017")

	source = MongoDBSource(_config())

	assert source.uri == "mongodb://secure-host:27017"


class _FakeCollection:
	def __init__(self, documents):
		self.documents = documents
		self.projection = None

	def find(self, query, projection):
		assert query == {}
		self.projection = projection
		return self.documents


class _FakeDatabase:
	def __init__(self, collection):
		self.collection = collection

	def __getitem__(self, name):
		assert name == "enrollments"
		return self.collection


class _FakeClient:
	def __init__(self, documents):
		self.collection = _FakeCollection(documents)
		self.closed = False

	def __getitem__(self, name):
		assert name == "student_pipeline"
		return _FakeDatabase(self.collection)

	def close(self):
		self.closed = True


class _FakeClientFactory:
	def __init__(self, client):
		self.client = client

	def __call__(self, uri, **kwargs):
		assert uri == "mongodb://localhost:27017"
		assert kwargs["serverSelectionTimeoutMS"] == 5000
		return self.client