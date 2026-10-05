# Alerting System

Multi-channel alerting system for StreamForge with Slack, email, SNS, and webhook support.

---

## Features

- **Multiple Channels** - Slack, email (SNS), SNS topics, custom webhooks
- **Severity Levels** - Info, Warning, Error, Critical
- **Alert Types** - Pipeline failures, data anomalies, cost spikes, quality issues
- **Quiet Hours** - Suppress non-critical alerts during off-hours
- **Rate Limiting** - Prevent alert fatigue with configurable limits
- **Alert History** - Track all sent alerts with delivery status

---

## Quick Start

### Configure Alerts

```bash
# Dashboard
open https://dashboard.streamforge.com/alerts?pipeline=pipeline-123
```

### Python SDK

```python
from streamforge import StreamForge

sf = StreamForge('https://api.streamforge.com')

# Configure alerts
sf.configure_alerts(
    pipeline_id='pipeline-123',
    channels=['slack', 'email'],
    severity_threshold='warning',
    slack_webhook_url='https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
    email_topic_arn='arn:aws:sns:us-east-1:123456789012:streamforge-alerts'
)

# Send manual alert
sf.send_alert(
    pipeline_id='pipeline-123',
    alert_type='failure',
    severity='error',
    title='Pipeline Processing Failed',
    message='Lambda timeout after 15 minutes',
    metadata={'function': 'transform-handler', 'error': 'Task timed out'}
)
```

---

## Alert Types

### 1. Pipeline Failures

Triggered when:
- Lambda function errors
- Lambda timeouts
- Step Function failures
- Kinesis throttling

**Example:**
```json
{
  "alert_type": "failure",
  "severity": "error",
  "title": "Pipeline Transform Failed",
  "message": "Lambda function 'transform-handler' threw exception: KeyError('user_id')",
  "metadata": {
    "function": "transform-handler",
    "error_type": "KeyError",
    "stack_trace": "..."
  }
}
```

---

### 2. Data Anomalies

Triggered when:
- ML anomaly detection score > threshold
- Sudden traffic spikes/drops
- Unusual data patterns

**Example:**
```json
{
  "alert_type": "anomaly",
  "severity": "warning",
  "title": "High Anomaly Rate Detected",
  "message": "Anomaly rate spiked to 15% (normal: 2-3%)",
  "metadata": {
    "anomaly_rate": 0.15,
    "events_analyzed": 10000,
    "anomalies_detected": 1500
  }
}
```

---

### 3. Cost Spikes

Triggered when:
- AWS costs exceed expected range
- Daily spend > threshold
- Unexpected service charges

**Example:**
```json
{
  "alert_type": "cost_spike",
  "severity": "warning",
  "title": "AWS Cost Spike Detected",
  "message": "Lambda cost jumped to $95 (expected: $30)",
  "metadata": {
    "service": "AWS Lambda",
    "expected_cost": 30.0,
    "actual_cost": 95.0,
    "impact": 65.0
  }
}
```

---

### 4. Data Quality Issues

Triggered when:
- Data quality score drops below threshold
- Schema validation failures
- Missing required fields

**Example:**
```json
{
  "alert_type": "quality_issue",
  "severity": "error",
  "title": "Data Quality Score Dropped",
  "message": "Quality score fell to 65% (threshold: 90%)",
  "metadata": {
    "quality_score": 0.65,
    "failed_checks": ["missing_fields", "invalid_types"],
    "events_affected": 2500
  }
}
```

---

## Notification Channels

### Slack

**Setup:**
1. Create Slack incoming webhook: https://api.slack.com/messaging/webhooks
2. Configure in dashboard or via API

**Example Slack Alert:**
```
🚨 Pipeline Processing Failed

Pipeline: pipeline-123
Severity: ERROR
Alert Type: Failure
Time: 2026-09-29T10:30:00Z

Lambda function 'transform-handler' threw exception: KeyError('user_id')

Function: transform-handler
Error Type: KeyError

StreamForge Alerts
```

---

### Email (SNS)

**Setup:**
1. Create SNS topic for email notifications
2. Subscribe email addresses to topic
3. Configure topic ARN in dashboard

**Email Format:**
```
Subject: [ERROR] Pipeline Processing Failed

StreamForge Alert

Pipeline: pipeline-123
Alert Type: Failure
Severity: ERROR
Time: 2026-09-29T10:30:00Z

Lambda function 'transform-handler' threw exception: KeyError('user_id')

---
Additional Details:
{
  "function": "transform-handler",
  "error_type": "KeyError",
  "stack_trace": "..."
}

---
View dashboard: https://dashboard.streamforge.com/pipeline/pipeline-123
```

---

### SNS Topic

**Setup:**
Send raw JSON to SNS topic for downstream processing.

**Use cases:**
- Integrate with PagerDuty
- Forward to Lambda for custom processing
- Fan-out to multiple subscribers

---

### Custom Webhook

**Setup:**
Configure webhook URL to receive POST requests with alert payload.

**Payload:**
```json
{
  "alert_id": "alert-1727604600000",
  "pipeline_id": "pipeline-123",
  "alert_type": "failure",
  "severity": "error",
  "title": "Pipeline Processing Failed",
  "message": "Lambda function threw exception",
  "metadata": {...},
  "timestamp": "2026-09-29T10:30:00Z",
  "delivered_to": ["slack", "email"]
}
```

---

## Configuration

### Severity Threshold

Only send alerts at or above configured severity level.

```python
# Only send ERROR and CRITICAL alerts
sf.configure_alerts(
    pipeline_id='pipeline-123',
    severity_threshold='error'  # info < warning < error < critical
)
```

---

### Quiet Hours

Suppress non-critical alerts during off-hours (only CRITICAL alerts sent).

```python
sf.configure_alerts(
    pipeline_id='pipeline-123',
    quiet_hours={'start': '22:00', 'end': '08:00'}  # UTC
)
```

**Behavior:**
- During quiet hours: Only CRITICAL alerts sent
- Outside quiet hours: All alerts sent (per severity threshold)

---

### Rate Limiting

Prevent alert fatigue by limiting alerts per time window.

```python
sf.configure_alerts(
    pipeline_id='pipeline-123',
    rate_limit={'max_alerts': 10, 'window_minutes': 60}
)
```

**Behavior:**
- After 10 alerts in 60 minutes, additional alerts suppressed
- Alert history still recorded (marked as "suppressed")
- Resets after time window passes

---

## Alert History

Track all sent alerts with delivery status.

### Dashboard

```bash
# View alert history
open https://dashboard.streamforge.com/alerts?pipeline=pipeline-123
```

### API

```bash
# Get recent alerts
curl https://api.streamforge.com/alerts/history/pipeline-123

# Response
{
  "alerts": [
    {
      "alert_id": "alert-1727604600000",
      "pipeline_id": "pipeline-123",
      "alert_type": "failure",
      "severity": "error",
      "title": "Pipeline Processing Failed",
      "message": "Lambda timeout after 15 minutes",
      "timestamp": "2026-09-29T10:30:00Z",
      "delivered_to": ["slack", "email"],
      "delivery_status": {
        "slack": "success",
        "email": "success"
      },
      "status": "delivered"
    }
  ]
}
```

---

## Automatic Alerts

Alerts are automatically triggered by StreamForge monitoring.

### Pipeline Failures

**Trigger:** CloudWatch Logs error patterns, Lambda failures

```python
# Automatically sent when Lambda fails
{
  "alert_type": "failure",
  "severity": "error",
  "title": "Pipeline Transform Failed",
  "message": "Lambda function 'transform-handler' threw exception"
}
```

---

### Cost Anomalies

**Trigger:** Cost Anomaly Detection (daily check)

```python
# Automatically sent when cost spike detected
{
  "alert_type": "cost_spike",
  "severity": "warning",
  "title": "AWS Cost Spike Detected",
  "message": "Lambda cost jumped to $95 (expected: $30)"
}
```

---

### Data Quality

**Trigger:** Quality score drops below threshold (real-time)

```python
# Automatically sent when quality drops
{
  "alert_type": "quality_issue",
  "severity": "error",
  "title": "Data Quality Score Dropped",
  "message": "Quality score fell to 65% (threshold: 90%)"
}
```

---

## Manual Alerts

Send alerts programmatically from your code.

### Python SDK

```python
from streamforge import AlertManager, AlertSeverity

manager = AlertManager()

# Send custom alert
manager.send_alert(
    pipeline_id='pipeline-123',
    alert_type='custom',
    severity=AlertSeverity.WARNING,
    title='Custom Business Logic Alert',
    message='Detected suspicious activity in payment processing',
    metadata={'user_id': '12345', 'transaction_amount': 10000}
)
```

---

### Lambda Invocation

```python
import boto3
import json

lambda_client = boto3.client('lambda')

# Invoke alert Lambda
lambda_client.invoke(
    FunctionName='streamforge-alert-manager',
    InvocationType='Event',  # Async
    Payload=json.dumps({
        'pipeline_id': 'pipeline-123',
        'alert_type': 'custom',
        'severity': 'warning',
        'title': 'Custom Alert',
        'message': 'Your message here',
        'metadata': {'key': 'value'}
    })
)
```

---

## CDK Deployment

```typescript
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';

// SNS topic for email alerts
const alertTopic = new sns.Topic(this, 'AlertTopic', {
  displayName: 'StreamForge Alerts'
});

// Subscribe email
alertTopic.addSubscription(
  new subscriptions.EmailSubscription('team@example.com')
);

// Alert manager Lambda
const alertManager = new lambda.Function(this, 'AlertManager', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'manager.lambda_handler',
  code: lambda.Code.fromAsset('services/alerts'),
  environment: {
    ALERT_CONFIG_TABLE: configTable.tableName,
    ALERTS_TABLE: alertsTable.tableName
  }
});

// Grant permissions
configTable.grantReadWriteData(alertManager);
alertsTable.grantReadWriteData(alertManager);
alertTopic.grantPublish(alertManager);
```

---

## Best Practices

### 1. Start with Email Only

```python
# Begin with email, add Slack after testing
sf.configure_alerts(
    pipeline_id='pipeline-123',
    channels=['email'],
    severity_threshold='warning'
)
```

---

### 2. Use Quiet Hours for Non-Critical Pipelines

```python
# Dev/staging pipelines: quiet hours
sf.configure_alerts(
    pipeline_id='dev-pipeline',
    quiet_hours={'start': '18:00', 'end': '09:00'}
)

# Production: always alert
sf.configure_alerts(
    pipeline_id='prod-pipeline',
    quiet_hours=None
)
```

---

### 3. Enable Rate Limiting

```python
# Prevent alert storms
sf.configure_alerts(
    pipeline_id='pipeline-123',
    rate_limit={'max_alerts': 10, 'window_minutes': 60}
)
```

---

### 4. Set Appropriate Severity Thresholds

```python
# Production: WARNING and above
sf.configure_alerts(
    pipeline_id='prod-pipeline',
    severity_threshold='warning'
)

# Development: ERROR and above only
sf.configure_alerts(
    pipeline_id='dev-pipeline',
    severity_threshold='error'
)
```

---

## Troubleshooting

### Alerts Not Being Sent

**Check configuration:**
```bash
curl https://api.streamforge.com/alerts/config/pipeline-123
```

**Common issues:**
- Alert type not enabled in `enabled_alert_types`
- Severity below threshold
- Rate limit exceeded
- During quiet hours (non-critical alert)

---

### Slack Webhook Failing

**Verify webhook URL:**
```bash
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  -H 'Content-Type: application/json' \
  -d '{"text": "Test message"}'
```

**Common issues:**
- Invalid webhook URL
- Webhook expired/revoked
- Slack app permissions changed

---

### Too Many Alerts (Alert Fatigue)

**Solutions:**
1. Increase severity threshold (`error` instead of `warning`)
2. Enable rate limiting
3. Configure quiet hours
4. Disable non-critical alert types

```python
# Reduce alert volume
sf.configure_alerts(
    pipeline_id='pipeline-123',
    severity_threshold='error',  # Only errors and critical
    enabled_alert_types=['failure', 'cost_spike'],  # Skip anomalies/quality
    rate_limit={'max_alerts': 5, 'window_minutes': 60}
)
```

---

## Alert Aggregation

During an incident, firing one notification per alert buries operators. The
aggregator collects alerts over a time window and emits a single **digest**,
collapsing similar alerts (same type + severity) into one line with a count.

```python
from streamforge.alerts import AlertAggregator

aggregator = AlertAggregator()

# Build a digest of the last 15 minutes
digest = aggregator.build_digest('pipeline-123', window_minutes=15)
# {
#   'total_alerts': 42,
#   'unique_groups': 3,
#   'highest_severity': 'error',
#   'summary': '42 alerts (3 distinct) for pipeline-123 — highest severity: ERROR',
#   'groups': [{'alert_type': 'failure', 'severity': 'error', 'count': 38, ...}, ...]
# }

# Render for Slack
slack_payload = aggregator.format_slack_digest(digest)
```

### Suppressing individual alerts

Once the same (type, severity) fires past a threshold in the window, individual
notifications are suppressed — the digest covers them. **Critical alerts are
never suppressed.**

```python
if aggregator.should_suppress_individual('pipeline-123', 'failure', 'error', threshold=3):
    # Skip the individual notification; the scheduled digest will include it
    pass
else:
    manager.send_alert(...)
```

Groups are ranked highest-severity-first, then by count, so the digest leads
with what matters most.

---

## Roadmap

- **Custom alert rules** - Define custom triggers (e.g., "Alert if latency > 5s")
- **PagerDuty integration** - Native PagerDuty support
- **Mobile push notifications** - iOS/Android app alerts
- **Alert templates** - Customizable message templates

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
