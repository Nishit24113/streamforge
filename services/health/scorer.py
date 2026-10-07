"""
Pipeline health scoring for StreamForge.

Each pipeline emits many signals — latency, error rate, anomaly rate, how deep
its dead-letter queue is, how well auto-replay is recovering. On their own they
tell fragmented stories. This module folds them into a single 0-100 health
score and a status tier (healthy / degraded / unhealthy / critical), so an
operator can glance at one number per pipeline and know where to look.
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from enum import Enum
from aws_lambda_powertools import Logger

logger = Logger()


class HealthStatus(Enum):
    """Overall health tiers derived from the composite score."""
    HEALTHY = "healthy"        # 90-100
    DEGRADED = "degraded"      # 70-89
    UNHEALTHY = "unhealthy"    # 40-69
    CRITICAL = "critical"      # 0-39


# Each signal contributes a weighted sub-score (0-1, higher is healthier).
# Weights sum to 1.0.
SIGNAL_WEIGHTS = {
    'error_rate': 0.30,
    'latency': 0.20,
    'anomaly_rate': 0.20,
    'dlq_depth': 0.15,
    'recovery_rate': 0.15,
}

# Thresholds at which a signal's sub-score hits 0 (fully unhealthy).
# Values at or better than "good" score 1.0; between good and bad scale linearly.
SIGNAL_BOUNDS = {
    # metric: (good_value, bad_value)
    'error_rate': (0.0, 0.10),        # 0% good, >=10% bad
    'latency': (200.0, 5000.0),       # 200ms good, >=5s bad (ms)
    'anomaly_rate': (0.01, 0.15),     # 1% good, >=15% bad
    'dlq_depth': (0.0, 1000.0),       # empty good, >=1000 msgs bad
    'recovery_rate': (1.0, 0.0),      # 100% recovery good, 0% bad (inverted)
}


def _normalize(metric: str, value: float) -> float:
    """
    Map a raw metric value to a 0-1 sub-score (1 = healthy, 0 = unhealthy).

    Linear scaling between the metric's good and bad bounds, clamped to [0, 1].
    """
    good, bad = SIGNAL_BOUNDS[metric]

    if good == bad:
        return 1.0

    # Fraction of the way from good -> bad
    frac = (value - good) / (bad - good)
    score = 1.0 - frac
    return max(0.0, min(1.0, score))


class HealthScorer:
    """Computes composite pipeline health scores from metric snapshots."""

    def score(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute a composite health score from a metrics snapshot.

        Args:
            metrics: Snapshot with any of the keys in SIGNAL_WEIGHTS. Missing
                     signals are excluded and remaining weights renormalized, so
                     a partial snapshot still produces a meaningful score.

        Returns:
            Score (0-100), status tier, per-signal breakdown, and worst signal.
        """
        breakdown = {}
        present_weights = {}

        for metric, weight in SIGNAL_WEIGHTS.items():
            if metric not in metrics or metrics[metric] is None:
                continue
            try:
                value = float(metrics[metric])
            except (ValueError, TypeError):
                continue

            sub_score = _normalize(metric, value)
            breakdown[metric] = {
                'value': value,
                'sub_score': round(sub_score, 4),
                'weight': weight
            }
            present_weights[metric] = weight

        if not present_weights:
            return {
                'score': None,
                'status': None,
                'breakdown': {},
                'worst_signal': None,
                'message': 'No scoreable metrics provided'
            }

        # Renormalize weights across present signals
        total_weight = sum(present_weights.values())
        composite = sum(
            breakdown[m]['sub_score'] * (present_weights[m] / total_weight)
            for m in present_weights
        )
        score = round(composite * 100, 1)

        worst_signal = min(breakdown, key=lambda m: breakdown[m]['sub_score'])

        return {
            'score': score,
            'status': self.status_for(score).value,
            'breakdown': breakdown,
            'worst_signal': worst_signal,
            'generated_at': datetime.utcnow().isoformat()
        }

    def status_for(self, score: float) -> HealthStatus:
        """Map a 0-100 score to a status tier."""
        if score >= 90:
            return HealthStatus.HEALTHY
        if score >= 70:
            return HealthStatus.DEGRADED
        if score >= 40:
            return HealthStatus.UNHEALTHY
        return HealthStatus.CRITICAL

    def score_many(self, pipelines: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Score multiple pipelines and return them ranked worst-first, so the
        most troubled pipelines surface at the top of a fleet view.
        """
        results = []
        for pipeline_id, metrics in pipelines.items():
            result = self.score(metrics)
            result['pipeline_id'] = pipeline_id
            results.append(result)

        # Rank: unscoreable last, then by ascending score (worst first)
        return sorted(
            results,
            key=lambda r: (r['score'] is None, r['score'] if r['score'] is not None else 0)
        )


# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for health scoring.

    - action=score   : score a single pipeline from `metrics`
    - action=score_many : score a map of {pipeline_id: metrics}
    """
    scorer = HealthScorer()
    action = event.get('action', 'score')

    try:
        if action == 'score':
            result = scorer.score(event.get('metrics', {}))
            result['pipeline_id'] = event.get('pipeline_id')
            return _response(200, result)

        elif action == 'score_many':
            results = scorer.score_many(event.get('pipelines', {}))
            return _response(200, {'pipelines': results})

        else:
            return _response(400, {'error': f'Unknown action: {action}'})

    except Exception as e:
        logger.error(f"Health scoring error: {e}")
        return _response(500, {'error': str(e)})


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {'Content-Type': 'application/json'}
    }
