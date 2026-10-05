"""
Tests for alert aggregation.

Verify grouping, severity/count ranking, digest summary, suppression logic,
and Slack formatting. DynamoDB is mocked.
"""

import sys
import pytest
from unittest.mock import MagicMock, patch

# Stub aws_lambda_powertools so the module imports without the Lambda runtime dep
if 'aws_lambda_powertools' not in sys.modules:
    powertools_stub = MagicMock()
    powertools_stub.Logger = MagicMock(return_value=MagicMock())
    sys.modules['aws_lambda_powertools'] = powertools_stub


@pytest.fixture
def aggregator():
    with patch('boto3.resource') as resource:
        table = MagicMock()
        resource.return_value.Table.return_value = table
        import importlib
        import services.alerts.aggregator as mod
        importlib.reload(mod)
        mod.dynamodb = resource.return_value
        agg = mod.AlertAggregator()
        agg._table = table
        agg._mod = mod
        yield agg


def _alert(alert_type, severity, ts, title='t', message='m'):
    return {
        'alert_type': alert_type,
        'severity': severity,
        'timestamp': ts,
        'title': title,
        'message': message
    }


# ---------------------------------------------------------------------------
# Aggregation / grouping
# ---------------------------------------------------------------------------

def test_aggregate_groups_by_type_and_severity(aggregator):
    alerts = [
        _alert('failure', 'error', '2026-10-05T10:00:00'),
        _alert('failure', 'error', '2026-10-05T10:05:00'),
        _alert('cost_spike', 'warning', '2026-10-05T10:02:00'),
    ]
    digest = aggregator.aggregate(alerts, 'p1', 15)

    assert digest['total_alerts'] == 3
    assert digest['unique_groups'] == 2

    failure_group = next(g for g in digest['groups'] if g['alert_type'] == 'failure')
    assert failure_group['count'] == 2
    assert failure_group['first_seen'] == '2026-10-05T10:00:00'
    assert failure_group['last_seen'] == '2026-10-05T10:05:00'


def test_aggregate_ranks_by_severity_then_count(aggregator):
    alerts = [
        _alert('cost_spike', 'warning', '2026-10-05T10:00:00'),
        _alert('cost_spike', 'warning', '2026-10-05T10:01:00'),
        _alert('cost_spike', 'warning', '2026-10-05T10:02:00'),
        _alert('failure', 'critical', '2026-10-05T10:03:00'),
    ]
    digest = aggregator.aggregate(alerts, 'p1', 15)

    # critical ranks above warning even though warning has a higher count
    assert digest['groups'][0]['severity'] == 'critical'
    assert digest['highest_severity'] == 'critical'


def test_aggregate_empty(aggregator):
    digest = aggregator.aggregate([], 'p1', 15)
    assert digest['total_alerts'] == 0
    assert digest['unique_groups'] == 0
    assert digest['highest_severity'] is None
    assert 'No alerts' in digest['summary']


def test_summary_line_pluralization(aggregator):
    one = aggregator.aggregate([_alert('failure', 'error', '2026-10-05T10:00:00')], 'p1', 15)
    assert '1 alert ' in one['summary']
    assert 'ERROR' in one['summary']


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------

def test_suppress_after_threshold(aggregator):
    aggregator._fetch_recent_alerts = MagicMock(return_value=[
        _alert('failure', 'error', '2026-10-05T10:00:00'),
        _alert('failure', 'error', '2026-10-05T10:01:00'),
        _alert('failure', 'error', '2026-10-05T10:02:00'),
    ])
    assert aggregator.should_suppress_individual('p1', 'failure', 'error', threshold=3) is True


def test_do_not_suppress_below_threshold(aggregator):
    aggregator._fetch_recent_alerts = MagicMock(return_value=[
        _alert('failure', 'error', '2026-10-05T10:00:00'),
    ])
    assert aggregator.should_suppress_individual('p1', 'failure', 'error', threshold=3) is False


def test_never_suppress_critical(aggregator):
    aggregator._fetch_recent_alerts = MagicMock(return_value=[
        _alert('failure', 'critical', '2026-10-05T10:00:00') for _ in range(10)
    ])
    assert aggregator.should_suppress_individual('p1', 'failure', 'critical', threshold=3) is False


# ---------------------------------------------------------------------------
# Slack formatting
# ---------------------------------------------------------------------------

def test_format_slack_digest(aggregator):
    digest = aggregator.aggregate([
        _alert('failure', 'error', '2026-10-05T10:00:00', title='Lambda timeout'),
        _alert('failure', 'error', '2026-10-05T10:01:00', title='Lambda timeout'),
    ], 'p1', 15)

    payload = aggregator.format_slack_digest(digest)

    assert 'Alert Digest' in payload['text']
    assert payload['attachments'][0]['color'] == '#FF0000'  # error
    field = payload['attachments'][0]['fields'][0]
    assert '×2' in field['value']


# ---------------------------------------------------------------------------
# build_digest wiring
# ---------------------------------------------------------------------------

def test_build_digest_queries_window(aggregator):
    aggregator._fetch_recent_alerts = MagicMock(return_value=[
        _alert('failure', 'error', '2026-10-05T10:00:00'),
    ])
    digest = aggregator.build_digest('p1', window_minutes=30)
    aggregator._fetch_recent_alerts.assert_called_once_with('p1', 30)
    assert digest['window_minutes'] == 30
    assert digest['total_alerts'] == 1
