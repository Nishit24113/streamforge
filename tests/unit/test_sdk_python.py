"""
Comprehensive tests for the StreamForge Python SDK client.

Uses unittest.mock to mock all HTTP calls via requests.Session.
Run with: pytest tests/unit/test_sdk_python.py -v
"""

import os
import json
import time
from unittest.mock import patch, MagicMock, call, mock_open

import pytest

from streamforge.client import StreamForge, StreamForgeError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None, raise_for_status=None):
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    if raise_for_status:
        resp.raise_for_status.side_effect = raise_for_status
    return resp


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestClientInit:
    """Tests for StreamForge client construction."""

    def test_init_with_explicit_url(self):
        client = StreamForge(api_url="https://api.example.com/v1")
        assert client.api_url == "https://api.example.com/v1"

    def test_init_strips_trailing_slash(self):
        client = StreamForge(api_url="https://api.example.com/v1/")
        assert client.api_url == "https://api.example.com/v1"

    @patch.dict(os.environ, {"STREAMFORGE_API_URL": "https://env.example.com"})
    def test_init_from_env_var(self):
        client = StreamForge()
        assert client.api_url == "https://env.example.com"

    @patch.dict(os.environ, {
        "STREAMFORGE_API_URL": "https://env.example.com",
        "STREAMFORGE_API_KEY": "env-key-123",
        "STREAMFORGE_ORG_ID": "org-from-env",
    })
    def test_init_all_env_vars(self):
        client = StreamForge()
        assert client.api_url == "https://env.example.com"
        assert client.api_key == "env-key-123"
        assert client.org_id == "org-from-env"

    def test_init_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            client = StreamForge()
            assert client.api_url == ""
            assert client.api_key is None
            assert client.org_id == "default"
            assert client.timeout == 30
            assert client.max_retries == 3

    def test_analytics_url_defaults_to_api_url(self):
        client = StreamForge(api_url="https://api.example.com")
        assert client.analytics_url == "https://api.example.com"

    def test_analytics_url_explicit(self):
        client = StreamForge(
            api_url="https://api.example.com",
            analytics_url="https://analytics.example.com/",
        )
        assert client.analytics_url == "https://analytics.example.com"


# ---------------------------------------------------------------------------
# Org-ID header
# ---------------------------------------------------------------------------

class TestOrgIdHeader:
    """Verify org_id is sent on every request."""

    def test_org_id_header_set_on_session(self):
        client = StreamForge(api_url="https://api.example.com", org_id="my-org")
        assert client._session.headers["X-Org-Id"] == "my-org"

    def test_api_key_header_set_when_provided(self):
        client = StreamForge(api_url="https://api.example.com", api_key="secret")
        assert client._session.headers["X-Api-Key"] == "secret"

    def test_api_key_header_absent_when_not_provided(self):
        client = StreamForge(api_url="https://api.example.com")
        assert "X-Api-Key" not in client._session.headers


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    """Test 'with' statement support."""

    def test_context_manager_closes_session(self):
        with StreamForge(api_url="https://api.example.com") as client:
            assert client._session is not None
            session = client._session
        session.close.assert_called_once()


# ---------------------------------------------------------------------------
# health()
# ---------------------------------------------------------------------------

class TestHealth:

    @patch("streamforge.client.requests.Session")
    def test_health_sends_get(self, MockSession):
        mock_session = MockSession.return_value
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(200, {"status": "ok"})

        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://api.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = 3
        client._session = mock_session

        result = client.health()
        mock_session.request.assert_called_once_with(
            "GET", "https://api.example.com/health", timeout=30
        )
        assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# ingest()
# ---------------------------------------------------------------------------

class TestIngest:

    def _make_client(self, mock_session):
        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://api.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = 3
        client._session = mock_session
        return client

    def test_ingest_sends_post_with_events(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, {"accepted": 2})
        client = self._make_client(mock_session)

        events = [{"user": "a"}, {"user": "b"}]
        result = client.ingest("my-pipeline", events)

        mock_session.request.assert_called_once_with(
            "POST",
            "https://api.example.com/ingest",
            json={"pipeline": "my-pipeline", "events": events},
            timeout=30,
        )
        assert result == {"accepted": 2}


# ---------------------------------------------------------------------------
# ingest_batch()
# ---------------------------------------------------------------------------

class TestIngestBatch:

    def _make_client(self, mock_session):
        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://api.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = 3
        client._session = mock_session
        return client

    def test_batch_splits_correctly(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, {"accepted": 2})
        client = self._make_client(mock_session)

        events = [{"i": n} for n in range(5)]
        results = client.ingest_batch("pipe", events, batch_size=2)

        # 5 events with batch_size=2 => 3 batches (2, 2, 1)
        assert len(results) == 3
        assert mock_session.request.call_count == 3

    def test_batch_single_batch(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, {"accepted": 3})
        client = self._make_client(mock_session)

        events = [{"i": n} for n in range(3)]
        results = client.ingest_batch("pipe", events, batch_size=500)

        assert len(results) == 1
        assert mock_session.request.call_count == 1

    def test_batch_empty_events(self):
        mock_session = MagicMock()
        client = self._make_client(mock_session)

        results = client.ingest_batch("pipe", [])
        assert results == []
        mock_session.request.assert_not_called()


# ---------------------------------------------------------------------------
# Pipeline CRUD
# ---------------------------------------------------------------------------

class TestPipelines:

    def _make_client(self, mock_session):
        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://api.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = 3
        client._session = mock_session
        return client

    def test_create_pipeline(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, {"id": "p-1", "name": "test"})
        client = self._make_client(mock_session)

        config = {"name": "test", "schema": {"type": "object"}}
        result = client.create_pipeline(config)

        mock_session.request.assert_called_once_with(
            "POST", "https://api.example.com/pipelines", json=config, timeout=30
        )
        assert result["id"] == "p-1"

    def test_list_pipelines(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, [{"id": "p-1"}, {"id": "p-2"}])
        client = self._make_client(mock_session)

        result = client.list_pipelines()
        mock_session.request.assert_called_once_with(
            "GET", "https://api.example.com/pipelines", timeout=30
        )
        assert len(result) == 2

    def test_get_pipeline(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, {"id": "p-1", "name": "clicks"})
        client = self._make_client(mock_session)

        result = client.get_pipeline("p-1")
        mock_session.request.assert_called_once_with(
            "GET", "https://api.example.com/pipelines/p-1", timeout=30
        )
        assert result["name"] == "clicks"

    def test_get_runs(self):
        mock_session = MagicMock()
        runs = [{"id": "r-1", "status": "completed"}]
        mock_session.request.return_value = _mock_response(200, runs)
        client = self._make_client(mock_session)

        result = client.get_runs("p-1")
        mock_session.request.assert_called_once_with(
            "GET", "https://api.example.com/pipelines/p-1/runs", timeout=30
        )
        assert result[0]["status"] == "completed"


# ---------------------------------------------------------------------------
# upload_file()
# ---------------------------------------------------------------------------

class TestUploadFile:

    @patch("streamforge.client.requests.put")
    def test_upload_file_csv(self, mock_put):
        mock_session = MagicMock()
        presigned = {"upload_url": "https://s3.example.com/presigned"}
        mock_session.request.return_value = _mock_response(200, presigned)
        mock_put.return_value = _mock_response(200)

        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://api.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = 3
        client._session = mock_session

        with patch("builtins.open", mock_open(read_data=b"col1,col2\na,b\n")):
            result = client.upload_file("p-1", "/data/events.csv")

        # Verify presigned URL request
        mock_session.request.assert_called_once_with(
            "POST",
            "https://api.example.com/upload",
            json={"pipeline": "p-1", "filename": "events.csv", "content_type": "text/csv"},
            timeout=30,
        )
        # Verify PUT to S3
        mock_put.assert_called_once()
        put_args = mock_put.call_args
        assert put_args[0][0] == "https://s3.example.com/presigned"
        assert put_args[1]["headers"]["Content-Type"] == "text/csv"
        assert result == presigned

    @patch("streamforge.client.requests.put")
    def test_upload_file_json(self, mock_put):
        mock_session = MagicMock()
        presigned = {"upload_url": "https://s3.example.com/presigned"}
        mock_session.request.return_value = _mock_response(200, presigned)
        mock_put.return_value = _mock_response(200)

        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://api.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = 3
        client._session = mock_session

        with patch("builtins.open", mock_open(read_data=b'[{"a":1}]')):
            result = client.upload_file("p-1", "/data/events.json")

        post_call = mock_session.request.call_args
        assert post_call[1]["json"]["content_type"] == "application/json"


# ---------------------------------------------------------------------------
# query() — auto-poll
# ---------------------------------------------------------------------------

class TestQuery:

    def _make_client(self, mock_session):
        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://analytics.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = 3
        client._session = mock_session
        return client

    @patch("streamforge.client.time.sleep")
    def test_query_immediate_completion(self, mock_sleep):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            200, {"status": "completed", "rows": [{"x": 1}]}
        )
        client = self._make_client(mock_session)

        result = client.query("SELECT 1")
        assert result["status"] == "completed"
        assert result["rows"] == [{"x": 1}]
        # No polling needed
        mock_sleep.assert_not_called()

    @patch("streamforge.client.time.sleep")
    @patch("streamforge.client.time.time")
    def test_query_polls_until_done(self, mock_time, mock_sleep):
        # Simulate: first call returns pending, then polling returns completed
        mock_session = MagicMock()
        mock_session.request.side_effect = [
            _mock_response(200, {"status": "running", "query_id": "q-1"}),
            _mock_response(200, {"status": "running", "query_id": "q-1"}),
            _mock_response(200, {"status": "completed", "rows": [{"x": 42}]}),
        ]
        # time.time() returns increasing values so the while loop works
        mock_time.side_effect = [0, 1, 2, 3]
        client = self._make_client(mock_session)

        result = client.query("SELECT * FROM t", poll_interval=0.01, max_wait=60)
        assert result["status"] == "completed"
        assert result["rows"] == [{"x": 42}]

    @patch("streamforge.client.time.sleep")
    @patch("streamforge.client.time.time")
    def test_query_timeout(self, mock_time, mock_sleep):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            200, {"status": "running", "query_id": "q-1"}
        )
        # Make time.time() jump past max_wait immediately after first poll
        mock_time.side_effect = [0, 100]
        client = self._make_client(mock_session)

        with pytest.raises(StreamForgeError, match="timed out"):
            client.query("SELECT 1", max_wait=5)


# ---------------------------------------------------------------------------
# get_stats() / get_anomalies()
# ---------------------------------------------------------------------------

class TestAnalytics:

    def _make_client(self, mock_session):
        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://analytics.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = 3
        client._session = mock_session
        return client

    def test_get_stats(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, {"events_today": 1500})
        client = self._make_client(mock_session)

        result = client.get_stats()
        mock_session.request.assert_called_once_with(
            "GET", "https://analytics.example.com/stats", timeout=30
        )
        assert result["events_today"] == 1500

    def test_get_anomalies_all(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, [{"severity": "high"}])
        client = self._make_client(mock_session)

        result = client.get_anomalies()
        mock_session.request.assert_called_once_with(
            "GET", "https://analytics.example.com/anomalies", timeout=30
        )
        assert len(result) == 1

    def test_get_anomalies_with_pipeline_filter(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(200, [])
        client = self._make_client(mock_session)

        client.get_anomalies(pipeline_id="p-1")
        url_called = mock_session.request.call_args[0][1]
        assert "pipeline_id=p-1" in url_called


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def _make_client(self, mock_session, max_retries=1):
        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://api.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = max_retries
        client._session = mock_session
        return client

    def test_4xx_raises_error_with_status(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            404, {"error": "Pipeline not found"}
        )
        client = self._make_client(mock_session)

        with pytest.raises(StreamForgeError) as exc_info:
            client.health()
        assert exc_info.value.status_code == 404
        assert "Pipeline not found" in str(exc_info.value)

    def test_5xx_raises_error(self):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            500, {"error": "Internal server error"}
        )
        client = self._make_client(mock_session)

        with pytest.raises(StreamForgeError) as exc_info:
            client.health()
        assert exc_info.value.status_code == 500

    def test_connection_error_raises_after_retries(self):
        import requests as real_requests

        mock_session = MagicMock()
        mock_session.request.side_effect = real_requests.exceptions.ConnectionError("refused")
        client = self._make_client(mock_session, max_retries=1)

        with pytest.raises(StreamForgeError, match="Failed after 1 retries"):
            client.health()

    def test_error_response_body_preserved(self):
        mock_session = MagicMock()
        body = {"error": "Bad request", "details": {"field": "missing"}}
        mock_session.request.return_value = _mock_response(400, body)
        client = self._make_client(mock_session)

        with pytest.raises(StreamForgeError) as exc_info:
            client.health()
        assert exc_info.value.response == body


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:

    def _make_client(self, mock_session, max_retries=3):
        client = StreamForge.__new__(StreamForge)
        client.api_url = "https://api.example.com"
        client.analytics_url = "https://api.example.com"
        client.api_key = None
        client.org_id = "default"
        client.timeout = 30
        client.max_retries = max_retries
        client._session = mock_session
        return client

    @patch("streamforge.client.time.sleep")
    def test_429_retries_with_backoff(self, mock_sleep):
        mock_session = MagicMock()
        mock_session.request.side_effect = [
            _mock_response(429, {"error": "rate limited"}),
            _mock_response(429, {"error": "rate limited"}),
            _mock_response(200, {"status": "ok"}),
        ]
        client = self._make_client(mock_session, max_retries=3)

        result = client.health()
        assert result == {"status": "ok"}
        assert mock_session.request.call_count == 3
        # Exponential backoff: 2^0=1, 2^1=2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch("streamforge.client.time.sleep")
    def test_connection_error_retries(self, mock_sleep):
        import requests as real_requests

        mock_session = MagicMock()
        mock_session.request.side_effect = [
            real_requests.exceptions.ConnectionError("refused"),
            _mock_response(200, {"status": "ok"}),
        ]
        client = self._make_client(mock_session, max_retries=2)

        result = client.health()
        assert result == {"status": "ok"}
        assert mock_session.request.call_count == 2
        mock_sleep.assert_called_once_with(1)  # 2^0

    @patch("streamforge.client.time.sleep")
    def test_429_exhausts_retries(self, mock_sleep):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(429, {"error": "rate limited"})
        client = self._make_client(mock_session, max_retries=2)

        with pytest.raises(StreamForgeError, match="Failed after 2 retries"):
            client.health()
        assert mock_session.request.call_count == 2
