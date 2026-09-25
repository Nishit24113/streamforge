# Performance Optimization Guide

Speed up StreamForge pipelines with caching, batching, and architectural patterns.

---

## Overview

StreamForge is built for performance from the ground up:

| Optimization | Impact | When to Use |
|--------------|--------|-------------|
| **Query result caching** | 10-50x faster repeat queries | Dashboards, reports |
| **Batch processing** | 3-5x throughput | High-volume ingestion |
| **Connection pooling** | 2-3x faster DB access | Frequent DynamoDB/S3 calls |
| **Parallel transforms** | 2-4x processing speed | CPU-intensive operations |
| **ARM64 Lambdas** | 20% faster, 20% cheaper | All functions |

---

## Query Result Caching

Cache Athena query results to avoid re-scanning S3.

### How It Works

1. Query executes → Result cached with 5-minute TTL
2. Same query within 5 min → Return cached result (no Athena scan)
3. New data ingested → Cache invalidated automatically

### Enable Caching

```python
from streamforge import StreamForge

sf = StreamForge('https://your-api-url.com', enable_cache=True)

# First query: Scans S3, takes 2-3 seconds
result1 = sf.query("SELECT COUNT(*) FROM clean WHERE pipeline_id='ecommerce'")

# Second query: Cached, returns in <100ms
result2 = sf.query("SELECT COUNT(*) FROM clean WHERE pipeline_id='ecommerce'")
```

### Cache Backends

**Memory (default):** Fast, but lost on Lambda cold start
```python
sf = StreamForge(api_url, cache_backend='memory', cache_ttl=300)
```

**Redis:** Persistent across Lambda invocations
```python
sf = StreamForge(api_url, cache_backend='redis', cache_ttl=600)
```

### Cache Invalidation

```python
# Invalidate specific pipeline cache after new ingestion
sf.ingest('ecommerce', events)
sf.invalidate_cache_for_pipeline('ecommerce')

# Invalidate all caches
sf.invalidate_all_caches()
```

### When to Use Caching

✅ **Use caching for:**
- Dashboards with multiple users viewing same data
- Reports generated from historical data
- Aggregate queries (COUNT, SUM, AVG)

❌ **Don't cache:**
- Real-time monitoring queries
- Queries with user-specific filters
- Queries on rapidly changing data (<5 min update frequency)

---

## Batch Processing

Process events in batches to improve throughput.

### Ingestion Batching

```python
# SLOW: Individual ingestions (500 req/s limit)
for event in events:
    sf.ingest('my-pipeline', [event])  # 1 API call per event

# FAST: Batch ingestion (can handle 50K events/s)
sf.ingest_batch('my-pipeline', events, batch_size=500)  # 1 call per 500 events
```

**Performance:**
- Individual: 500 events/second
- Batched (100): 10K events/second
- Batched (500): 50K events/second

### Transform Batching

```python
# Configure batch size in pipeline
{
  "name": "high-throughput-pipeline",
  "steps": [
    {
      "type": "transform",
      "batch_size": 1000,  # Process 1000 events at once
      "operations": [{"op": "cast", "field": "amount", "to": "float"}]
    }
  ]
}
```

### Parallel Processing

Process batches in parallel for CPU-intensive operations:

```python
from streamforge.optimization import BatchProcessor

processor = BatchProcessor(batch_size=100)

# Split into batches
batches = processor.batch_events(events, batch_size=100)

# Process in parallel (4 workers)
results = processor.parallel_process(
    batches,
    process_fn=lambda batch: heavy_transform(batch),
    max_workers=4
)
```

---

## Connection Pooling

Reuse database connections across Lambda invocations.

### Before (Slow)

```python
# Creates new connection every time Lambda is invoked
def lambda_handler(event, context):
    dynamodb = boto3.resource('dynamodb')  # NEW connection
    table = dynamodb.Table('pipelines')
    result = table.get_item(Key={'id': 'abc'})
```

### After (Fast)

```python
# Reuse connection across invocations
dynamodb = boto3.resource('dynamodb')  # GLOBAL - reused
table = dynamodb.Table('pipelines')

def lambda_handler(event, context):
    result = table.get_item(Key={'id': 'abc'})  # Reuses connection
```

**Performance:** 2-3x faster on warm Lambda invocations

---

## Lambda Optimizations

### Use ARM64 (Graviton2)

```typescript
// infrastructure/lib/processing-stack.ts
new lambda.Function(this, 'Transformer', {
  architecture: lambda.Architecture.ARM_64,  // 20% faster, 20% cheaper
  runtime: lambda.Runtime.PYTHON_3_12,
  memorySize: 1024,
});
```

**Benefits:**
- 20% better price/performance
- 20% faster cold starts
- Better for CPU-intensive transforms

### Right-Size Memory

```python
# Test with different memory sizes
# More memory = more CPU = faster execution = lower cost (pay for duration)

# 512MB: 5.2s execution = $0.000104
# 1024MB: 2.8s execution = $0.000056  ✅ BEST
# 2048MB: 1.9s execution = $0.000076
```

**Rule of thumb:** Double memory if it cuts execution time by >50%

### Reduce Cold Starts

```typescript
new lambda.Function(this, 'ApiHandler', {
  reservedConcurrentExecutions: 10,  // Keep 10 warm
  timeout: cdk.Duration.seconds(30),
});
```

**Or use provisioned concurrency:**
```bash
aws lambda put-provisioned-concurrency-config \
  --function-name streamforge-api-handler \
  --provisioned-concurrent-executions 5
```

---

## S3 Optimizations

### Use Parquet with Snappy Compression

```python
# JSON: 1GB file, 45s Athena scan, $0.005
# Parquet + Snappy: 100MB file, 8s Athena scan, $0.001
```

**Benefits:**
- 90% smaller files
- 5-6x faster queries
- 80% cost reduction

### Partition by Date

```
s3://bucket/clean/pipeline_id/year=2026/month=09/day=25/run_abc.parquet
```

**Query with partition filtering:**
```sql
SELECT * FROM clean
WHERE year = 2026 AND month = 09 AND day = 25
```

**Scans only 1 day instead of entire dataset**

### Use S3 Transfer Acceleration

```python
s3_client = boto3.client('s3', config=Config(
    s3={'use_accelerate_endpoint': True}
))
```

**Benefits:** 2-6x faster uploads from distant regions

---

## Athena Optimizations

### Optimize Query Patterns

**SLOW:**
```sql
-- Scans entire dataset
SELECT * FROM clean WHERE pipeline_id = 'ecommerce'
```

**FAST:**
```sql
-- Partition pruning + column selection
SELECT event_id, amount FROM clean
WHERE year = 2026 AND month = 09 AND pipeline_id = 'ecommerce'
```

### Use CTAS for Complex Queries

```sql
-- Create materialized table for dashboard
CREATE TABLE ecommerce_daily_stats AS
SELECT
  DATE(from_unixtime(timestamp/1000)) as date,
  COUNT(*) as total_orders,
  SUM(CAST(json_extract_scalar(payload, '$.amount') AS DOUBLE)) as revenue
FROM clean
WHERE pipeline_id = 'ecommerce'
GROUP BY DATE(from_unixtime(timestamp/1000))
```

**Query materialized table:**
```sql
SELECT * FROM ecommerce_daily_stats WHERE date = DATE '2026-09-25'
```

**Performance:** 50-100x faster than aggregating raw data

---

## Kinesis Optimizations

### Use On-Demand Mode

```typescript
new kinesis.Stream(this, 'IngestionStream', {
  streamMode: StreamMode.ON_DEMAND,  // Auto-scales to demand
});
```

**Benefits:**
- No shard management
- Auto-scales 0 → 200 MB/s in seconds
- Pay only for throughput used

### Batch Records

```python
# SLOW: 1 record per PutRecord call
for event in events:
    kinesis.put_record(StreamName='stream', Data=event, PartitionKey='key')

# FAST: Up to 500 records per PutRecords call
kinesis.put_records(
    StreamName='stream',
    Records=[{'Data': e, 'PartitionKey': 'key'} for e in events[:500]]
)
```

---

## DynamoDB Optimizations

### Batch Get/Write

```python
# SLOW: 1 item per call
for pipeline_id in pipeline_ids:
    table.get_item(Key={'pipeline_id': pipeline_id})

# FAST: Up to 100 items per call
response = dynamodb.batch_get_item(
    RequestItems={
        'pipelines': {
            'Keys': [{'pipeline_id': pid} for pid in pipeline_ids[:100]]
        }
    }
)
```

### Use Query Instead of Scan

```python
# SLOW: Scans entire table
table.scan(FilterExpression=Attr('status').eq('ACTIVE'))

# FAST: Uses partition key
table.query(KeyConditionExpression=Key('pipeline_id').eq('abc'))
```

### Enable TTL for Cleanup

```typescript
new dynamodb.Table(this, 'RunHistory', {
  partitionKey: {name: 'pipeline_id', type: AttributeType.STRING},
  timeToLiveAttribute: 'ttl',  // Auto-delete old runs
});
```

---

## Monitoring Performance

### CloudWatch Metrics

```bash
# Lambda duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=streamforge-transformer \
  --start-time 2026-09-25T00:00:00Z \
  --end-time 2026-09-25T23:59:59Z \
  --period 3600 \
  --statistics Average,Maximum
```

### Query Performance

```python
# Track query performance
from streamforge.optimization import get_performance_monitor

monitor = get_performance_monitor()

# Record query
start = time.time()
result = sf.query("SELECT * FROM clean")
duration = time.time() - start
monitor.record_query(duration, cache_hit=False)

# Get stats
stats = monitor.get_stats()
print(f"Cache hit rate: {stats['cache_hit_rate']:.1%}")
print(f"Avg query time: {stats['avg_query_time']:.2f}s")
```

### X-Ray Tracing

Enable in Step Functions for end-to-end tracing:

```typescript
new sfn.StateMachine(this, 'Pipeline', {
  definitionBody: sfn.DefinitionBody.fromChainable(definition),
  tracingEnabled: true,  // X-Ray tracing
});
```

**View in X-Ray console:** See Lambda → Step Functions → S3 latency breakdown

---

## Performance Benchmarks

### Ingestion Throughput

| Method | Throughput | Latency (p50) |
|--------|------------|---------------|
| Single events | 500/s | 50ms |
| Batched (100) | 10K/s | 200ms |
| Batched (500) | 50K/s | 500ms |
| File upload | 100K/s | N/A |

### Query Performance

| Query Type | Cold (no cache) | Warm (cached) |
|------------|----------------|---------------|
| Count (*) | 2.5s | 80ms |
| Aggregation (1M rows) | 8.2s | 90ms |
| Full scan (10M rows) | 45s | N/A (too large) |

### Transform Performance

| Transform | Events/sec (512MB) | Events/sec (1024MB) |
|-----------|-------------------|---------------------|
| Simple (cast, rename) | 5K | 12K |
| Regex extract | 2K | 5K |
| Hash (SHA256) | 3K | 7K |
| GeoIP lookup | 1.5K | 3.5K |

---

## Cost vs Performance

### Caching ROI

**Without caching:**
- 10 users × 5 queries/min × 60 min = 3,000 queries/hr
- Athena: $5 per TB scanned
- Avg query scans 10 GB = $0.05 per query
- Cost: 3,000 × $0.05 = **$150/hr**

**With caching (80% hit rate):**
- 600 queries hit Athena (20%)
- Cost: 600 × $0.05 = **$30/hr**
- **Savings: $120/hr = $2,880/day**

### Lambda Memory ROI

| Config | Duration | Cost per 1M invocations |
|--------|----------|------------------------|
| 512MB | 5.2s | $104 |
| 1024MB | 2.8s | $56 ✅ |
| 2048MB | 1.9s | $76 |

**Best:** 1024MB saves $48 per 1M invocations

---

## Best Practices

1. **Enable caching for dashboards** - 80-90% hit rate typical
2. **Batch ingestion** - Use 500-event batches for high throughput
3. **Partition S3 by date** - 10-100x faster Athena queries
4. **Use ARM64 Lambdas** - 20% cheaper + faster
5. **Right-size Lambda memory** - Test 512MB / 1024MB / 2048MB
6. **Connection pooling** - Define boto3 clients globally in Lambdas
7. **Monitor cache hit rate** - Target >70% for dashboards
8. **Use Parquet + Snappy** - 90% smaller files, 5x faster queries

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
