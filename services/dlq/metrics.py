"""
DLQ metrics aggregation for StreamForge.

Turns raw dead-letter-queue failures into trends: how many events are failing,
why, and whether it's getting better or worse. Powers the DLQ metrics dashboard
and feeds alerting when failure rates spike.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import boto3
from aws_lambda_powertools import Logger

logger = Logger()

cloudwatch = boto3.client('cloudwatch')
dynamodb = boto3.resource('dynamodb')

NAMESPACE = 'StreamForge/DLQ'


class DLQMetrics:
    """Aggregates and queries DLQ failure metrics."""

    def __init__(self):
        self.replay_table = dynamodb.Table('streamforge-dlq-replays')

    def record_failure(self, pipeline_id: str, failure_reason: str, count: int = 1):
        """
        Emit a CloudWatch metric when events are dead-lettered.

        Called from the ingestion/processing path whenever events are routed
        to the DLQ, so trends are captured in real time.
        """
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[{
                'MetricName': 'FailedEvents',
                'Value': count,
                'Unit': 'Count',
                'Dimensions': [
                    {'Name': 'PipelineId', 'Value': pipeline_id},
                    {'Name': 'FailureReason', 'Value': failure_reason}
                ]
            }]
        )

    def record_replay(self, pipeline_id: str, replayed: int, still_failing: int):
        """Emit metrics after a replay so recovery rate is tracked."""
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    'MetricName': 'ReplayedEvents',
                    'Value': replayed,
                    'Unit': 'Count',
                    'Dimensions': [{'Name': 'PipelineId', 'Value': pipeline_id}]
                },
                {
                    'MetricName': 'ReplayStillFailing',
                    'Value': still_failing,
                    'Unit': 'Count',
                    'Dimensions': [{'Name': 'PipelineId', 'Value': pipeline_id}]
                }
            ]
        )

    def get_failure_trend(
        self,
        pipeline_id: str,
        hours: int = 24,
        period_seconds: int = 3600
    ) -> List[Dict[str, Any]]:
        """
        Get failure counts over time for a pipeline.

        Args:
            pipeline_id: Pipeline identifier
            hours: Lookback window in hours
            period_seconds: Aggregation bucket size (default 1 hour)

        Returns:
            Time-bucketed failure counts, oldest first
        """
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)

        response = cloudwatch.get_metric_statistics(
            Namespace=NAMESPACE,
            MetricName='FailedEvents',
            Dimensions=[{'Name': 'PipelineId', 'Value': pipeline_id}],
            StartTime=start,
            EndTime=end,
            Period=period_seconds,
            Statistics=['Sum']
        )

        points = sorted(
            response.get('Datapoints', []),
            key=lambda d: d['Timestamp']
        )

        return [
            {
                'timestamp': p['Timestamp'].isoformat(),
                'failures': int(p['Sum'])
            }
            for p in points
        ]

    def get_failures_by_reason(
        self,
        pipeline_id: str,
        hours: int = 24
    ) -> Dict[str, int]:
        """
        Get total failures broken down by reason over the lookback window.

        Returns:
            Mapping of failure_reason -> total count
        """
        reasons = [
            'schema_validation',
            'transform_error',
            'downstream_timeout',
            'throttled',
            'unknown'
        ]

        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        by_reason: Dict[str, int] = {}

        for reason in reasons:
            response = cloudwatch.get_metric_statistics(
                Namespace=NAMESPACE,
                MetricName='FailedEvents',
                Dimensions=[
                    {'Name': 'PipelineId', 'Value': pipeline_id},
                    {'Name': 'FailureReason', 'Value': reason}
                ],
                StartTime=start,
                EndTime=end,
                Period=hours * 3600,
                Statistics=['Sum']
            )

            total = sum(int(p['Sum']) for p in response.get('Datapoints', []))
            if total > 0:
                by_reason[reason] = total

        return by_reason

    def get_recovery_rate(self, pipeline_id: str, hours: int = 24) -> Dict[str, Any]:
        """
        Compute how effective replays have been: of events we attempted to
        replay, what fraction actually succeeded.

        Returns:
            Replay totals and recovery rate (0.0 - 1.0)
        """
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)

        def _sum(metric: str) -> int:
            response = cloudwatch.get_metric_statistics(
                Namespace=NAMESPACE,
                MetricName=metric,
                Dimensions=[{'Name': 'PipelineId', 'Value': pipeline_id}],
                StartTime=start,
                EndTime=end,
                Period=hours * 3600,
                Statistics=['Sum']
            )
            return sum(int(p['Sum']) for p in response.get('Datapoints', []))

        replayed = _sum('ReplayedEvents')
        still_failing = _sum('ReplayStillFailing')
        attempted = replayed + still_failing

        recovery_rate = (replayed / attempted) if attempted > 0 else 0.0

        return {
            'replayed': replayed,
            'still_failing': still_failing,
            'attempted': attempted,
            'recovery_rate': round(recovery_rate, 4)
        }

    def get_dashboard_summary(
        self,
        pipeline_id: str,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Build the full payload for the DLQ metrics dashboard.
        """
        by_reason = self.get_failures_by_reason(pipeline_id, hours)
        trend = self.get_failure_trend(pipeline_id, hours)
        recovery = self.get_recovery_rate(pipeline_id, hours)

        total_failures = sum(by_reason.values())
        top_reason = max(by_reason, key=by_reason.get) if by_reason else None

        return {
            'pipeline_id': pipeline_id,
            'window_hours': hours,
            'generated_at': datetime.utcnow().isoformat(),
            'total_failures': total_failures,
            'top_failure_reason': top_reason,
            'by_reason': by_reason,
            'trend': trend,
            'recovery': recovery
        }


# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for DLQ metrics API.

    Endpoints:
    - GET /dlq/{pipeline_id}/metrics          - Full dashboard summary
    - GET /dlq/{pipeline_id}/metrics/trend    - Failure trend over time
    - GET /dlq/{pipeline_id}/metrics/reasons  - Failures by reason
    """
    metrics = DLQMetrics()

    path = event.get('path', '')
    path_params = event.get('pathParameters', {}) or {}
    query = event.get('queryStringParameters', {}) or {}

    pipeline_id = path_params.get('pipeline_id')
    if not pipeline_id:
        return _response(400, {'error': 'pipeline_id is required'})

    hours = int(query.get('hours', 24))

    try:
        if path.endswith('/trend'):
            result = {'trend': metrics.get_failure_trend(pipeline_id, hours)}
        elif path.endswith('/reasons'):
            result = {'by_reason': metrics.get_failures_by_reason(pipeline_id, hours)}
        else:
            result = metrics.get_dashboard_summary(pipeline_id, hours)

        return _response(200, result)

    except Exception as e:
        logger.error(f"DLQ metrics error: {e}")
        return _response(500, {'error': str(e)})


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {'Content-Type': 'application/json'}
    }
