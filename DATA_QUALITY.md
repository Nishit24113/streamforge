# Data Quality Metrics

Monitor and improve data quality with automated scoring across 5 dimensions.

---

## Overview

StreamForge automatically calculates data quality metrics for every pipeline run:

| Metric | Weight | What It Measures |
|--------|--------|------------------|
| **Completeness** | 25% | Percentage of non-null required fields |
| **Freshness** | 20% | Data recency and ingestion lag |
| **Accuracy** | 30% | Type correctness, range validation |
| **Uniqueness** | 15% | Duplicate detection |
| **Schema Health** | 10% | Schema stability and drift detection |

**Overall Quality Score:** Weighted average (0-100)

---

## Completeness

Measures what percentage of required fields are present and non-null.

### Scoring

- **100:** All required fields present in all events
- **75-99:** Most required fields present
- **50-74:** Half of required fields present
- **<50:** Many missing fields

### Example

```json
{
  "completeness": {
    "score": 87.5,
    "completeness_rate": 0.875,
    "missing_fields": {
      "phone": "25.0% missing",
      "address": "12.5% missing"
    },
    "field_completeness": {
      "email": 1.0,
      "name": 1.0,
      "phone": 0.75,
      "address": 0.875
    }
  }
}
```

### How to Improve

- Add default values with `op: default`
- Filter incomplete records with `op: filter`
- Validate at ingestion with schema enforcement
- Track source quality (which APIs/systems send incomplete data)

---

## Freshness

Measures how recent the data is and ingestion lag.

### Scoring

- **100:** Data <5 minutes old
- **90:** Data <1 hour old
- **70:** Data <6 hours old
- **50:** Data <24 hours old
- **<50:** Data >24 hours old

### Example

```json
{
  "freshness": {
    "score": 95.0,
    "avg_age_seconds": 180.5,
    "max_age_seconds": 425.0,
    "is_fresh": true
  }
}
```

### How to Improve

- Reduce batch intervals (process every 5m instead of 1h)
- Use Kinesis on-demand scaling for burst traffic
- Check for backpressure in Step Functions
- Monitor Lambda cold starts (ARM64 reduces startup time)

---

## Accuracy

Measures type correctness and format compliance.

### Scoring

- **100:** All values match expected types and formats
- **90-99:** Most values correct
- **70-89:** Some type/format violations
- **<70:** Many incorrect values

### Example

```json
{
  "accuracy": {
    "score": 92.5,
    "accuracy_rate": 0.925,
    "violations": [
      {
        "event_index": 15,
        "field": "amount",
        "expected": "number",
        "actual": "string",
        "value": "99.99"
      }
    ],
    "total_violations": 5
  }
}
```

### How to Improve

- Add `op: cast` to convert types (string → number)
- Use `op: regex_validate` for format checking
- Validate at ingestion with schema enforcement
- Add `op: default` for missing values

---

## Uniqueness

Measures duplicate rate based on event_id.

### Scoring

- **100:** No duplicates
- **90:** <5% duplicates
- **70:** <15% duplicates
- **<70:** High duplicate rate

### Example

```json
{
  "uniqueness": {
    "score": 100.0,
    "total_events": 1000,
    "unique_events": 1000,
    "duplicate_count": 0,
    "duplicate_rate": 0.0
  }
}
```

### How to Improve

- Generate unique IDs at source (UUID v4)
- Deduplicate at ingestion with DynamoDB conditional writes
- Use Kinesis deduplication (partition key + sequence number)
- Implement idempotency keys for retries

---

## Schema Health

Detects schema drift (new fields, type changes).

### Scoring

- **100:** Schema stable, no drift
- **90:** Minor drift (new optional fields)
- **70:** Moderate drift (type changes)
- **<70:** Major drift (missing required fields)

### Example

```json
{
  "schema_health": {
    "score": 90.0,
    "drift_detected": true,
    "new_fields": ["device_type", "session_id"],
    "type_changes": [
      {
        "field": "timestamp",
        "types": {"int": 950, "str": 50}
      }
    ],
    "schema_stability": "stable"
  }
}
```

### How to Improve

- Version your schemas and store in DynamoDB
- Use `op: cast` to normalize types
- Communicate schema changes to downstream consumers
- Run schema validation before deploying pipeline changes

---

## Viewing Quality Metrics

### Python SDK

```python
from streamforge import StreamForge

sf = StreamForge('https://your-api-url.com')

# Get latest quality metrics
metrics = sf.get_quality_metrics('ecommerce-events')
print(f"Quality score: {metrics['quality_score']}")
print(f"Completeness: {metrics['completeness']['score']}")
print(f"Freshness: {metrics['freshness']['score']}")

# Get quality trends (last 24 hours)
trends = sf.get_quality_trends('ecommerce-events', hours=24)
print(f"Average score: {trends['avg_quality_score']}")
print(f"Trend: {trends['trend']}")  # 'improving' or 'declining'
```

---

### REST API

```bash
# Get latest metrics
curl https://your-api-url.com/v1/quality/ecommerce-events

# Get 24-hour trends
curl https://your-api-url.com/v1/quality/ecommerce-events/trends?hours=24
```

---

### CloudWatch Dashboard

Quality metrics are automatically published to CloudWatch under `StreamForge/DataQuality`:

- `QualityScore` - Overall score (0-100)
- `CompletenessScore` - Completeness dimension
- `FreshnessScore` - Freshness dimension
- `AccuracyScore` - Accuracy dimension

**View in dashboard:** CloudWatch → Dashboards → `StreamForge-DataQuality`

---

## Alerting on Quality Issues

### CloudWatch Alarms

```bash
# Alert when quality score drops below 70
aws cloudwatch put-metric-alarm \
  --alarm-name "StreamForge-LowQualityScore-ecommerce" \
  --metric-name QualityScore \
  --namespace StreamForge/DataQuality \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 70 \
  --comparison-operator LessThanThreshold \
  --dimensions Name=PipelineId,Value=ecommerce-events \
  --alarm-actions arn:aws:sns:us-west-2:ACCOUNT:streamforge-alerts
```

---

### SNS Notifications

Subscribe to quality alerts:

```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-west-2:ACCOUNT:streamforge-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com
```

---

## Quality-Based Pipeline Actions

### Auto-pause on Low Quality

```python
# Monitor quality and pause pipeline if score < 60
metrics = sf.get_quality_metrics('my-pipeline')

if metrics['quality_score'] < 60:
    print(f"⚠️  Quality score too low: {metrics['quality_score']}")
    
    # Identify issues
    if metrics['completeness']['score'] < 70:
        print(f"Issue: {metrics['completeness']['missing_fields']}")
    
    if metrics['accuracy']['score'] < 70:
        print(f"Type violations: {metrics['accuracy']['total_violations']}")
    
    # Pause pipeline (requires admin API)
    # sf.pause_pipeline('my-pipeline')
```

---

### Quality Gating in CI/CD

```yaml
# .github/workflows/deploy-pipeline.yml
- name: Test Pipeline Quality
  run: |
    streamforge ingest test-pipeline test-data.json
    sleep 30  # Wait for processing
    
    quality=$(streamforge quality test-pipeline --json | jq '.quality_score')
    
    if (( $(echo "$quality < 80" | bc -l) )); then
      echo "Quality score $quality is below threshold"
      exit 1
    fi
```

---

## Best Practices

### 1. Set Quality Thresholds by Pipeline Type

| Pipeline Type | Min Score | Why |
|--------------|-----------|-----|
| **Financial transactions** | 95+ | Regulatory compliance |
| **E-commerce orders** | 90+ | Revenue impact |
| **Web analytics** | 75+ | Can tolerate some missing data |
| **IoT sensors** | 70+ | High volume, some sensor failures OK |

---

### 2. Monitor Trends, Not Just Snapshots

```python
# Check if quality is declining over time
trends = sf.get_quality_trends('my-pipeline', hours=168)  # 7 days

if trends['trend'] == 'declining':
    recent_avg = sum([h['score'] for h in trends['history'][:24]]) / 24
    past_avg = sum([h['score'] for h in trends['history'][-24:]]) / 24
    
    drop = past_avg - recent_avg
    if drop > 10:
        print(f"⚠️  Quality dropped {drop:.1f} points in last 24h")
```

---

### 3. Fix Root Causes, Not Symptoms

**Symptom:** Low completeness score  
**Root causes:**
- Source API changed schema (new required field)
- Network timeouts truncating payloads
- ETL bug dropping fields during transform

**Action:** Check upstream sources, not just downstream pipeline

---

### 4. Quality SLAs

Define SLAs and track compliance:

```python
SLA = {
    'quality_score': 85,
    'completeness': 90,
    'freshness': 95,
    'accuracy': 95
}

metrics = sf.get_quality_metrics('my-pipeline')
breaches = []

for dimension, threshold in SLA.items():
    if dimension == 'quality_score':
        score = metrics['quality_score']
    else:
        score = metrics[dimension]['score']
    
    if score < threshold:
        breaches.append(f"{dimension}: {score} < {threshold}")

if breaches:
    print("SLA BREACH:", breaches)
```

---

## Cost Considerations

Quality metric calculation:

- **Lambda invocations:** 1 per pipeline run
- **DynamoDB writes:** 1 per run (90-day TTL)
- **CloudWatch metrics:** 4 per run ($0.30 per 1000 metrics)
- **S3 reads:** 1 per run (read clean events)

**Estimated cost:** ~$5/month for 100K pipeline runs

---

## Roadmap

- **Column-level profiling** - Min/max/avg for numeric fields
- **Data lineage tracking** - Where did bad data come from?
- **Anomaly detection on quality** - Alert when score drops suddenly
- **Quality score prediction** - ML model to predict future quality
- **Auto-remediation** - Automatically fix common issues

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
