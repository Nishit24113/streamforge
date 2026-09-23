# StreamForge Monitoring & Alerting

## Overview

StreamForge includes production-grade monitoring with CloudWatch dashboards, custom metrics, and automated alerts via SNS.

---

## CloudWatch Dashboard

**Access**: AWS Console → CloudWatch → Dashboards → `StreamForge-Monitoring`

Or via CDK output after deployment:
```bash
./deploy.sh --profile sandbox2025
# Look for: MonitoringStack.DashboardUrl
```

### Dashboard Widgets

**Row 1: Ingestion Metrics**
- Kinesis incoming records/bytes per minute
- Kinesis throttling & error rates

**Row 2: Pipeline Processing**
- Step Functions execution counts (started/succeeded/failed)
- Pipeline execution duration (average)

**Row 3: DynamoDB Metrics**
- Run history table consumed read/write capacity
- Total pipeline runs in last 24 hours

**Row 4: Anomaly Detection**
- Anomalies detected over time (by pipeline)
- Anomaly detection rate (%)

---

## Custom Metrics

All metrics are published to the `StreamForge` namespace with dimensions by `PipelineId`.

| Metric Name | Unit | Description |
|-------------|------|-------------|
| `EventsProcessed` | Count | Total events processed by anomaly detector |
| `AnomaliesDetected` | Count | Number of anomalies flagged |
| `AnomalyRate` | Percent | (anomalies / events) × 100 |

**Published by**: `anomaly-detector` Lambda after each pipeline run

**How to query**:
```bash
aws cloudwatch get-metric-statistics \
  --namespace StreamForge \
  --metric-name AnomaliesDetected \
  --dimensions Name=PipelineId,Value=ecommerce-events \
  --start-time 2026-09-22T00:00:00Z \
  --end-time 2026-09-23T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

---

## Alarms & Alerts

### SNS Topic: `streamforge-alerts`

**Configure email notifications**:
```bash
# Set your email before deployment
export ALERT_EMAIL=your-email@example.com
./deploy.sh --profile sandbox2025

# Subscribe to the SNS topic (check email for confirmation)
```

**Or subscribe manually**:
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-west-2:ACCOUNT_ID:streamforge-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com
```

---

### Active Alarms

#### 1. **High Pipeline Failure Rate**
- **Alarm**: `StreamForge-HighPipelineFailureRate`
- **Threshold**: >10% failure rate
- **Evaluation**: 2 consecutive periods of 5 minutes
- **Action**: SNS alert
- **What it means**: Step Functions pipelines are failing frequently
- **Investigate**: 
  - Check Step Functions execution history in AWS Console
  - Review Lambda CloudWatch logs for errors
  - Verify pipeline configurations in DynamoDB

#### 2. **High Anomaly Rate**
- **Alarm**: `StreamForge-HighAnomalyRate`
- **Threshold**: >20% anomaly rate
- **Evaluation**: 3 consecutive periods of 5 minutes
- **Action**: SNS alert
- **What it means**: Data quality issue or legitimate anomaly spike
- **Investigate**:
  - Check dashboard for specific pipeline
  - Review anomaly alerts table in DynamoDB
  - Validate data source isn't sending corrupted data

#### 3. **Kinesis Throttling**
- **Alarm**: `StreamForge-KinesisThrottling`
- **Threshold**: >10 throttled writes per minute
- **Evaluation**: 2 consecutive periods of 1 minute
- **Action**: SNS alert
- **What it means**: Ingestion rate exceeds Kinesis on-demand capacity
- **Investigate**:
  - Check ingestion patterns (bursty vs steady)
  - Consider batching at source
  - Verify shard count (on-demand should auto-scale)

#### 4. **No Data Ingestion**
- **Alarm**: `StreamForge-NoDataIngestion`
- **Threshold**: <1 record in 30 minutes
- **Evaluation**: 1 period
- **Action**: SNS alert
- **What it means**: Pipeline is idle (could be expected or a problem)
- **Investigate**:
  - Verify data sources are still sending
  - Check API Gateway logs
  - Review webhook endpoints are accessible

---

## Metric Publisher Lambda

**Function**: `streamforge-metric-publisher`  
**Use case**: Publish custom metrics from external systems (EventBridge, DynamoDB Streams, etc.)

**Trigger manually**:
```bash
aws lambda invoke \
  --function-name streamforge-metric-publisher \
  --payload '{
    "anomalies_detected": 5,
    "events_processed": 100,
    "pipeline_id": "my-pipeline"
  }' \
  response.json
```

**Integrate with EventBridge**:
```json
{
  "source": ["streamforge"],
  "detail-type": ["Pipeline Completed"],
  "detail": {
    "anomalies_detected": 5,
    "events_processed": 100,
    "pipeline_id": "ecommerce-events"
  }
}
```

---

## Cost Considerations

| Service | Cost Driver | Estimated Monthly Cost |
|---------|-------------|----------------------|
| CloudWatch Dashboard | 3 dashboards × $3 | $3 |
| CloudWatch Alarms | 4 alarms × $0.10 | $0.40 |
| CloudWatch Metrics | Custom metrics | $0.30/metric × 3 = $0.90 |
| SNS | Email notifications | $0 (first 1,000 free) |
| **Total** | | **~$4.30/month** |

**Note**: Most services stay within free tier for dev/test workloads.

---

## Troubleshooting

### Alarm Firing Unexpectedly

**Check current metric value**:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/States \
  --metric-name ExecutionsFailed \
  --dimensions Name=StateMachineArn,Value=YOUR_STATE_MACHINE_ARN \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

**Disable alarm temporarily**:
```bash
aws cloudwatch disable-alarm-actions \
  --alarm-names StreamForge-HighPipelineFailureRate
```

**Re-enable**:
```bash
aws cloudwatch enable-alarm-actions \
  --alarm-names StreamForge-HighPipelineFailureRate
```

### Metrics Not Appearing

1. **Check Lambda CloudWatch logs**:
   ```bash
   aws logs tail /aws/lambda/streamforge-anomaly-detector --follow
   ```

2. **Verify IAM permissions**:
   - Anomaly detector Lambda must have `cloudwatch:PutMetricData`
   - Check execution role in AWS Console

3. **Manual metric test**:
   ```bash
   aws cloudwatch put-metric-data \
     --namespace StreamForge \
     --metric-name TestMetric \
     --value 1
   ```

### Dashboard Not Showing Data

- **Wait 5-15 minutes** after deployment (metric propagation delay)
- Verify pipelines have actually run (check DynamoDB run history)
- Ensure time range in dashboard is set correctly (last 3 hours)

---

## Best Practices

1. **Set up email alerts** immediately after deployment
2. **Review dashboard weekly** to understand baseline behavior
3. **Tune alarm thresholds** based on your actual traffic patterns
4. **Archive old alarms** - SNS delivers to dead letter queue after 3 retries
5. **Cost optimization**: Delete unused custom metrics after 15 months (auto-expire)

---

## Integration with Existing Tools

### Grafana
Use CloudWatch data source plugin:
```yaml
datasources:
  - name: StreamForge
    type: cloudwatch
    jsonData:
      defaultRegion: us-west-2
      customMetricsNamespaces: StreamForge
```

### Datadog
Forward CloudWatch metrics via AWS integration:
```bash
# Install Datadog CloudWatch integration
# Select namespace: StreamForge
# Enable metric collection
```

### PagerDuty
Subscribe SNS topic to PagerDuty email endpoint:
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-west-2:ACCOUNT_ID:streamforge-alerts \
  --protocol email \
  --notification-endpoint streamforge@YOUR_SUBDOMAIN.pagerduty.com
```

---

## Metrics Retention

| Metric Age | Granularity | Retention |
|------------|-------------|-----------|
| < 3 hours | 1 minute | 15 days |
| < 15 days | 5 minutes | 63 days |
| < 63 days | 1 hour | 15 months |
| < 15 months | Aggregated | Deleted |

**To extend retention**: Export to S3 using CloudWatch Logs export or Kinesis Firehose.

---

## Next Steps

- **Day 2 Feature**: Pipeline templates with pre-configured monitoring
- **Day 3 Feature**: Advanced X-Ray tracing for distributed request tracking
- **Day 7 Feature**: Structured logging with correlation IDs for full observability
