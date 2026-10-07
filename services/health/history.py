"""
Health score history and trend detection for StreamForge.

A single health score tells you where a pipeline is now; it doesn't tell you
where it's heading. This module persists scores over time and analyzes the
recent series to classify the trend — improving, stable, or degrading — and to
catch *gradual* degradation that never trips a point-in-time threshold but
quietly erodes a pipeline over hours.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from enum import Enum
import boto3
from aws_lambda_powertools import Logger

logger = Logger()

dynamodb = boto3.resource('dynamodb')


class Trend(Enum):
    """Direction of a pipeline's health over the analyzed window."""
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    UNKNOWN = "unknown"      # not enough data


# A score series must have at least this many points to classify a trend.
MIN_POINTS_FOR_TREND = 3

# Slope (score-points per sample) beyond which a trend is non-stable.
# E.g. losing >1 point per sample on average is "degrading".
SLOPE_THRESHOLD = 1.0


def _linear_slope(values: List[float]) -> float:
    """
    Least-squares slope of `values` against their index (0, 1, 2, ...).

    Positive slope => rising scores (improving); negative => falling (degrading).
    """
    n = len(values)
    if n < 2:
        return 0.0

    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    denominator = sum((x - mean_x) ** 2 for x in xs)

    if denominator == 0:
        return 0.0
    return numerator / denominator


class HealthHistory:
    """Persists and analyzes pipeline health scores over time."""

    def __init__(self):
        self.history_table = dynamodb.Table('streamforge-health-history')

    def record_score(
        self,
        pipeline_id: str,
        score: float,
        status: str,
        now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Persist a health score sample."""
        now = now or datetime.utcnow()
        item = {
            'pipeline_id': pipeline_id,
            'timestamp': now.isoformat(),
            'score': score,
            'status': status
        }
        self.history_table.put_item(Item=item)
        return item

    def get_history(
        self,
        pipeline_id: str,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Fetch score samples for a pipeline within the window, oldest first."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        response = self.history_table.query(
            KeyConditionExpression='pipeline_id = :pid AND #ts > :cutoff',
            ExpressionAttributeNames={'#ts': 'timestamp'},
            ExpressionAttributeValues={':pid': pipeline_id, ':cutoff': cutoff}
        )
        items = response.get('Items', [])
        return sorted(items, key=lambda i: i['timestamp'])

    def analyze_trend(self, scores: List[float]) -> Dict[str, Any]:
        """
        Classify the trend of a score series.

        Returns:
            Dict with trend, slope, and the change from first to last sample.
        """
        if len(scores) < MIN_POINTS_FOR_TREND:
            return {
                'trend': Trend.UNKNOWN.value,
                'slope': 0.0,
                'change': 0.0,
                'samples': len(scores)
            }

        slope = _linear_slope(scores)
        change = scores[-1] - scores[0]

        if slope <= -SLOPE_THRESHOLD:
            trend = Trend.DEGRADING
        elif slope >= SLOPE_THRESHOLD:
            trend = Trend.IMPROVING
        else:
            trend = Trend.STABLE

        return {
            'trend': trend.value,
            'slope': round(slope, 3),
            'change': round(change, 1),
            'samples': len(scores)
        }

    def detect_gradual_degradation(
        self,
        pipeline_id: str,
        hours: int = 6
    ) -> Dict[str, Any]:
        """
        Detect sustained, gradual degradation over the window.

        Flags pipelines whose health is trending down even if the current score
        hasn't yet crossed a critical threshold — the slow leaks that
        point-in-time alerts miss.

        Returns:
            Analysis with a `degrading` flag and supporting detail.
        """
        history = self.get_history(pipeline_id, hours)
        scores = [float(h['score']) for h in history if h.get('score') is not None]

        analysis = self.analyze_trend(scores)

        degrading = analysis['trend'] == Trend.DEGRADING.value

        current = scores[-1] if scores else None
        peak = max(scores) if scores else None
        drop_from_peak = round(peak - current, 1) if (peak is not None and current is not None) else None

        return {
            'pipeline_id': pipeline_id,
            'window_hours': hours,
            'degrading': degrading,
            'current_score': current,
            'peak_score': peak,
            'drop_from_peak': drop_from_peak,
            **analysis
        }


# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for health history.

    - action=record : persist a score sample
    - action=trend  : analyze gradual degradation over a window
    """
    history = HealthHistory()
    action = event.get('action')
    pipeline_id = event.get('pipeline_id')

    if not pipeline_id:
        return _response(400, {'error': 'pipeline_id is required'})

    try:
        if action == 'record':
            item = history.record_score(
                pipeline_id=pipeline_id,
                score=event['score'],
                status=event.get('status', 'unknown')
            )
            return _response(201, item)

        elif action == 'trend':
            hours = int(event.get('hours', 6))
            return _response(200, history.detect_gradual_degradation(pipeline_id, hours))

        else:
            return _response(400, {'error': f'Unknown action: {action}'})

    except (KeyError, ValueError) as e:
        return _response(400, {'error': str(e)})
    except Exception as e:
        logger.error(f"Health history error: {e}")
        return _response(500, {'error': str(e)})


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {'Content-Type': 'application/json'}
    }
