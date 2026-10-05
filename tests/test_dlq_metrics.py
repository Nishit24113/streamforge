"""
Tests for DLQ metrics aggregation.

CloudWatch is mocked; tests verify trend sorting, reason breakdown,
recovery-rate math, and the dashboard summary payload.
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
def mocked():
    with patch('boto3.client') as client, patch('boto3.resource') as resource:
        cw = MagicMock()
        client.return_value = cw
        resource.return_value.Table.return_value = MagicMock()

        import importlib
        import services.dlq.metrics as mod
        importlib.reload(mod)
        mod.cloudwatch = cw
        mod.dynamodb = resource.return_value

        yield mod, cw


def _datapoint(ts, total):
    return {'Timestamp': ts, 'Sum': float(total)}


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

def test_trend_sorted_oldest_first(mocked):
    mod, cw = mocked
    t0 = datetime(2026, 10, 5, 10, 0, 0)
    t1 = datetime(2026, 10, 5, 11, 0, 0)
    t2 = datetime(2026, 10, 5, 12, 0, 0)
    # Return out of order; service must sort
    cw.get_metric_statistics.return_value = {
        'Datapoints': [_datapoint(t2, 5), _datapoint(t0, 2), _datapoint(t1, 9)]
    }

    svc = mod.DLQMetrics()
    trend = svc.get_failure_trend('p1', hours=6)

    assert [p['failures'] for p in trend] == [2, 9, 5]
    assert trend[0]['timestamp'] == t0.isoformat()


def test_trend_empty(mocked):
    mod, cw = mocked
    cw.get_metric_statistics.return_value = {'Datapoints': []}
    svc = mod.DLQMetrics()
    assert svc.get_failure_trend('p1') == []


# ---------------------------------------------------------------------------
# By reason
# ---------------------------------------------------------------------------

def test_failures_by_reason_only_nonzero(mocked):
    mod, cw = mocked

    def per_reason(**kwargs):
        reason = next(d['Value'] for d in kwargs['Dimensions'] if d['Name'] == 'FailureReason')
        totals = {
            'schema_validation': [_datapoint(datetime.utcnow(), 30)],
            'transform_error': [_datapoint(datetime.utcnow(), 4)],
        }
        return {'Datapoints': totals.get(reason, [])}

    cw.get_metric_statistics.side_effect = per_reason

    svc = mod.DLQMetrics()
    by_reason = svc.get_failures_by_reason('p1', hours=24)

    assert by_reason == {'schema_validation': 30, 'transform_error': 4}
    assert 'throttled' not in by_reason  # zero counts omitted


# ---------------------------------------------------------------------------
# Recovery rate
# ---------------------------------------------------------------------------

def test_recovery_rate_computes_fraction(mocked):
    mod, cw = mocked

    def per_metric(**kwargs):
        values = {'ReplayedEvents': 38, 'ReplayStillFailing': 2}
        return {'Datapoints': [_datapoint(datetime.utcnow(), values[kwargs['MetricName']])]}

    cw.get_metric_statistics.side_effect = per_metric

    svc = mod.DLQMetrics()
    recovery = svc.get_recovery_rate('p1')

    assert recovery['replayed'] == 38
    assert recovery['still_failing'] == 2
    assert recovery['attempted'] == 40
    assert recovery['recovery_rate'] == 0.95


def test_recovery_rate_no_attempts_is_zero(mocked):
    mod, cw = mocked
    cw.get_metric_statistics.return_value = {'Datapoints': []}
    svc = mod.DLQMetrics()
    recovery = svc.get_recovery_rate('p1')
    assert recovery['attempted'] == 0
    assert recovery['recovery_rate'] == 0.0


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

def test_dashboard_summary_picks_top_reason(mocked):
    mod, cw = mocked

    svc = mod.DLQMetrics()
    svc.get_failures_by_reason = MagicMock(return_value={
        'schema_validation': 30,
        'transform_error': 4
    })
    svc.get_failure_trend = MagicMock(return_value=[{'timestamp': 't', 'failures': 34}])
    svc.get_recovery_rate = MagicMock(return_value={
        'replayed': 0, 'still_failing': 0, 'attempted': 0, 'recovery_rate': 0.0
    })

    summary = svc.get_dashboard_summary('p1', hours=24)

    assert summary['total_failures'] == 34
    assert summary['top_failure_reason'] == 'schema_validation'
    assert summary['pipeline_id'] == 'p1'
    assert summary['window_hours'] == 24


def test_dashboard_summary_handles_no_failures(mocked):
    mod, cw = mocked
    svc = mod.DLQMetrics()
    svc.get_failures_by_reason = MagicMock(return_value={})
    svc.get_failure_trend = MagicMock(return_value=[])
    svc.get_recovery_rate = MagicMock(return_value={
        'replayed': 0, 'still_failing': 0, 'attempted': 0, 'recovery_rate': 0.0
    })

    summary = svc.get_dashboard_summary('p1')

    assert summary['total_failures'] == 0
    assert summary['top_failure_reason'] is None


# ---------------------------------------------------------------------------
# Metric emission
# ---------------------------------------------------------------------------

def test_record_failure_emits_metric(mocked):
    mod, cw = mocked
    svc = mod.DLQMetrics()
    svc.record_failure('p1', 'schema_validation', count=5)

    cw.put_metric_data.assert_called_once()
    call = cw.put_metric_data.call_args.kwargs
    assert call['Namespace'] == 'StreamForge/DLQ'
    data = call['MetricData'][0]
    assert data['Value'] == 5
    dims = {d['Name']: d['Value'] for d in data['Dimensions']}
    assert dims['PipelineId'] == 'p1'
    assert dims['FailureReason'] == 'schema_validation'


def test_record_replay_emits_two_metrics(mocked):
    mod, cw = mocked
    svc = mod.DLQMetrics()
    svc.record_replay('p1', replayed=10, still_failing=2)

    data = cw.put_metric_data.call_args.kwargs['MetricData']
    names = {d['MetricName']: d['Value'] for d in data}
    assert names['ReplayedEvents'] == 10
    assert names['ReplayStillFailing'] == 2
