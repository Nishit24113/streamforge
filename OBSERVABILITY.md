# X-Ray Tracing & Observability

Complete observability with distributed tracing, latency analysis, and service maps.

---

## Overview

StreamForge uses AWS X-Ray for distributed tracing across:

| Component | Traced Operations | Metrics Captured |
|-----------|-------------------|------------------|
| **API Gateway** | HTTP requests | Method, path, status code |
| **Lambda Functions** | All handlers | Duration, errors, memory |
| **Kinesis** | put_records, get_records | Record count, throughput |
| **Step Functions** | Pipeline stages | Stage duration, transitions |
| **DynamoDB** | get_item, put_item, query | Table, key, latency |
| **S3** | put_object, get_object | Bucket, key, size |

**Three Pillars of Observability:**
1. **Metrics** - CloudWatch metrics (covered in MONITORING.md)
2. **Logs** - CloudWatch Logs (Lambda execution logs)
3. **Traces** - X-Ray distributed tracing (this document)

---

## Why X-Ray Tracing?

### Problem: Distributed Systems Are Hard to Debug

**Without X-Ray:**
- "Pipeline is slow" → Which stage? Lambda? S3? DynamoDB?
- "Some requests fail" → Where exactly? Kinesis? Validation? Transform?
- "Latency spiked at 3pm" → What changed? Which component?

**With X-Ray:**
- See request flow: API Gateway → Lambda → Kinesis → Step Functions → S3
- Latency breakdown: Validate (50ms) + Transform (200ms) + S3 (100ms) = 350ms total
- Error correlation: Lambda timeout caused by slow DynamoDB query

---

## Quick Start

### Enable X-Ray on Lambda

```typescript
// infrastructure/lib/processing-stack.ts
new lambda.Function(this, 'Transformer', {
  functionName: 'streamforge-transformer',
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'handler.lambda_handler',
  code: lambda.Code.fromAsset('./services/processing/transformer'),
  tracing: lambda.Tracing.ACTIVE,  // ✅ Enable X-Ray
});
```

### Instrument Lambda Handler

```python
from streamforge.tracing import trace_lambda_handler, propagate_trace_id

@trace_lambda_handler  # Automatic tracing
def lambda_handler(event, context):
    pipeline_id = event['pipeline_id']
    run_id = event['run_id']

    # Propagate trace ID through pipeline
    trace_id = propagate_trace_id(pipeline_id, run_id)

    # Your handler logic...
    return {'statusCode': 200, 'trace_id': trace_id}
```

That's it! X-Ray now traces this Lambda and all AWS SDK calls (S3, DynamoDB, Kinesis).

---

## Tracing Pipeline Stages

Break down latency by pipeline stage.

### Example: Transformer Lambda

```python
from streamforge.tracing import trace_lambda_handler, trace_pipeline_stage

@trace_lambda_handler
def lambda_handler(event, context):
    events = event.get('events', [])

    # Each stage is traced separately
    validated = validate_events(events)
    transformed = transform_events(validated)
    written = write_to_s3(transformed)

    return {'events_processed': len(written)}


@trace_pipeline_stage('validate')
def validate_events(events):
    """Validation stage - traced with subsegment."""
    return [e for e in events if is_valid(e)]


@trace_pipeline_stage('transform')
def transform_events(events):
    """Transform stage - traced with subsegment."""
    return [apply_transforms(e) for e in events]


@trace_pipeline_stage('write_s3')
def write_to_s3(events):
    """S3 write stage - traced with subsegment."""
    from streamforge.tracing import trace_s3_operation

    with trace_s3_operation('put_object', 'streamforge-lake', 'clean/data.json'):
        s3.put_object(Bucket='streamforge-lake', Key='clean/data.json', Body=json.dumps(events))

    return events
```

### X-Ray Trace Output

```
Lambda: streamforge-transformer (350ms)
  ├─ validate (50ms)
  ├─ transform (200ms)
  └─ write_s3 (100ms)
       └─ s3.put_object (85ms)
```

**Now you know:** Transform stage is the bottleneck (200ms of 350ms total).

---

## Tracing AWS SDK Operations

### S3 Operations

```python
from streamforge.tracing import trace_s3_operation

# Trace S3 put
with trace_s3_operation('put_object', 'streamforge-lake', 'data/file.json'):
    s3.put_object(Bucket='streamforge-lake', Key='data/file.json', Body=data)

# Trace S3 get
with trace_s3_operation('get_object', 'streamforge-lake', 'data/file.json'):
    obj = s3.get_object(Bucket='streamforge-lake', Key='data/file.json')
```

**X-Ray shows:**
- Bucket and key annotations
- Duration per operation
- Errors with stack traces

---

### DynamoDB Operations

```python
from streamforge.tracing import trace_dynamodb_operation

# Trace DynamoDB get
with trace_dynamodb_operation('get_item', 'streamforge-pipelines', 'pipeline-123'):
    result = pipeline_table.get_item(Key={'pipeline_id': 'pipeline-123'})

# Trace DynamoDB put
with trace_dynamodb_operation('put_item', 'streamforge-runs', 'run-456'):
    run_table.put_item(Item={'run_id': 'run-456', 'status': 'COMPLETED'})
```

**X-Ray shows:**
- Table name
- Key being accessed
- Query latency
- Throttling errors

---

### Kinesis Operations

```python
from streamforge.tracing import trace_kinesis_operation

# Trace Kinesis put_records
with trace_kinesis_operation('put_records', 'streamforge-events', len(records)):
    response = kinesis.put_records(StreamName='streamforge-events', Records=records)
```

**X-Ray shows:**
- Stream name
- Record count
- Throughput (records/sec)
- ProvisionedThroughputExceededException if throttled

---

## Propagating Trace IDs

Enable end-to-end tracing across async components.

### Generate Trace ID

```python
from streamforge.tracing import propagate_trace_id

@trace_lambda_handler
def ingestion_handler(event, context):
    pipeline_id = event['pipeline_id']
    run_id = f'run-{uuid.uuid4().hex[:12]}'

    # Generate trace ID
    trace_id = propagate_trace_id(pipeline_id, run_id)

    # Pass trace ID to Kinesis
    kinesis.put_records(
        StreamName='streamforge-events',
        Records=[{
            'Data': json.dumps({'trace_id': trace_id, **event_data}),
            'PartitionKey': pipeline_id
        }]
    )

    return {'trace_id': trace_id}
```

### Receive Trace ID

```python
from streamforge.tracing import extract_trace_id

@trace_lambda_handler
def stream_processor(event, context):
    # Extract trace ID from Kinesis record
    trace_id = extract_trace_id(event)

    if trace_id:
        xray_recorder.put_annotation('parent_trace_id', trace_id)

    # Now this Lambda's trace is linked to parent
    process_records(event['Records'])
```

**Result:** X-Ray shows single trace across:
1. API Gateway (ingestion endpoint)
2. Lambda (ingestion handler)
3. Kinesis (stream)
4. Lambda (stream processor)
5. Step Functions (pipeline)
6. Lambda (transform/aggregate)
7. S3 (final write)

---

## Service Map Visualization

X-Ray automatically builds service dependency graph.

### Example Service Map

```
┌─────────────┐       ┌────────────┐       ┌──────────────┐
│ API Gateway │──────>│  Lambda    │──────>│   Kinesis    │
└─────────────┘       │ (Ingest)   │       │   Stream     │
                      └────────────┘       └──────────────┘
                                                   │
                                                   v
                      ┌────────────┐       ┌──────────────┐
                      │  Lambda    │<──────│    Step      │
                      │(Transform) │       │  Functions   │
                      └────────────┘       └──────────────┘
                             │
                             v
                      ┌────────────┐       ┌──────────────┐
                      │     S3     │       │  DynamoDB    │
                      │ Data Lake  │       │ (Metadata)   │
                      └────────────┘       └──────────────┘
```

**Metrics shown per edge:**
- Average latency
- Request count
- Error rate
- Throttle rate

---

## X-Ray Insights Queries

Query traces programmatically.

### Average Latency by Pipeline

```python
import boto3

xray = boto3.client('xray')

response = xray.get_trace_summaries(
    StartTime=datetime.utcnow() - timedelta(hours=1),
    EndTime=datetime.utcnow(),
    FilterExpression='annotation.pipeline_id = "ecommerce"'
)

latencies = [trace['Duration'] for trace in response['TraceSummaries']]
avg_latency = sum(latencies) / len(latencies)

print(f"Average pipeline latency: {avg_latency:.1f}s")
```

### Error Rate by Service

```python
# Find all traces with errors in last hour
response = xray.get_trace_summaries(
    StartTime=datetime.utcnow() - timedelta(hours=1),
    EndTime=datetime.utcnow(),
    FilterExpression='error = true'
)

# Group by service
errors_by_service = {}
for trace in response['TraceSummaries']:
    trace_detail = xray.get_trace_graph(TraceIds=[trace['Id']])

    for service in trace_detail['Services']:
        name = service['Name']
        errors_by_service[name] = errors_by_service.get(name, 0) + 1

print("Errors by service:")
for service, count in sorted(errors_by_service.items(), key=lambda x: -x[1]):
    print(f"  {service}: {count} errors")
```

### P95 Latency Breakdown

```sql
-- CloudWatch Logs Insights query
SELECT
    annotation.pipeline_id,
    PERCENTILE(response_time, 95) as p95_latency_ms,
    PERCENTILE(response_time, 99) as p99_latency_ms,
    AVG(response_time) as avg_latency_ms
FROM TraceSummary
WHERE annotation.service = 'streamforge'
  AND timestamp > @start
GROUP BY annotation.pipeline_id
ORDER BY p95_latency_ms DESC
```

---

## Debugging with X-Ray

### Scenario 1: Slow Pipeline

**Symptom:** Pipeline taking 5 seconds instead of 1 second.

**Steps:**
1. Open X-Ray console
2. Filter traces: `annotation.pipeline_id = "ecommerce"`
3. Sort by duration (longest first)
4. Click slowest trace
5. See breakdown:
   - Validate: 100ms
   - Transform: 200ms
   - **DynamoDB get_item: 4,500ms** ← Problem!
   - S3 put_object: 200ms

**Root cause:** DynamoDB throttling due to hot partition.

**Fix:** Add caching or increase read capacity.

---

### Scenario 2: Intermittent Failures

**Symptom:** 2% of requests fail with no obvious pattern.

**Steps:**
1. Filter traces: `error = true AND annotation.pipeline_id = "ecommerce"`
2. Open failed trace
3. See error in Step Functions → Transform Lambda:
   ```
   KeyError: 'amount'
   ```
4. Check X-Ray metadata for failing events:
   - All missing 'amount' field
   - All from source 'webhook' (not 'api')

**Root cause:** Webhook parser not adding default values.

**Fix:** Add default in transform: `amount = event.get('amount', 0)`

---

### Scenario 3: High Latency Spike

**Symptom:** Latency jumped from 500ms to 3s at 2pm.

**Steps:**
1. Filter traces: `timestamp > 1695039600000 AND annotation.pipeline_id = "ecommerce"`
2. Compare latency breakdown before/after 2pm:

**Before 2pm:**
- S3 put_object: 200ms
- Total: 500ms

**After 2pm:**
- S3 put_object: 2,500ms ← 12x slower!
- Total: 3,000ms

**Root cause:** S3 Cross-Region Replication enabled at 2pm (increased latency).

**Fix:** Disable CRR or use S3 Transfer Acceleration.

---

## CloudWatch Integration

X-Ray traces feed CloudWatch dashboards.

### Add X-Ray Widget to Dashboard

```typescript
// infrastructure/lib/monitoring-stack.ts
dashboard.addWidgets(
  new cloudwatch.GraphWidget({
    title: 'Pipeline Latency (X-Ray)',
    left: [
      new cloudwatch.Metric({
        namespace: 'AWS/XRay',
        metricName: 'ResponseTime',
        statistic: 'Average',
        dimensions: {
          ServiceName: 'streamforge-transformer'
        }
      })
    ]
  })
);
```

### Alarm on High Latency

```typescript
new cloudwatch.Alarm(this, 'HighXRayLatency', {
  alarmName: 'StreamForge-HighLatency',
  metric: new cloudwatch.Metric({
    namespace: 'AWS/XRay',
    metricName: 'ResponseTime',
    statistic: 'p95',
    dimensions: {ServiceName: 'streamforge-transformer'}
  }),
  threshold: 2000,  // 2 seconds
  evaluationPeriods: 2,
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
  actionsEnabled: true
});
```

---

## Best Practices

### 1. Always Propagate Trace IDs

```python
# BAD: Trace ID lost at async boundary
kinesis.put_records(Records=[{'Data': json.dumps(event)}])

# GOOD: Trace ID propagated
kinesis.put_records(Records=[{'Data': json.dumps({'trace_id': trace_id, **event})}])
```

---

### 2. Use Annotations for Filtering

```python
# Annotations are indexed (fast filtering)
xray_recorder.put_annotation('pipeline_id', 'ecommerce')
xray_recorder.put_annotation('run_id', 'run-123')
xray_recorder.put_annotation('status_code', 200)

# Metadata is NOT indexed (detailed context only)
xray_recorder.put_metadata('event_payload', event)
```

**Rule:** Use annotations for dimensions you'll filter by (pipeline_id, error type, status).  
Use metadata for detailed context (payloads, stack traces).

---

### 3. Trace Expensive Operations

```python
# Trace slow operations to find bottlenecks
@trace_pipeline_stage('ml_inference')
def run_anomaly_detection(events):
    # This takes 500ms - good to trace!
    return detect_anomalies(events)

# Don't trace trivial operations
def add_timestamp(event):
    # This takes <1ms - not worth tracing
    event['timestamp'] = int(time.time())
    return event
```

---

### 4. Sample Traces in Production

```typescript
// Sample 5% of traces to reduce costs
new lambda.Function(this, 'HighVolumeFunction', {
  tracing: lambda.Tracing.ACTIVE,
  environment: {
    AWS_XRAY_TRACING_NAME: 'streamforge',
    AWS_XRAY_SAMPLING_RATE: '0.05'  // 5%
  }
});
```

**Why:** 1M traces/day × $5/million = $5/day. Sample 5% → $0.25/day.

---

## Cost Analysis

### X-Ray Pricing

| Item | Cost | StreamForge Usage | Monthly Cost |
|------|------|-------------------|--------------|
| Traces recorded | $5 per 1M | 100K/day × 30 = 3M | $15 |
| Traces retrieved | $0.50 per 1M | 10K/day × 30 = 300K | $0.15 |
| Trace storage (30 days) | Included | - | $0 |
| **Total** | | | **$15.15/month** |

**Cost optimization:**
- Sample 10% in production: $15 → $1.50/month
- Enable only on critical pipelines
- Disable after debugging (toggle with env var)

---

## Roadmap

- **Custom traces** - Trace external API calls (webhooks, BigQuery)
- **Trace retention** - Export to S3 for >30 day retention
- **ML insights** - Anomaly detection on latency patterns
- **Auto-remediation** - Trigger Lambda to fix slow queries

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
