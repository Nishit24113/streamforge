"""
Tests for the StreamForge Python SDK decorators.

Covers @streamforge_event, @streamforge_track, and the configure() helper.
Run with: pytest tests/unit/test_sdk_decorators.py -v
"""

import time
from unittest.mock import patch, MagicMock, ANY

import pytest

from streamforge.decorators import (
    streamforge_event,
    streamforge_track,
    configure,
    _get_client,
    _default_client,
)
import streamforge.decorators as dec_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_default_client():
    """Reset the module-level default client."""
    dec_module._default_client = None


# ---------------------------------------------------------------------------
# configure()
# ---------------------------------------------------------------------------

class TestConfigure:

    def setup_method(self):
        _reset_default_client()

    def teardown_method(self):
        _reset_default_client()

    def test_configure_sets_default_client(self):
        client = configure(api_url="https://api.example.com")
        assert client is not None
        assert dec_module._default_client is client

    def test_configure_returns_client(self):
        client = configure(api_url="https://api.example.com", org_id="my-org")
        assert client.api_url == "https://api.example.com"
        assert client.org_id == "my-org"

    def test_get_client_auto_creates(self):
        _reset_default_client()
        client = _get_client()
        assert client is not None
        assert dec_module._default_client is client


# ---------------------------------------------------------------------------
# @streamforge_event
# ---------------------------------------------------------------------------

class TestStreamforgeEvent:

    def setup_method(self):
        _reset_default_client()

    def teardown_method(self):
        _reset_default_client()

    @patch.object(dec_module, "_get_client")
    def test_captures_return_value_dict(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_event("my-pipe", event_type="custom_event")
        def my_func():
            return {"key": "value", "count": 42}

        result = my_func()
        assert result == {"key": "value", "count": 42}

        mock_client.ingest.assert_called_once()
        call_args = mock_client.ingest.call_args
        assert call_args[0][0] == "my-pipe"
        events = call_args[0][1]
        assert len(events) == 1
        assert events[0]["key"] == "value"
        assert events[0]["count"] == 42
        assert events[0]["event_type"] == "custom_event"
        assert "timestamp" in events[0]

    @patch.object(dec_module, "_get_client")
    def test_captures_non_dict_return(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_event("my-pipe")
        def my_func():
            return 42

        result = my_func()
        assert result == 42

        events = mock_client.ingest.call_args[0][1]
        assert events[0]["result"] == 42

    @patch.object(dec_module, "_get_client")
    def test_does_not_interfere_with_return_value(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_event("pipe")
        def compute():
            return {"answer": 42}

        result = compute()
        assert result == {"answer": 42}

    @patch.object(dec_module, "_get_client")
    def test_swallows_ingestion_errors(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.ingest.side_effect = Exception("Network error")
        mock_get_client.return_value = mock_client

        @streamforge_event("pipe")
        def compute():
            return "ok"

        # Should NOT raise even though ingest fails
        result = compute()
        assert result == "ok"

    @patch.object(dec_module, "_get_client")
    def test_default_event_type(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_event("pipe")
        def my_func():
            return {"data": 1}

        my_func()
        events = mock_client.ingest.call_args[0][1]
        assert events[0]["event_type"] == "function_result"

    @patch.object(dec_module, "_get_client")
    def test_preserves_existing_event_type(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_event("pipe", event_type="default_type")
        def my_func():
            return {"event_type": "already_set", "data": 1}

        my_func()
        events = mock_client.ingest.call_args[0][1]
        # setdefault should not overwrite existing event_type
        assert events[0]["event_type"] == "already_set"


# ---------------------------------------------------------------------------
# @streamforge_track
# ---------------------------------------------------------------------------

class TestStreamforgeTrack:

    def setup_method(self):
        _reset_default_client()

    def teardown_method(self):
        _reset_default_client()

    @patch.object(dec_module, "_get_client")
    def test_captures_timing_on_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_track("pipe")
        def slow_func():
            return "done"

        result = slow_func()
        assert result == "done"

        mock_client.ingest.assert_called_once()
        events = mock_client.ingest.call_args[0][1]
        event = events[0]
        assert event["event_type"] == "function_call"
        assert event["success"] is True
        assert "duration_ms" in event
        assert isinstance(event["duration_ms"], int)
        assert "timestamp" in event
        assert "function" in event
        assert "module" in event

    @patch.object(dec_module, "_get_client")
    def test_captures_failure(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_track("pipe")
        def failing_func():
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            failing_func()

        events = mock_client.ingest.call_args[0][1]
        event = events[0]
        assert event["success"] is False
        assert event["error"] == "bad input"
        assert event["error_type"] == "ValueError"

    @patch.object(dec_module, "_get_client")
    def test_fields_parameter_extracts_values(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_track("pipe", fields=["user_count", "region"])
        def get_metrics():
            return {"user_count": 150, "region": "us-west-2", "secret": "hidden"}

        result = get_metrics()
        assert result == {"user_count": 150, "region": "us-west-2", "secret": "hidden"}

        events = mock_client.ingest.call_args[0][1]
        event = events[0]
        assert event["user_count"] == 150
        assert event["region"] == "us-west-2"
        assert "secret" not in event

    @patch.object(dec_module, "_get_client")
    def test_fields_parameter_ignores_missing_keys(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_track("pipe", fields=["nonexistent"])
        def get_data():
            return {"actual": "value"}

        get_data()
        events = mock_client.ingest.call_args[0][1]
        event = events[0]
        assert "nonexistent" not in event

    @patch.object(dec_module, "_get_client")
    def test_fields_parameter_ignored_for_non_dict_result(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_track("pipe", fields=["count"])
        def get_number():
            return 42

        result = get_number()
        assert result == 42

        # Should not raise even though result is not a dict
        events = mock_client.ingest.call_args[0][1]
        assert "count" not in events[0]

    @patch.object(dec_module, "_get_client")
    def test_track_swallows_ingestion_errors(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.ingest.side_effect = Exception("Network error")
        mock_get_client.return_value = mock_client

        @streamforge_track("pipe")
        def my_func():
            return "ok"

        # Should not raise
        result = my_func()
        assert result == "ok"

    @patch.object(dec_module, "_get_client")
    def test_preserves_function_metadata(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_track("pipe")
        def documented_func():
            """This is my docstring."""
            return True

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is my docstring."

    @patch.object(dec_module, "_get_client")
    def test_event_preserves_function_metadata(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        @streamforge_event("pipe")
        def documented_func():
            """Event docstring."""
            return True

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "Event docstring."
