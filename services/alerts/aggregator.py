"""
Alert aggregation for StreamForge.

Instead of firing one notification per alert — which buries operators during an
incident — the aggregator collects alerts over a time window and emits a single
digest. Similar alerts (same pipeline, type, and severity) are collapsed into one
line with an occurrence count.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
import boto3
from aws_lambda_powertools import Logger

logger = Logger()

dynamodb = boto3.resource('dynamodb')

# Severity ordering for ranking the most important alerts in a digest
SEVERITY_RANK = {'info': 0, 'warning': 1, 'error': 2, 'critical': 3}


class AlertAggregator:
    """Collapses many alerts into a single digest over a time window."""

    def __init__(self):
        self.alerts_table = dynamodb.Table('streamforge-alerts')

    def build_digest(
        self,
        pipeline_id: str,
        window_minutes: int = 15
    ) -> Dict[str, Any]:
        """
        Build a digest of alerts for a pipeline over the recent window.

        Args:
            pipeline_id: Pipeline identifier
            window_minutes: Lookback window in minutes

        Returns:
            Digest with grouped alerts, counts, and a summary line
        """
        alerts = self._fetch_recent_alerts(pipeline_id, window_minutes)
        return self.aggregate(alerts, pipeline_id, window_minutes)

    def aggregate(
        self,
        alerts: List[Dict[str, Any]],
        pipeline_id: str,
        window_minutes: int
    ) -> Dict[str, Any]:
        """
        Group a list of alerts into a digest.

        Grouping key is (alert_type, severity). Each group reports its count,
        first/last seen timestamps, and a representative message.
        """
        groups: Dict[tuple, Dict[str, Any]] = {}

        for alert in alerts:
            key = (alert.get('alert_type', 'unknown'), alert.get('severity', 'info'))

            if key not in groups:
                groups[key] = {
                    'alert_type': key[0],
                    'severity': key[1],
                    'count': 0,
                    'first_seen': alert.get('timestamp'),
                    'last_seen': alert.get('timestamp'),
                    'sample_title': alert.get('title'),
                    'sample_message': alert.get('message')
                }

            group = groups[key]
            group['count'] += 1

            ts = alert.get('timestamp')
            if ts:
                if not group['first_seen'] or ts < group['first_seen']:
                    group['first_seen'] = ts
                if not group['last_seen'] or ts > group['last_seen']:
                    group['last_seen'] = ts

        # Rank groups: highest severity first, then highest count
        ranked = sorted(
            groups.values(),
            key=lambda g: (SEVERITY_RANK.get(g['severity'], 0), g['count']),
            reverse=True
        )

        total = sum(g['count'] for g in ranked)
        highest_severity = ranked[0]['severity'] if ranked else None

        return {
            'pipeline_id': pipeline_id,
            'window_minutes': window_minutes,
            'generated_at': datetime.utcnow().isoformat(),
            'total_alerts': total,
            'unique_groups': len(ranked),
            'highest_severity': highest_severity,
            'summary': self._summary_line(pipeline_id, total, len(ranked), highest_severity),
            'groups': ranked
        }

    def _summary_line(
        self,
        pipeline_id: str,
        total: int,
        unique_groups: int,
        highest_severity: Optional[str]
    ) -> str:
        """Build a one-line human-readable summary for the digest."""
        if total == 0:
            return f"No alerts for {pipeline_id}"

        return (
            f"{total} alert{'s' if total != 1 else ''} "
            f"({unique_groups} distinct) for {pipeline_id} "
            f"— highest severity: {(highest_severity or 'info').upper()}"
        )

    def should_suppress_individual(
        self,
        pipeline_id: str,
        alert_type: str,
        severity: str,
        window_minutes: int = 15,
        threshold: int = 3
    ) -> bool:
        """
        Decide whether an individual alert should be suppressed in favor of a digest.

        Once the same (type, severity) has fired `threshold` times in the window,
        further individual notifications are suppressed — the digest covers them.
        Critical alerts are never suppressed.

        Returns:
            True if the individual alert should be suppressed
        """
        if severity == 'critical':
            return False

        alerts = self._fetch_recent_alerts(pipeline_id, window_minutes)
        matching = [
            a for a in alerts
            if a.get('alert_type') == alert_type and a.get('severity') == severity
        ]

        return len(matching) >= threshold

    def _fetch_recent_alerts(
        self,
        pipeline_id: str,
        window_minutes: int
    ) -> List[Dict[str, Any]]:
        """Fetch alerts for a pipeline within the recent window."""
        cutoff = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()

        response = self.alerts_table.query(
            IndexName='pipeline-timestamp-index',
            KeyConditionExpression='pipeline_id = :pid AND #ts > :cutoff',
            ExpressionAttributeNames={'#ts': 'timestamp'},
            ExpressionAttributeValues={':pid': pipeline_id, ':cutoff': cutoff}
        )

        return response.get('Items', [])

    def format_slack_digest(self, digest: Dict[str, Any]) -> Dict[str, Any]:
        """Render a digest as a Slack message payload."""
        color_map = {
            'info': '#36A64F',
            'warning': '#FFA500',
            'error': '#FF0000',
            'critical': '#8B0000'
        }

        fields = []
        for group in digest['groups']:
            fields.append({
                'title': f"{group['alert_type'].replace('_', ' ').title()} ({group['severity'].upper()})",
                'value': f"×{group['count']} — {group['sample_title'] or 'n/a'}",
                'short': False
            })

        return {
            'text': f":bell: *Alert Digest* — {digest['summary']}",
            'attachments': [{
                'color': color_map.get(digest['highest_severity'], '#808080'),
                'fields': fields,
                'footer': f"StreamForge • last {digest['window_minutes']}m",
            }]
        }


# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for alert digests.

    Triggered by EventBridge on a schedule (e.g. every 15 minutes) per pipeline,
    or invoked directly with a pipeline_id.
    """
    aggregator = AlertAggregator()

    pipeline_id = event.get('pipeline_id')
    window_minutes = int(event.get('window_minutes', 15))

    if not pipeline_id:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'pipeline_id is required'})
        }

    try:
        digest = aggregator.build_digest(pipeline_id, window_minutes)
        return {
            'statusCode': 200,
            'body': json.dumps(digest),
            'headers': {'Content-Type': 'application/json'}
        }
    except Exception as e:
        logger.error(f"Alert aggregation error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
