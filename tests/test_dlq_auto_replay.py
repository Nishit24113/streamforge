"""
Tests for scheduled DLQ auto-replay.

Verify retry eligibility, exponential backoff timing, attempt tracking,
exhaustion, and the idle reset path. The underlying DLQReplayService is mocked.
"""

import sys
from datetime import datetime, timedelta
import pytest
from unittest.mock import MagicMock, patch

# Stub aws_lambda_powertools so the module imports without the Lambda runtime dep
if 'aws_lambda_powertools' not in sys.modules:
    powertools_stub = MagicMock()
    powertools_stub.Logger = MagicMock(return_value=MagicMock())
    sys.modules['aws_lambda_powertools'] = powertools_stub


@pytest.fixture
def scheduler():
    with patch('boto3.client'), patch('boto3.resource') as resource:
        attempts_table = MagicMock()
        resource.return_value.Table.return_value = attempts_table

        import importlib
        import services.dlq.auto_replay as mod
        importlib.reload(mod)
        mod.dynamodb = resource.return_value

        sched = mod.AutoReplayScheduler('dlq-url', 'stream')
        sched.attempts_table = attempts_table
        # Replace the real replay service with a mock
        sched.replay_service = MagicMock()
        sched._mod = mod
        yield sched


def _replay_result(replayed, still_failing):
    return {'replayed': replayed, 'still_failing': still_failing}


# ---------------------------------------------------------------------------
# Retry eligibility
# ---------------------------------------------------------------------------

def test_retryable_reasons(scheduler):
    assert scheduler.is_retryable('downstream_timeout') is True
    assert scheduler.is_retryable('throttled') is True


def test_non_retryable_reasons(scheduler):
    assert scheduler.is_retryable('schema_validation') is False
    assert scheduler.is_retryable('transform_error') is False
    assert scheduler.is_retryable('bogus_reason') is False


# ---------------------------------------------------------------------------
# Backoff timing
# ---------------------------------------------------------------------------

def test_backoff_first_attempt_always_due(scheduler):
    assert scheduler.backoff_due(attempt=0, last_attempt_at=None) is True


def test_backoff_not_due_before_window(scheduler):
    now = datetime(2026, 10, 6, 12, 0, 0)
    # attempt 1 -> 5m window; only 2m elapsed
    last = (now - timedelta(minutes=2)).isoformat()
    assert scheduler.backoff_due(attempt=1, last_attempt_at=last, now=now) is False


def test_backoff_due_after_window(scheduler):
    now = datetime(2026, 10, 6, 12, 0, 0)
    # attempt 1 -> 5m window; 6m elapsed
    last = (now - timedelta(minutes=6)).isoformat()
    assert scheduler.backoff_due(attempt=1, last_attempt_at=last, now=now) is True


def test_backoff_exhausted_never_due(scheduler):
    now = datetime(2026, 10, 6, 12, 0, 0)
    last = (now - timedelta(hours=24)).isoformat()
    assert scheduler.backoff_due(attempt=4, last_attempt_at=last, now=now) is False


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

def test_run_replays_when_due(scheduler):
    scheduler._get_attempt_record = MagicMock(return_value={'attempt': 0, 'last_attempt_at': None})
    scheduler.replay_service.replay.side_effect = [
        _replay_result(3, 1),  # one retryable reason
        _replay_result(2, 0),  # other retryable reason
    ]
    scheduler._save_attempt_record = MagicMock()

    result = scheduler.run('p1')

    assert result['action'] == 'replayed'
    assert result['replayed'] == 5
    assert result['still_failing'] == 1
    assert result['attempt'] == 1
    scheduler._save_attempt_record.assert_called_once()


def test_run_waits_when_backoff_not_elapsed(scheduler):
    now = datetime(2026, 10, 6, 12, 0, 0)
    recent = (now - timedelta(minutes=1)).isoformat()
    scheduler._get_attempt_record = MagicMock(return_value={'attempt': 2, 'last_attempt_at': recent})

    result = scheduler.run('p1', now=now)

    assert result['action'] == 'waiting'
    scheduler.replay_service.replay.assert_not_called()


def test_run_exhausted_after_max_attempts(scheduler):
    scheduler._get_attempt_record = MagicMock(return_value={'attempt': 4, 'last_attempt_at': '2026-10-06T00:00:00'})

    result = scheduler.run('p1')

    assert result['action'] == 'exhausted'
    scheduler.replay_service.replay.assert_not_called()


def test_run_idle_resets_when_nothing_retryable(scheduler):
    scheduler._get_attempt_record = MagicMock(return_value={'attempt': 1, 'last_attempt_at': None})
    scheduler.replay_service.replay.side_effect = [
        _replay_result(0, 0),
        _replay_result(0, 0),
    ]
    scheduler._reset_attempts = MagicMock()

    result = scheduler.run('p1')

    assert result['action'] == 'idle'
    assert result['replayed'] == 0
    scheduler._reset_attempts.assert_called_once_with('p1')


def test_run_only_replays_retryable_reasons(scheduler):
    scheduler._get_attempt_record = MagicMock(return_value={'attempt': 0, 'last_attempt_at': None})
    scheduler.replay_service.replay.side_effect = [
        _replay_result(1, 0),
        _replay_result(1, 0),
    ]
    scheduler._save_attempt_record = MagicMock()

    scheduler.run('p1')

    # One replay call per retryable reason (downstream_timeout, throttled)
    assert scheduler.replay_service.replay.call_count == 2
    reasons = {
        call.kwargs['reason_filter']
        for call in scheduler.replay_service.replay.call_args_list
    }
    mod = scheduler._mod
    assert reasons == {mod.FailureReason.DOWNSTREAM_TIMEOUT, mod.FailureReason.THROTTLED}
