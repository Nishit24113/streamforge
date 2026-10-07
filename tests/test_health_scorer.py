"""
Tests for pipeline health scoring.

Verify signal normalization, composite weighting, weight renormalization for
partial snapshots, status tiers, worst-signal detection, and fleet ranking.
"""

import sys
import pytest
from unittest.mock import MagicMock

# Stub aws_lambda_powertools so the module imports without the Lambda runtime dep
if 'aws_lambda_powertools' not in sys.modules:
    powertools_stub = MagicMock()
    powertools_stub.Logger = MagicMock(return_value=MagicMock())
    sys.modules['aws_lambda_powertools'] = powertools_stub

import importlib
import services.health.scorer as mod
importlib.reload(mod)

HealthStatus = mod.HealthStatus


@pytest.fixture
def scorer():
    return mod.HealthScorer()


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def test_normalize_good_value_scores_one():
    assert mod._normalize('error_rate', 0.0) == 1.0
    assert mod._normalize('latency', 200.0) == 1.0


def test_normalize_bad_value_scores_zero():
    assert mod._normalize('error_rate', 0.10) == 0.0
    assert mod._normalize('latency', 5000.0) == 0.0


def test_normalize_beyond_bad_clamps_to_zero():
    assert mod._normalize('error_rate', 0.5) == 0.0
    assert mod._normalize('latency', 100000.0) == 0.0


def test_normalize_better_than_good_clamps_to_one():
    assert mod._normalize('latency', 50.0) == 1.0


def test_normalize_midpoint():
    # error_rate 5% is halfway between 0% (good) and 10% (bad)
    assert mod._normalize('error_rate', 0.05) == pytest.approx(0.5)


def test_normalize_inverted_recovery_rate():
    # recovery_rate: 100% good -> 1.0, 0% bad -> 0.0
    assert mod._normalize('recovery_rate', 1.0) == 1.0
    assert mod._normalize('recovery_rate', 0.0) == 0.0
    assert mod._normalize('recovery_rate', 0.5) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def test_score_all_healthy(scorer):
    result = scorer.score({
        'error_rate': 0.0,
        'latency': 200.0,
        'anomaly_rate': 0.01,
        'dlq_depth': 0.0,
        'recovery_rate': 1.0
    })
    assert result['score'] == 100.0
    assert result['status'] == 'healthy'


def test_score_all_bad(scorer):
    result = scorer.score({
        'error_rate': 0.10,
        'latency': 5000.0,
        'anomaly_rate': 0.15,
        'dlq_depth': 1000.0,
        'recovery_rate': 0.0
    })
    assert result['score'] == 0.0
    assert result['status'] == 'critical'


def test_score_weights_error_rate_most(scorer):
    # error_rate has the highest weight (0.30); a bad error_rate should hurt
    # more than a bad recovery_rate (0.15)
    bad_errors = scorer.score({'error_rate': 0.10, 'recovery_rate': 1.0})
    bad_recovery = scorer.score({'error_rate': 0.0, 'recovery_rate': 0.0})
    assert bad_errors['score'] < bad_recovery['score']


def test_score_partial_snapshot_renormalizes(scorer):
    # Only one signal present, and it's perfect -> score should be 100
    result = scorer.score({'latency': 200.0})
    assert result['score'] == 100.0
    assert set(result['breakdown'].keys()) == {'latency'}


def test_score_partial_half(scorer):
    # Single signal at midpoint -> 50
    result = scorer.score({'error_rate': 0.05})
    assert result['score'] == pytest.approx(50.0)


def test_score_no_metrics(scorer):
    result = scorer.score({})
    assert result['score'] is None
    assert result['status'] is None


def test_score_ignores_non_numeric(scorer):
    result = scorer.score({'latency': 'bad', 'error_rate': 0.0})
    assert set(result['breakdown'].keys()) == {'error_rate'}


def test_worst_signal_identified(scorer):
    result = scorer.score({
        'error_rate': 0.0,       # perfect
        'latency': 5000.0,       # worst
        'anomaly_rate': 0.01     # perfect
    })
    assert result['worst_signal'] == 'latency'


# ---------------------------------------------------------------------------
# Status tiers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (100, HealthStatus.HEALTHY),
    (90, HealthStatus.HEALTHY),
    (89, HealthStatus.DEGRADED),
    (70, HealthStatus.DEGRADED),
    (69, HealthStatus.UNHEALTHY),
    (40, HealthStatus.UNHEALTHY),
    (39, HealthStatus.CRITICAL),
    (0, HealthStatus.CRITICAL),
])
def test_status_tiers(scorer, score, expected):
    assert scorer.status_for(score) == expected


# ---------------------------------------------------------------------------
# Fleet ranking
# ---------------------------------------------------------------------------

def test_score_many_ranks_worst_first(scorer):
    results = scorer.score_many({
        'healthy-pipe': {'error_rate': 0.0, 'latency': 200.0},
        'bad-pipe': {'error_rate': 0.10, 'latency': 5000.0},
        'mid-pipe': {'error_rate': 0.05, 'latency': 200.0},
    })
    ids = [r['pipeline_id'] for r in results]
    assert ids[0] == 'bad-pipe'
    assert ids[-1] == 'healthy-pipe'


def test_score_many_unscoreable_last(scorer):
    results = scorer.score_many({
        'empty-pipe': {},
        'bad-pipe': {'error_rate': 0.10},
    })
    assert results[-1]['pipeline_id'] == 'empty-pipe'
    assert results[-1]['score'] is None
