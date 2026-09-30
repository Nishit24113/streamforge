"""
Alert Manager for StreamForge.

Sends notifications via Slack, email (SNS), and webhooks for:
- Pipeline failures
- Cost anomalies
- Data quality issues
- Performance degradation
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from enum import Enum
import boto3
import requests
from aws_lambda_powertools import Logger

logger = Logger()

# AWS clients
sns = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """Supported alert channels."""
    SLACK = "slack"
    EMAIL = "email"
    SNS = "sns"
    WEBHOOK = "webhook"


class AlertManager:
    """Manages alerts across multiple channels."""

    def __init__(self):
        self.alerts_table = dynamodb.Table('streamforge-alerts')
        self.config_table = dynamodb.Table('streamforge-alert-config')

    def send_alert(
        self,
        pipeline_id: str,
        alert_type: str,
        severity: AlertSeverity,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send alert to configured channels.

        Args:
            pipeline_id: Pipeline identifier
            alert_type: Type of alert (failure, anomaly, cost_spike, quality_issue)
            severity: Alert severity level
            title: Alert title
            message: Detailed message
            metadata: Additional context

        Returns:
            Alert record with delivery status
        """
        alert_id = f"alert-{int(datetime.utcnow().timestamp() * 1000)}"

        alert_record = {
            'alert_id': alert_id,
            'pipeline_id': pipeline_id,
            'alert_type': alert_type,
            'severity': severity.value,
            'title': title,
            'message': message,
            'metadata': metadata or {},
            'timestamp': datetime.utcnow().isoformat(),
            'delivered_to': []
        }

        # Get alert configuration for pipeline
        config = self._get_alert_config(pipeline_id)

        # Check if alert should be sent based on config
        if not self._should_send_alert(config, alert_type, severity):
            logger.info(f"Alert {alert_id} suppressed by configuration")
            alert_record['status'] = 'suppressed'
            self.alerts_table.put_item(Item=alert_record)
            return alert_record

        # Send to configured channels
        delivery_status = {}

        for channel in config.get('channels', []):
            try:
                if channel == AlertChannel.SLACK.value:
                    self._send_slack_alert(config, alert_record)
                    delivery_status['slack'] = 'success'
                    alert_record['delivered_to'].append('slack')

                elif channel == AlertChannel.EMAIL.value:
                    self._send_email_alert(config, alert_record)
                    delivery_status['email'] = 'success'
                    alert_record['delivered_to'].append('email')

                elif channel == AlertChannel.SNS.value:
                    self._send_sns_alert(config, alert_record)
                    delivery_status['sns'] = 'success'
                    alert_record['delivered_to'].append('sns')

                elif channel == AlertChannel.WEBHOOK.value:
                    self._send_webhook_alert(config, alert_record)
                    delivery_status['webhook'] = 'success'
                    alert_record['delivered_to'].append('webhook')

            except Exception as e:
                logger.error(f"Failed to send alert to {channel}: {e}")
                delivery_status[channel] = f'failed: {str(e)}'

        alert_record['delivery_status'] = delivery_status
        alert_record['status'] = 'delivered' if alert_record['delivered_to'] else 'failed'

        # Store alert record
        self.alerts_table.put_item(Item=alert_record)

        # Publish CloudWatch metric
        cloudwatch.put_metric_data(
            Namespace='StreamForge/Alerts',
            MetricData=[{
                'MetricName': 'AlertsSent',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': [
                    {'Name': 'PipelineId', 'Value': pipeline_id},
                    {'Name': 'AlertType', 'Value': alert_type},
                    {'Name': 'Severity', 'Value': severity.value}
                ]
            }]
        )

        return alert_record

    def _get_alert_config(self, pipeline_id: str) -> Dict[str, Any]:
        """Get alert configuration for pipeline."""
        try:
            response = self.config_table.get_item(Key={'pipeline_id': pipeline_id})
            return response.get('Item', self._get_default_config())
        except Exception as e:
            logger.warning(f"Failed to get alert config: {e}, using defaults")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default alert configuration."""
        return {
            'channels': [AlertChannel.EMAIL.value],
            'severity_threshold': AlertSeverity.WARNING.value,
            'enabled_alert_types': ['failure', 'anomaly', 'cost_spike', 'quality_issue'],
            'quiet_hours': None,  # {'start': '22:00', 'end': '08:00'}
            'rate_limit': {'max_alerts': 10, 'window_minutes': 60}
        }

    def _should_send_alert(
        self,
        config: Dict[str, Any],
        alert_type: str,
        severity: AlertSeverity
    ) -> bool:
        """Check if alert should be sent based on configuration."""
        # Check if alert type is enabled
        if alert_type not in config.get('enabled_alert_types', []):
            return False

        # Check severity threshold
        severity_order = ['info', 'warning', 'error', 'critical']
        threshold = config.get('severity_threshold', 'warning')

        if severity_order.index(severity.value) < severity_order.index(threshold):
            return False

        # Check quiet hours
        quiet_hours = config.get('quiet_hours')
        if quiet_hours:
            current_time = datetime.utcnow().time()
            start = datetime.strptime(quiet_hours['start'], '%H:%M').time()
            end = datetime.strptime(quiet_hours['end'], '%H:%M').time()

            if start <= current_time <= end:
                # Only send critical alerts during quiet hours
                if severity != AlertSeverity.CRITICAL:
                    return False

        # Check rate limit
        rate_limit = config.get('rate_limit')
        if rate_limit and self._is_rate_limited(config['pipeline_id'], rate_limit):
            return False

        return True

    def _is_rate_limited(self, pipeline_id: str, rate_limit: Dict[str, int]) -> bool:
        """Check if pipeline has exceeded alert rate limit."""
        window_minutes = rate_limit['window_minutes']
        max_alerts = rate_limit['max_alerts']

        # Query recent alerts
        from datetime import timedelta
        cutoff_time = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()

        response = self.alerts_table.query(
            IndexName='pipeline-timestamp-index',
            KeyConditionExpression='pipeline_id = :pid AND #ts > :cutoff',
            ExpressionAttributeNames={'#ts': 'timestamp'},
            ExpressionAttributeValues={
                ':pid': pipeline_id,
                ':cutoff': cutoff_time
            }
        )

        recent_alert_count = len(response.get('Items', []))
        return recent_alert_count >= max_alerts

    def _send_slack_alert(self, config: Dict[str, Any], alert: Dict[str, Any]):
        """Send alert to Slack."""
        webhook_url = config.get('slack_webhook_url')
        if not webhook_url:
            raise ValueError("Slack webhook URL not configured")

        # Map severity to color
        color_map = {
            'info': '#36A64F',      # green
            'warning': '#FFA500',   # orange
            'error': '#FF0000',     # red
            'critical': '#8B0000'   # dark red
        }

        payload = {
            'text': f"*{alert['title']}*",
            'attachments': [{
                'color': color_map.get(alert['severity'], '#808080'),
                'fields': [
                    {
                        'title': 'Pipeline',
                        'value': alert['pipeline_id'],
                        'short': True
                    },
                    {
                        'title': 'Severity',
                        'value': alert['severity'].upper(),
                        'short': True
                    },
                    {
                        'title': 'Alert Type',
                        'value': alert['alert_type'].replace('_', ' ').title(),
                        'short': True
                    },
                    {
                        'title': 'Time',
                        'value': alert['timestamp'],
                        'short': True
                    }
                ],
                'text': alert['message'],
                'footer': 'StreamForge Alerts',
                'ts': int(datetime.fromisoformat(alert['timestamp']).timestamp())
            }]
        }

        # Add metadata fields
        if alert.get('metadata'):
            for key, value in alert['metadata'].items():
                payload['attachments'][0]['fields'].append({
                    'title': key.replace('_', ' ').title(),
                    'value': str(value),
                    'short': True
                })

        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()

    def _send_email_alert(self, config: Dict[str, Any], alert: Dict[str, Any]):
        """Send alert via email (SNS)."""
        topic_arn = config.get('email_topic_arn')
        if not topic_arn:
            raise ValueError("Email SNS topic ARN not configured")

        subject = f"[{alert['severity'].upper()}] {alert['title']}"

        message_body = f"""
StreamForge Alert

Pipeline: {alert['pipeline_id']}
Alert Type: {alert['alert_type'].replace('_', ' ').title()}
Severity: {alert['severity'].upper()}
Time: {alert['timestamp']}

{alert['message']}

---
Additional Details:
{json.dumps(alert.get('metadata', {}), indent=2)}

---
View dashboard: https://dashboard.streamforge.com/pipeline/{alert['pipeline_id']}
"""

        sns.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=message_body
        )

    def _send_sns_alert(self, config: Dict[str, Any], alert: Dict[str, Any]):
        """Send alert to SNS topic."""
        topic_arn = config.get('sns_topic_arn')
        if not topic_arn:
            raise ValueError("SNS topic ARN not configured")

        sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps(alert),
            Subject=alert['title'],
            MessageAttributes={
                'pipeline_id': {'DataType': 'String', 'StringValue': alert['pipeline_id']},
                'severity': {'DataType': 'String', 'StringValue': alert['severity']},
                'alert_type': {'DataType': 'String', 'StringValue': alert['alert_type']}
            }
        )

    def _send_webhook_alert(self, config: Dict[str, Any], alert: Dict[str, Any]):
        """Send alert to custom webhook."""
        webhook_url = config.get('webhook_url')
        if not webhook_url:
            raise ValueError("Webhook URL not configured")

        response = requests.post(webhook_url, json=alert, timeout=10)
        response.raise_for_status()

    def configure_alerts(
        self,
        pipeline_id: str,
        channels: List[str],
        severity_threshold: str = 'warning',
        enabled_alert_types: Optional[List[str]] = None,
        slack_webhook_url: Optional[str] = None,
        email_topic_arn: Optional[str] = None,
        sns_topic_arn: Optional[str] = None,
        webhook_url: Optional[str] = None,
        quiet_hours: Optional[Dict[str, str]] = None,
        rate_limit: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Configure alert settings for pipeline.

        Args:
            pipeline_id: Pipeline identifier
            channels: List of channels to send alerts to
            severity_threshold: Minimum severity to trigger alerts
            enabled_alert_types: List of enabled alert types
            slack_webhook_url: Slack webhook URL
            email_topic_arn: SNS topic ARN for email
            sns_topic_arn: SNS topic ARN for raw alerts
            webhook_url: Custom webhook URL
            quiet_hours: Quiet hours config {'start': 'HH:MM', 'end': 'HH:MM'}
            rate_limit: Rate limit config {'max_alerts': N, 'window_minutes': M}

        Returns:
            Saved configuration
        """
        config = {
            'pipeline_id': pipeline_id,
            'channels': channels,
            'severity_threshold': severity_threshold,
            'enabled_alert_types': enabled_alert_types or ['failure', 'anomaly', 'cost_spike', 'quality_issue'],
            'updated_at': datetime.utcnow().isoformat()
        }

        if slack_webhook_url:
            config['slack_webhook_url'] = slack_webhook_url
        if email_topic_arn:
            config['email_topic_arn'] = email_topic_arn
        if sns_topic_arn:
            config['sns_topic_arn'] = sns_topic_arn
        if webhook_url:
            config['webhook_url'] = webhook_url
        if quiet_hours:
            config['quiet_hours'] = quiet_hours
        if rate_limit:
            config['rate_limit'] = rate_limit

        self.config_table.put_item(Item=config)
        return config

    def get_alert_history(
        self,
        pipeline_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent alert history for pipeline."""
        response = self.alerts_table.query(
            IndexName='pipeline-timestamp-index',
            KeyConditionExpression='pipeline_id = :pid',
            ExpressionAttributeValues={':pid': pipeline_id},
            Limit=limit,
            ScanIndexForward=False  # Most recent first
        )

        return response.get('Items', [])


# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for sending alerts.

    Can be triggered by:
    - CloudWatch Events (pipeline failures)
    - EventBridge rules (scheduled checks)
    - Direct invocation (manual alerts)
    """
    manager = AlertManager()

    # Extract alert details from event
    pipeline_id = event.get('pipeline_id')
    alert_type = event.get('alert_type')
    severity = AlertSeverity(event.get('severity', 'warning'))
    title = event.get('title')
    message = event.get('message')
    metadata = event.get('metadata', {})

    if not all([pipeline_id, alert_type, title, message]):
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing required fields'})
        }

    try:
        result = manager.send_alert(
            pipeline_id=pipeline_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            metadata=metadata
        )

        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
