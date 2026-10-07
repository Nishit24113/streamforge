"""
Tests for the custom alert rules engine.

Verify operator comparisons, AND/OR composition, missing-metric handling,
cooldown suppression, rule validation, and alert payload construction.
DynamoDB is mocked.
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
def engine():
    with patch('boto3.resource') as resource:
        rules_table = MagicMock()
        state_table = MagicMock()
        resource.return_value.Table.side_effect = lambda name: {
            'streamforge-alert-rules': rules_table,
            'streamforge-alert-rule-state': state_table
        }[name]

        import importlib
        import services.alerts.rules as mod
        importlib.reload(mod)
        mod.dynamodb = resource.return_value

        eng = mod.AlertRulesEngine()
        eng.rules_table = rules_table
        eng.state_table = state_table
        eng._mod = mod
        yield eng


def _rule(name='r1', conditions=None, severity='warning', logical_op='and', cooldown=15, enabled=True):
    return {
        'rule_id': f'p1:{name}',
        'pipeline_id': 'p1',
        'name': name,
        'conditions': conditions or [{'metric': 'latency', 'operator': 'gt', 'threshold': 5000}],
        'severity': severity,
        'logical_op': logical_op,
        'cooldown_minutes': cooldown,
        'enabled': enabled
    }


# ---------------------------------------------------------------------------
# Operator comparisons
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op,value,threshold,expected", [
    ('gt', 10, 5, True), ('gt', 5, 10, False),
    ('gte', 5, 5, True), ('lt', 3, 5, True),
    ('lte', 5, 5, True), ('eq', 7, 7, True),
    ('neq', 7, 8, True), ('neq', 7, 7, False),
])
def test_compare_operators(engine, op, value, threshold, expected):
    mod = engine._mod
    assert mod._compare(value, op, threshold) is expected


def test_compare_unknown_operator_raises(engine):
    mod = engine._mod
    with pytest.raises(ValueError):
        mod._compare(1, 'bogus', 2)


# ---------------------------------------------------------------------------
# Single rule evaluation
# ---------------------------------------------------------------------------

def test_evaluate_rule_triggered(engine):
    rule = _rule(conditions=[{'metric': 'latency', 'operator': 'gt', 'threshold': 5000}])
    result = engine.evaluate_rule(rule, {'latency': 6000})
    assert result['triggered'] is True
    assert result['matched_conditions'][0]['actual'] == 6000


def test_evaluate_rule_not_triggered(engine):
    rule = _rule(conditions=[{'metric': 'latency', 'operator': 'gt', 'threshold': 5000}])
    result = engine.evaluate_rule(rule, {'latency': 1000})
    assert result['triggered'] is False


def test_evaluate_rule_and_requires_all(engine):
    rule = _rule(logical_op='and', conditions=[
        {'metric': 'anomaly_rate', 'operator': 'gt', 'threshold': 0.05},
        {'metric': 'throughput', 'operator': 'lt', 'threshold': 10},
    ])
    assert engine.evaluate_rule(rule, {'anomaly_rate': 0.1, 'throughput': 5})['triggered'] is True
    assert engine.evaluate_rule(rule, {'anomaly_rate': 0.1, 'throughput': 50})['triggered'] is False


def test_evaluate_rule_or_requires_any(engine):
    rule = _rule(logical_op='or', conditions=[
        {'metric': 'anomaly_rate', 'operator': 'gt', 'threshold': 0.05},
        {'metric': 'throughput', 'operator': 'lt', 'threshold': 10},
    ])
    assert engine.evaluate_rule(rule, {'anomaly_rate': 0.1, 'throughput': 50})['triggered'] is True
    assert engine.evaluate_rule(rule, {'anomaly_rate': 0.01, 'throughput': 50})['triggered'] is False


def test_evaluate_rule_missing_metric_is_false(engine):
    rule = _rule(conditions=[{'metric': 'latency', 'operator': 'gt', 'threshold': 5000}])
    result = engine.evaluate_rule(rule, {'throughput': 100})
    assert result['triggered'] is False


def test_evaluate_rule_non_numeric_metric_is_false(engine):
    rule = _rule(conditions=[{'metric': 'latency', 'operator': 'gt', 'threshold': 5000}])
    result = engine.evaluate_rule(rule, {'latency': 'not-a-number'})
    assert result['triggered'] is False


# ---------------------------------------------------------------------------
# evaluate_all + cooldown
# ---------------------------------------------------------------------------

def test_evaluate_all_fires_and_records(engine):
    engine.list_rules = MagicMock(return_value=[_rule()])
    engine.state_table.get_item.return_value = {'Item': None}

    alerts = engine.evaluate_all('p1', {'latency': 9000})

    assert len(alerts) == 1
    assert alerts[0]['alert_type'] == 'custom_rule'
    assert alerts[0]['severity'] == 'warning'
    engine.state_table.put_item.assert_called_once()


def test_evaluate_all_skips_disabled(engine):
    engine.list_rules = MagicMock(return_value=[_rule(enabled=False)])
    alerts = engine.evaluate_all('p1', {'latency': 9000})
    assert alerts == []


def test_evaluate_all_respects_cooldown(engine):
    now = datetime(2026, 10, 7, 12, 0, 0)
    recent = (now - timedelta(minutes=5)).isoformat()  # cooldown is 15m
    engine.list_rules = MagicMock(return_value=[_rule(cooldown=15)])
    engine.state_table.get_item.return_value = {'Item': {'rule_id': 'p1:r1', 'last_fired_at': recent}}

    alerts = engine.evaluate_all('p1', {'latency': 9000}, now=now)

    assert alerts == []  # suppressed by cooldown
    engine.state_table.put_item.assert_not_called()


def test_evaluate_all_fires_after_cooldown(engine):
    now = datetime(2026, 10, 7, 12, 0, 0)
    old = (now - timedelta(minutes=20)).isoformat()  # cooldown is 15m
    engine.list_rules = MagicMock(return_value=[_rule(cooldown=15)])
    engine.state_table.get_item.return_value = {'Item': {'rule_id': 'p1:r1', 'last_fired_at': old}}

    alerts = engine.evaluate_all('p1', {'latency': 9000}, now=now)

    assert len(alerts) == 1


# ---------------------------------------------------------------------------
# create_rule validation
# ---------------------------------------------------------------------------

def test_create_rule_requires_conditions(engine):
    with pytest.raises(ValueError):
        engine.create_rule('p1', 'r1', conditions=[], severity='warning')


def test_create_rule_validates_condition_shape(engine):
    with pytest.raises(ValueError):
        engine.create_rule('p1', 'r1', conditions=[{'metric': 'latency'}], severity='warning')


def test_create_rule_validates_operator(engine):
    with pytest.raises(ValueError):
        engine.create_rule('p1', 'r1', conditions=[
            {'metric': 'latency', 'operator': 'bogus', 'threshold': 5}
        ], severity='warning')


def test_create_rule_persists(engine):
    rule = engine.create_rule('p1', 'high-latency', conditions=[
        {'metric': 'latency', 'operator': 'gt', 'threshold': 5000}
    ], severity='error')

    assert rule['rule_id'] == 'p1:high-latency'
    assert rule['severity'] == 'error'
    engine.rules_table.put_item.assert_called_once()


# ---------------------------------------------------------------------------
# Alert payload
# ---------------------------------------------------------------------------

def test_build_alert_includes_matched_conditions(engine):
    rule = _rule(name='high-latency', severity='critical')
    matched = [{'metric': 'latency', 'operator': 'gt', 'threshold': 5000, 'actual': 9000}]
    alert = engine._build_alert(rule, matched)

    assert alert['severity'] == 'critical'
    assert 'high-latency' in alert['title']
    assert alert['metadata']['matched_conditions'] == matched
    assert '9000' in alert['message']
