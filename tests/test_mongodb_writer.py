from __future__ import annotations

import pandas as pd
import pytest

from app.output.mongodb_writer import (
	MongoDBOutputError,
	write_mongodb_snapshot,
)


def _config(enabled=True):
	return {
		"sources": {
			"mongodb": {
				"uri": "mongodb://localhost:27017",
				"uri_env": "TEST_MONGODB_URI",
				"database": "student_pipeline",
				"server_selection_timeout_ms": 2500,
			}
		},
		"output": {
			"mongodb": {
				"enabled": enabled,
				"collections": {
					"students": "processed_students",
					"rejected": "rejected_students",
					"web": "scraped_users",
				},
			}
		},
	}


def test_writer_atomically_replaces_snapshot_and_nests_dotted_columns(monkeypatch):
	client = _FakeClient()
	database = client.database
	database.collections["scraped_users"] = [{"old": True}]
	monkeypatch.setattr(
		"app.output.mongodb_writer._load_mongodb_driver",
		lambda: (_FakeClientFactory(client), RuntimeError),
	)
	frame = pd.DataFrame(
		[
			{
				"id": 1,
				"address.city": "Gwenborough",
				"address.geo.lat": -37.3,
				"email": pd.NA,
			}
		]
	)

	count = write_mongodb_snapshot(frame, _config(), collection_key="web")

	assert count == 1
	assert database.collections["scraped_users"] == [
		{
			"id": 1,
			"address": {"city": "Gwenborough", "geo": {"lat": -37.3}},
			"email": None,
		}
	]
	assert "_scraped_users_staging" not in database.collections
	assert client.pinged
	assert client.closed


def test_empty_frame_replaces_collection_with_empty_snapshot(monkeypatch):
	client = _FakeClient()
	client.database.collections["rejected_students"] = [{"stale": True}]
	monkeypatch.setattr(
		"app.output.mongodb_writer._load_mongodb_driver",
		lambda: (_FakeClientFactory(client), RuntimeError),
	)

	count = write_mongodb_snapshot(
		pd.DataFrame(columns=["student_id"]),
		_config(),
		collection_key="rejected",
	)

	assert count == 0
	assert client.database.collections["rejected_students"] == []
	assert client.closed


def test_disabled_mongodb_output_does_not_connect(monkeypatch):
	monkeypatch.setattr(
		"app.output.mongodb_writer._load_mongodb_driver",
		lambda: pytest.fail("Disabled MongoDB output must not load the driver."),
	)

	assert (
		write_mongodb_snapshot(
			pd.DataFrame([{"student_id": 1}]),
			_config(enabled=False),
			collection_key="students",
		)
		== 0
	)


def test_missing_mongodb_output_collection_is_reported():
	config = _config()
	del config["output"]["mongodb"]["collections"]["web"]

	with pytest.raises(MongoDBOutputError, match="collections.web"):
		write_mongodb_snapshot(
			pd.DataFrame([{"id": 1}]), config, collection_key="web"
		)


class _FakeAdmin:
	def __init__(self, client):
		self.client = client

	def command(self, name):
		assert name == "ping"
		self.client.pinged = True


class _FakeCollection:
	def __init__(self, database, name):
		self.database = database
		self.name = name

	def insert_many(self, documents):
		self.database.collections[self.name] = documents

	def rename(self, target, dropTarget=False):
		assert dropTarget is True
		self.database.collections.pop(target, None)
		self.database.collections[target] = self.database.collections.pop(self.name)
		return _FakeCollection(self.database, target)


class _FakeDatabase:
	def __init__(self):
		self.collections = {}

	def drop_collection(self, name):
		self.collections.pop(name, None)

	def create_collection(self, name):
		self.collections[name] = []
		return _FakeCollection(self, name)


class _FakeClient:
	def __init__(self):
		self.database = _FakeDatabase()
		self.admin = _FakeAdmin(self)
		self.pinged = False
		self.closed = False

	def __getitem__(self, name):
		assert name == "student_pipeline"
		return self.database

	def close(self):
		self.closed = True


class _FakeClientFactory:
	def __init__(self, client):
		self.client = client

	def __call__(self, uri, **kwargs):
		assert uri == "mongodb://localhost:27017"
		assert kwargs == {"serverSelectionTimeoutMS": 2500}
		return self.client