"""
Tests for health score history and trend detection.

Verify least-squares slope, trend classification (improving/stable/degrading/
unknown), insufficient-data handling, and gradual-degradation detection.
DynamoDB is mocked.
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
def history():
    with patch('boto3.resource') as resource:
        table = MagicMock()
        resource.return_value.Table.return_value = table
        import importlib
        import services.health.history as mod
        importlib.reload(mod)
        mod.dynamodb = resource.return_value
        h = mod.HealthHistory()
        h.history_table = table
        h._mod = mod
        yield h


# ---------------------------------------------------------------------------
# Slope
# ---------------------------------------------------------------------------

def test_slope_rising(history):
    mod = history._mod
    assert mod._linear_slope([10, 20, 30, 40]) == pytest.approx(10.0)


def test_slope_falling(history):
    mod = history._mod
    assert mod._linear_slope([40, 30, 20, 10]) == pytest.approx(-10.0)


def test_slope_flat(history):
    mod = history._mod
    assert mod._linear_slope([50, 50, 50]) == pytest.approx(0.0)


def test_slope_single_point(history):
    mod = history._mod
    assert mod._linear_slope([50]) == 0.0


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------

def test_trend_degrading(history):
    result = history.analyze_trend([95, 90, 85, 80, 75])
    assert result['trend'] == 'degrading'
    assert result['slope'] < 0
    assert result['change'] == -20.0


def test_trend_improving(history):
    result = history.analyze_trend([60, 70, 80, 90])
    assert result['trend'] == 'improving'
    assert result['slope'] > 0


def test_trend_stable(history):
    # small fluctuations, slope within +/- threshold
    result = history.analyze_trend([80, 80.5, 79.5, 80])
    assert result['trend'] == 'stable'


def test_trend_unknown_insufficient_data(history):
    result = history.analyze_trend([80, 75])
    assert result['trend'] == 'unknown'
    assert result['samples'] == 2


def test_trend_empty(history):
    result = history.analyze_trend([])
    assert result['trend'] == 'unknown'


# ---------------------------------------------------------------------------
# Gradual degradation detection
# ---------------------------------------------------------------------------

def test_detect_gradual_degradation_flags_slow_decline(history):
    history.get_history = MagicMock(return_value=[
        {'score': 92}, {'score': 88}, {'score': 84}, {'score': 80}, {'score': 76}
    ])
    result = history.detect_gradual_degradation('p1', hours=6)

    assert result['degrading'] is True
    assert result['current_score'] == 76
    assert result['peak_score'] == 92
    assert result['drop_from_peak'] == 16.0


def test_detect_no_degradation_when_stable(history):
    history.get_history = MagicMock(return_value=[
        {'score': 90}, {'score': 90}, {'score': 91}, {'score': 90}
    ])
    result = history.detect_gradual_degradation('p1')
    assert result['degrading'] is False


def test_detect_handles_missing_scores(history):
    history.get_history = MagicMock(return_value=[
        {'score': 90}, {'score': None}, {'score': 80}, {'score': 70}
    ])
    result = history.detect_gradual_degradation('p1')
    # None filtered out; 3 valid points, clear decline
    assert result['samples'] == 3
    assert result['degrading'] is True


def test_detect_insufficient_data(history):
    history.get_history = MagicMock(return_value=[{'score': 90}])
    result = history.detect_gradual_degradation('p1')
    assert result['trend'] == 'unknown'
    assert result['degrading'] is False


# ---------------------------------------------------------------------------
# record_score
# ---------------------------------------------------------------------------

def test_record_score_persists(history):
    item = history.record_score('p1', score=85.0, status='degraded')
    assert item['pipeline_id'] == 'p1'
    assert item['score'] == 85.0
    assert item['status'] == 'degraded'
    history.history_table.put_item.assert_called_once()
