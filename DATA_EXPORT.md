# Data Export & Integration

Export StreamForge pipeline data to external systems, data warehouses, and BI tools.

---

## Overview

StreamForge supports multiple export mechanisms:

| Export Type | Use Case | Latency | Cost |
|-------------|----------|---------|------|
| **CSV/JSON Download** | Ad-hoc analysis, reporting | On-demand | $0.001/GB |
| **BigQuery Streaming** | Real-time dashboards | <1 minute | $0.05/GB |
| **Snowflake Bulk** | Daily data warehouse loads | Hourly/daily | $0.02/GB |
| **Webhooks** | Slack/Discord notifications | Real-time | Free |
| **Scheduled Exports** | Automated daily reports | Configured | $0.001/GB |

---

## CSV/JSON Export

Export pipeline data with presigned download URLs.

### Python SDK

```python
from streamforge import StreamForge

sf = StreamForge('https://your-api-url.com')

# Export last 7 days to CSV
result = sf.export_data(
    pipeline_id='ecommerce',
    format='csv',
    date_from='2026-09-19',
    date_to='2026-09-26',
    zone='clean'
)

print(f"Download URL: {result['export_url']}")
print(f"Events exported: {result['event_count']:,}")
print(f"Expires in: {result['expires_in']} seconds")

# Download the file
import requests
response = requests.get(result['export_url'])
with open('export.csv', 'wb') as f:
    f.write(response.content)
```

### REST API

```bash
# Export to CSV
curl -X POST https://your-api-url.com/v1/export \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_id": "ecommerce",
    "format": "csv",
    "date_from": "2026-09-01",
    "date_to": "2026-09-26",
    "zone": "clean"
  }'

# Response:
# {
#   "export_url": "https://s3.amazonaws.com/...",
#   "event_count": 15000,
#   "format": "csv",
#   "expires_in": 3600
# }
```

### CSV Format

Exported CSV includes:

```csv
event_id,pipeline_id,timestamp,event_type,source,is_anomaly,anomaly_score,user_id,amount,email
evt-abc123,ecommerce,1695000000000,purchase,api,false,0,user_12345,99.99,user@example.com
evt-def456,ecommerce,1695000060000,purchase,api,true,0.85,user_67890,9999.99,fraud@example.com
```

**Columns:**
- Standard fields: `event_id`, `pipeline_id`, `timestamp`, `event_type`, `source`, `is_anomaly`, `anomaly_score`
- Payload fields: All fields from event payload (flattened)

---

## BigQuery Streaming Integration

Stream events to BigQuery for real-time analytics.

### Setup

**1. Create BigQuery table:**

```sql
CREATE TABLE `your-project.streamforge.events` (
  event_id STRING NOT NULL,
  pipeline_id STRING NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  event_type STRING,
  source STRING,
  is_anomaly BOOLEAN,
  anomaly_score FLOAT64,
  payload JSON
)
PARTITION BY DATE(timestamp)
CLUSTER BY pipeline_id, event_type;
```

**2. Configure in StreamForge:**

```python
from streamforge.integrations import BigQueryExporter

# Initialize exporter
exporter = BigQueryExporter(
    project_id='your-gcp-project',
    dataset_id='streamforge',
    table_id='events'
)

# Create table if not exists
exporter.create_table_if_not_exists()

# Stream events (called automatically by pipeline)
events = [
    {'event_id': 'evt-123', 'pipeline_id': 'ecommerce', 'amount': 99.99},
    {'event_id': 'evt-456', 'pipeline_id': 'ecommerce', 'amount': 149.99}
]

result = exporter.stream_events(events)
print(f"Streamed {result['rows_streamed']} rows")
```

### Query in BigQuery

```sql
-- Daily revenue by pipeline
SELECT
  DATE(timestamp) as date,
  pipeline_id,
  COUNT(*) as events,
  CAST(JSON_VALUE(payload, '$.amount') AS FLOAT64) as total_revenue
FROM `your-project.streamforge.events`
WHERE DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY date, pipeline_id
ORDER BY date DESC;

-- Anomaly rate by hour
SELECT
  TIMESTAMP_TRUNC(timestamp, HOUR) as hour,
  COUNT(*) as total_events,
  SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END) as anomalies,
  ROUND(100.0 * SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END) / COUNT(*), 2) as anomaly_rate
FROM `your-project.streamforge.events`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY hour
ORDER BY hour DESC;
```

### Performance

- **Streaming inserts:** <1 minute latency
- **Cost:** $0.05 per GB inserted ($0.01 per GB in US)
- **Partitioning:** Queries scan only relevant date partitions
- **Clustering:** Filters on `pipeline_id` skip irrelevant data

---

## Snowflake Bulk Export

Bulk export for data warehouse analytics.

### Setup

**1. Create Snowflake table:**

```sql
CREATE TABLE STREAMFORGE_EVENTS (
    event_id VARCHAR(255) NOT NULL,
    pipeline_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP_NTZ NOT NULL,
    event_type VARCHAR(255),
    source VARCHAR(255),
    is_anomaly BOOLEAN,
    anomaly_score FLOAT,
    payload VARIANT,
    PRIMARY KEY (event_id)
);
```

**2. Configure bulk export:**

```python
from streamforge.integrations import SnowflakeExporter

exporter = SnowflakeExporter(
    account='your-account.snowflakecomputing.com',
    user='streamforge_user',
    password='password',
    warehouse='COMPUTE_WH',
    database='ANALYTICS',
    schema='PUBLIC',
    table='STREAMFORGE_EVENTS'
)

# Create table if not exists
exporter.create_table_if_not_exists()

# Bulk insert (called by scheduled export)
events = load_events_from_s3()  # Your export logic
result = exporter.bulk_insert(events)

print(f"Inserted {result['rows_inserted']} rows")

exporter.close()
```

### Query in Snowflake

```sql
-- Daily event volume
SELECT
  DATE(timestamp) as date,
  pipeline_id,
  COUNT(*) as events,
  SUM(IFF(is_anomaly, 1, 0)) as anomalies
FROM STREAMFORGE_EVENTS
WHERE timestamp >= DATEADD(day, -30, CURRENT_DATE())
GROUP BY date, pipeline_id
ORDER BY date DESC;

-- Parse JSON payload
SELECT
  event_id,
  payload:user_id::STRING as user_id,
  payload:amount::FLOAT as amount,
  payload:email::STRING as email
FROM STREAMFORGE_EVENTS
WHERE pipeline_id = 'ecommerce'
LIMIT 100;
```

---

## Webhook Notifications

Send real-time notifications to Slack, Discord, or custom endpoints.

### Slack Webhook

```python
from streamforge import StreamForge

sf = StreamForge('https://your-api-url.com')

# Send Slack notification
sf.send_webhook(
    webhook_url='https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
    pipeline_id='ecommerce',
    event_data={
        'message': 'Daily export completed',
        'event_count': 15000,
        'export_url': 'https://...'
    },
    webhook_type='slack'
)
```

**Slack message format:**
```
📊 StreamForge Export: ecommerce

Events: 15,000
Status: ✅ Daily export completed

📥 Download Export
```

### Discord Webhook

```python
sf.send_webhook(
    webhook_url='https://discord.com/api/webhooks/YOUR/WEBHOOK',
    pipeline_id='ecommerce',
    event_data={
        'message': 'Anomaly spike detected',
        'anomaly_count': 42,
        'anomaly_rate': 8.5
    },
    webhook_type='discord'
)
```

### Custom Webhook

```python
# Send to any HTTP endpoint
sf.send_webhook(
    webhook_url='https://your-service.com/webhook',
    pipeline_id='ecommerce',
    event_data={
        'custom_field_1': 'value1',
        'custom_field_2': 'value2'
    },
    webhook_type='custom'
)
```

**Custom webhook receives:**
```json
{
  "custom_field_1": "value1",
  "custom_field_2": "value2"
}
```

---

## Scheduled Exports

Automate daily/weekly exports with optional notifications.

### Configure Scheduled Export

```python
from streamforge import StreamForge

sf = StreamForge('https://your-api-url.com')

# Daily export at midnight UTC with Slack notification
config = sf.configure_scheduled_export(
    pipeline_id='ecommerce',
    schedule='daily',          # or 'weekly' or cron expression
    format='csv',
    zone='clean',
    notify_webhook='https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
    webhook_type='slack'
)

print(f"Export configured: {config['config_id']}")
```

### Schedule Options

**Preset schedules:**
- `'daily'` - Every day at midnight UTC
- `'weekly'` - Every Sunday at midnight UTC

**Custom cron:**
```python
# Every day at 8am UTC
schedule='cron(0 8 * * ? *)'

# Every weekday at 6pm UTC
schedule='cron(0 18 ? * MON-FRI *)'

# First day of month at noon
schedule='cron(0 12 1 * ? *)'
```

### List Configured Exports

```python
# All exports
exports = sf.list_exports()
print(f"Found {exports['count']} exports")

# Pipeline-specific
exports = sf.list_exports(pipeline_id='ecommerce')
for exp in exports['exports']:
    print(f"{exp['config_id']}: {exp['schedule']} → {exp['format']}")
```

---

## Integration Patterns

### Pattern 1: Daily BI Reports

**Goal:** Export yesterday's data to BigQuery every morning for Tableau dashboards.

```python
from streamforge import StreamForge
from streamforge.integrations import BigQueryExporter
from datetime import datetime, timedelta

sf = StreamForge('https://your-api-url.com')

# Configure daily export at 1am UTC
sf.configure_scheduled_export(
    pipeline_id='ecommerce',
    schedule='cron(0 1 * * ? *)',
    format='csv'
)

# Lambda/Cloud Function triggered by schedule:
def daily_export_to_bigquery(event, context):
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Export from StreamForge
    export = sf.export_data(
        pipeline_id='ecommerce',
        format='json',
        date_from=yesterday,
        date_to=yesterday
    )
    
    # Load into BigQuery
    bq = BigQueryExporter('project', 'dataset', 'events')
    
    import requests
    events = requests.get(export['export_url']).json()
    bq.stream_events(events)
    
    # Notify Slack
    sf.send_webhook(
        'https://hooks.slack.com/...',
        'ecommerce',
        {'message': f"Loaded {len(events)} events to BigQuery for {yesterday}"},
        'slack'
    )
```

---

### Pattern 2: Real-Time Slack Alerts

**Goal:** Notify Slack when anomaly rate exceeds threshold.

```python
# In your pipeline processing Lambda:
def check_and_alert(pipeline_id, anomaly_count, total_events):
    anomaly_rate = (anomaly_count / total_events) * 100
    
    if anomaly_rate > 10:  # Alert if >10% anomalies
        sf.send_webhook(
            'https://hooks.slack.com/...',
            pipeline_id,
            {
                'message': f'⚠️ High anomaly rate detected!',
                'anomaly_count': anomaly_count,
                'total_events': total_events,
                'anomaly_rate': f'{anomaly_rate:.1f}%'
            },
            'slack'
        )
```

---

### Pattern 3: Snowflake Weekly Rollup

**Goal:** Load week's data to Snowflake every Monday for executive reports.

```python
from streamforge import StreamForge
from streamforge.integrations import SnowflakeExporter
from datetime import datetime, timedelta

# Triggered every Monday at 2am
def weekly_snowflake_load(event, context):
    sf = StreamForge('https://your-api-url.com')
    
    # Last 7 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    
    # Export from StreamForge
    export = sf.export_data(
        pipeline_id='ecommerce',
        format='json',
        date_from=start_date.strftime('%Y-%m-%d'),
        date_to=end_date.strftime('%Y-%m-%d')
    )
    
    # Load to Snowflake
    sf_exporter = SnowflakeExporter(
        account='your-account',
        user='user',
        password='pass',
        warehouse='WH',
        database='DB',
        schema='PUBLIC',
        table='EVENTS'
    )
    
    import requests
    events = requests.get(export['export_url']).json()
    result = sf_exporter.bulk_insert(events)
    
    sf_exporter.close()
    
    print(f"Loaded {result['rows_inserted']} rows to Snowflake")
```

---

## Cost Analysis

### Export Costs

| Operation | AWS Cost | Data Transfer | Total (1M events) |
|-----------|----------|---------------|-------------------|
| CSV export (10GB) | $0.01 (S3) | $0.09/GB (egress) | $0.91 |
| JSON export (15GB) | $0.015 (S3) | $0.09/GB | $1.36 |
| BigQuery stream | $0 (Lambda) | $0.05/GB (BQ) | $0.50 |
| Snowflake bulk | $0.01 (S3) | $0.02/GB (SF) | $0.21 |
| Webhooks | $0 (Lambda) | $0 | $0 |

**Recommendation:** Use BigQuery streaming for real-time dashboards, Snowflake bulk for weekly reports.

---

## Best Practices

### 1. Use Partitioning

**BigQuery:**
```sql
-- Partition by timestamp (query only relevant dates)
PARTITION BY DATE(timestamp)
CLUSTER BY pipeline_id
```

**Snowflake:**
```sql
-- Cluster by commonly filtered columns
CLUSTER BY (pipeline_id, DATE(timestamp))
```

**Benefit:** 10-100x faster queries, 90% cost reduction

---

### 2. Export Incrementally

```python
# BAD: Export all data every day (expensive, slow)
export = sf.export_data('ecommerce', date_from='2026-01-01', date_to='2026-09-26')

# GOOD: Export only yesterday (fast, cheap)
yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
export = sf.export_data('ecommerce', date_from=yesterday, date_to=yesterday)
```

---

### 3. Compress Large Exports

```python
# After downloading export
import gzip
import shutil

with open('export.csv', 'rb') as f_in:
    with gzip.open('export.csv.gz', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

# Result: 90% size reduction (10GB → 1GB)
```

---

### 4. Cache Export URLs

```python
# Cache presigned URLs to avoid re-exporting
from functools import lru_cache

@lru_cache(maxsize=100)
def get_export_url(pipeline_id, date):
    export = sf.export_data(pipeline_id, date_from=date, date_to=date)
    return export['export_url']

# Multiple requests use cached URL (valid for 1 hour)
url = get_export_url('ecommerce', '2026-09-26')
```

---

### 5. Monitor Export Performance

```python
import time

start = time.time()
export = sf.export_data('ecommerce', format='csv')
duration = time.time() - start

print(f"Export took {duration:.1f}s for {export['event_count']} events")
print(f"Throughput: {export['event_count'] / duration:.0f} events/sec")
```

---

## Troubleshooting

### Export Returns 0 Events

**Check:**
1. Date range includes data: `sf.query("SELECT COUNT(*) FROM clean WHERE pipeline_id='...' AND year=2026")`
2. Zone is correct: Try `zone='raw'` instead of `zone='clean'`
3. Pipeline ID matches exactly (case-sensitive)

---

### BigQuery Streaming Errors

**Common issues:**
1. **Schema mismatch** - Ensure table schema matches StreamForge events
2. **Quota exceeded** - Check BigQuery streaming limits (100K rows/sec)
3. **Authentication** - Verify service account has `bigquery.dataEditor` role

**Fix:**
```python
# Check table schema
from google.cloud import bigquery
client = bigquery.Client()
table = client.get_table('project.dataset.events')
print([f.name for f in table.schema])
```

---

### Webhook Not Received

**Debug:**
1. Test webhook URL manually: `curl -X POST https://... -d '{"test": "data"}'`
2. Check webhook logs in Slack/Discord settings
3. Verify webhook type matches endpoint (`slack` vs `discord` vs `custom`)

---

## Roadmap

- **Redshift integration** - Native AWS data warehouse support
- **Firehose streaming** - Direct S3 → Redshift/OpenSearch
- **Parquet exports** - 90% smaller files, faster queries
- **Email exports** - Automated CSV reports via email
- **PowerBI/Tableau connectors** - Native BI tool integration

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
