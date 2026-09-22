"""Shared fixtures for StreamForge integration tests.

Provides mock AWS services (S3, DynamoDB) that store data in memory,
pipeline config loaders, and sample event generators for each pipeline type.
"""

import io
import json
import os
import importlib.util
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[2]
PIPELINES_DIR = ROOT_DIR / "pipelines"
SERVICES_DIR = ROOT_DIR / "services"

# ---------------------------------------------------------------------------
# Dynamic handler loader
# ---------------------------------------------------------------------------


def _load_handler(service_path: str):
    """Import a Lambda handler module by its relative path under services/.

    Because the handler directories have no __init__.py (they are deployed as
    standalone Lambda packages), we use importlib to load them dynamically.
    """
    full_path = SERVICES_DIR / service_path / "handler.py"
    module_name = service_path.replace("/", "_").replace("\\", "_") + "_handler"

    spec = importlib.util.spec_from_file_location(module_name, str(full_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Mock S3
# ---------------------------------------------------------------------------


class MockS3:
    """In-memory S3 mock that supports get_object, put_object, and
    generate_presigned_url.
    """

    def __init__(self):
        self.store: dict[str, bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body, ContentType: str = ""):
        if isinstance(Body, str):
            Body = Body.encode("utf-8")
        self.store[f"{Bucket}/{Key}"] = Body

    def get_object(self, *, Bucket: str, Key: str):
        full_key = f"{Bucket}/{Key}"
        if full_key not in self.store:
            raise Exception(f"NoSuchKey: {full_key}")
        body = io.BytesIO(self.store[full_key])
        return {"Body": body}

    def generate_presigned_url(self, method, Params=None, ExpiresIn=3600):
        return "https://mock-presigned-url.example.com/upload"

    # Convenience helpers for tests ------------------------------------------

    def get_json(self, bucket: str, key: str):
        """Return parsed JSON for a stored object."""
        obj = self.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))

    def list_keys(self, prefix: str = ""):
        """Return all stored keys (optionally filtered by prefix)."""
        return [k for k in self.store if k.startswith(prefix)]


# ---------------------------------------------------------------------------
# Mock DynamoDB table
# ---------------------------------------------------------------------------


class MockDynamoTable:
    """In-memory DynamoDB table mock supporting put_item, get_item,
    update_item, query, and scan.
    """

    def __init__(self):
        self.items: list[dict] = {}
        self._store: dict[str, dict] = {}

    def put_item(self, Item: dict = None, **kwargs):
        item = Item or kwargs.get("Item", {})
        key = self._make_key(item)
        self._store[key] = item

    def get_item(self, Key: dict = None, **kwargs):
        key_dict = Key or kwargs.get("Key", {})
        key = self._make_key(key_dict)
        item = self._store.get(key)
        result = {}
        if item:
            result["Item"] = item
        return result

    def update_item(self, **kwargs):
        # No-op for test purposes; we only need the handlers not to crash.
        pass

    def query(self, **kwargs):
        return {"Items": [], "Count": 0}

    def scan(self, **kwargs):
        return {"Items": list(self._store.values()), "Count": len(self._store)}

    @staticmethod
    def _make_key(d: dict) -> str:
        return json.dumps(d, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_s3():
    """Provide a fresh in-memory S3 mock."""
    return MockS3()


@pytest.fixture()
def mock_dynamo_table():
    """Provide a fresh in-memory DynamoDB table mock."""
    return MockDynamoTable()


@pytest.fixture()
def mock_alerts_table():
    """Separate DynamoDB table mock for anomaly alerts."""
    return MockDynamoTable()


# ---- Handler module fixtures (patched with mocks) --------------------------


@pytest.fixture()
def validator_handler(mock_s3, mock_dynamo_table):
    """Load the validator handler with mocked AWS services."""
    mod = _load_handler("processing/validator")
    mod.s3 = mock_s3
    mod.run_table = mock_dynamo_table
    mod.DATA_LAKE_BUCKET = BUCKET
    return mod


@pytest.fixture()
def transformer_handler(mock_s3, mock_dynamo_table):
    """Load the transformer handler with mocked AWS services."""
    mod = _load_handler("processing/transformer")
    mod.s3 = mock_s3
    mod.run_table = mock_dynamo_table
    mod.DATA_LAKE_BUCKET = BUCKET
    return mod


@pytest.fixture()
def anomaly_handler(mock_s3, mock_dynamo_table, mock_alerts_table):
    """Load the anomaly-detector handler with mocked AWS services."""
    mod = _load_handler("processing/anomaly-detector")
    mod.s3 = mock_s3
    mod.run_table = mock_dynamo_table
    mod.alerts_table = mock_alerts_table
    mod.DATA_LAKE_BUCKET = BUCKET
    return mod


@pytest.fixture()
def aggregator_handler(mock_s3, mock_dynamo_table):
    """Load the aggregator handler with mocked AWS services."""
    mod = _load_handler("processing/aggregator")
    mod.s3 = mock_s3
    mod.run_table = mock_dynamo_table
    mod.DATA_LAKE_BUCKET = BUCKET
    return mod


# ---- Pipeline config fixtures ----------------------------------------------


def _load_pipeline(name: str) -> dict:
    path = PIPELINES_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture()
def ecommerce_config():
    return _load_pipeline("demo-ecommerce")


@pytest.fixture()
def iot_config():
    return _load_pipeline("demo-iot-sensors")


@pytest.fixture()
def web_analytics_config():
    return _load_pipeline("demo-web-analytics")


# ---- Sample event generators -----------------------------------------------

BUCKET = "test-bucket"
RAW_KEY_PREFIX = "raw/test"


def _seed_events_in_s3(mock_s3_instance, events, pipeline_id="test", run_id="run-001"):
    """Write events JSON to mock S3 and return the s3:// location string."""
    key = f"{RAW_KEY_PREFIX}/{pipeline_id}/{run_id}.json"
    mock_s3_instance.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(events),
        ContentType="application/json",
    )
    return f"s3://{BUCKET}/{key}"


@pytest.fixture()
def seed_events(mock_s3):
    """Return a helper that seeds events into mock S3."""

    def _seed(events, pipeline_id="test", run_id="run-001"):
        return _seed_events_in_s3(mock_s3, events, pipeline_id, run_id)

    return _seed


def make_ecommerce_events(n=10, *, include_invalid=False):
    """Generate sample e-commerce events."""
    now = int(time.time() * 1000)
    events = []
    for i in range(n):
        events.append({
            "event_id": f"evt-ecom-{i:04d}",
            "pipeline_id": "ecommerce-events",
            "timestamp": now + i * 1000,
            "source": "api",
            "event_type": "purchase",
            "user_id": f"user-{i % 5}",
            "action": "Purchase",
            "amount": 25.0 + i * 10,
            "payload": json.dumps({
                "user_id": f"user-{i % 5}",
                "action": "Purchase",
                "amount": 25.0 + i * 10,
                "timestamp": now + i * 1000,
                "currency": "USD",
            }),
        })
    if include_invalid:
        # Missing required field user_id
        events.append({
            "event_id": "evt-ecom-invalid-1",
            "pipeline_id": "ecommerce-events",
            "timestamp": now,
            "source": "api",
            "event_type": "purchase",
            "action": "Purchase",
            "amount": 50.0,
            "payload": json.dumps({
                "action": "Purchase",
                "amount": 50.0,
                "timestamp": now,
            }),
        })
        # Amount out of range
        events.append({
            "event_id": "evt-ecom-invalid-2",
            "pipeline_id": "ecommerce-events",
            "timestamp": now,
            "source": "api",
            "event_type": "purchase",
            "user_id": "user-bad",
            "action": "Purchase",
            "amount": -500,
            "payload": json.dumps({
                "user_id": "user-bad",
                "action": "Purchase",
                "amount": -500,
                "timestamp": now,
            }),
        })
        # Null user_id
        events.append({
            "event_id": "evt-ecom-invalid-3",
            "pipeline_id": "ecommerce-events",
            "timestamp": now,
            "source": "api",
            "event_type": "purchase",
            "user_id": None,
            "action": "Purchase",
            "amount": 10.0,
            "payload": json.dumps({
                "user_id": None,
                "action": "Purchase",
                "amount": 10.0,
                "timestamp": now,
            }),
        })
    return events


def make_iot_events(n=20, *, include_outlier=False):
    """Generate sample IoT sensor events with optional outlier."""
    now = int(time.time() * 1000)
    events = []
    for i in range(n):
        value = 22.0 + (i % 5) * 0.5  # Normal range: 22-24 celsius
        events.append({
            "event_id": f"evt-iot-{i:04d}",
            "pipeline_id": "iot-sensors",
            "timestamp": now + i * 1000,
            "source": "sensor",
            "event_type": "reading",
            "device_id": f"device-{i % 3}",
            "sensor_type": "temperature",
            "value": value,
            "payload": json.dumps({
                "device_id": f"device-{i % 3}",
                "sensor_type": "temperature",
                "value": value,
                "timestamp": now + i * 1000,
            }),
        })
    if include_outlier:
        # Extreme outlier to trigger anomaly detection
        events.append({
            "event_id": "evt-iot-outlier",
            "pipeline_id": "iot-sensors",
            "timestamp": now + n * 1000,
            "source": "sensor",
            "event_type": "reading",
            "device_id": "device-0",
            "sensor_type": "temperature",
            "value": 999.0,
            "payload": json.dumps({
                "device_id": "device-0",
                "sensor_type": "temperature",
                "value": 999.0,
                "timestamp": now + n * 1000,
            }),
        })
    return events


def make_web_analytics_events(n=10):
    """Generate sample web analytics events."""
    now = int(time.time() * 1000)
    pages = ["/home", "/pricing", "/docs", "/about", "/contact"]
    events = []
    for i in range(n):
        events.append({
            "event_id": f"evt-web-{i:04d}",
            "pipeline_id": "web-analytics",
            "timestamp": now + i * 1000,
            "source": "tracker",
            "event_type": "pageview",
            "page_url": pages[i % len(pages)],
            "session_id": f"sess-{i % 4}",
            "ip_address": f"192.168.1.{i}",
            "session_duration": 30 + i * 15,
            "geo": {"country": "US", "city": "Phoenix"},
            "payload": json.dumps({
                "page_url": pages[i % len(pages)],
                "session_id": f"sess-{i % 4}",
                "ip_address": f"192.168.1.{i}",
                "session_duration": 30 + i * 15,
                "timestamp": now + i * 1000,
                "geo": {"country": "US", "city": "Phoenix"},
            }),
        })
    return events
