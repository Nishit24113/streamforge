# Multi-Region Deployment

High-availability StreamForge deployment across multiple AWS regions with automatic failover and cross-region replication.

---

## Overview

StreamForge supports active-active multi-region deployment for:
- **High Availability:** < 1 minute failover during regional outages
- **Disaster Recovery:** Automated backups and cross-region replication
- **Low Latency:** Users routed to nearest region via Route 53 latency-based routing
- **Data Residency:** Deploy in regions that comply with data sovereignty requirements

| Component | Primary Region | Secondary Region | Replication |
|-----------|---------------|------------------|-------------|
| **API Gateway** | us-east-1 | us-west-2 | Active-Active |
| **S3 Data Lake** | us-east-1 | us-west-2 | Cross-Region Replication (CRR) |
| **DynamoDB** | us-east-1 | us-west-2 | Global Tables (automatic) |
| **Lambda** | us-east-1 | us-west-2 | Deployed in both |
| **Route 53** | Global | Global | Latency-based routing + health checks |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Route 53 (Global)                      │
│          api.streamforge.example.com                     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Latency-Based Routing + Health Checks          │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────┬──────────────────────────┬────────────────┘
               │                          │
    ┌──────────▼──────────┐    ┌─────────▼──────────┐
    │  us-east-1 (Primary)│    │ us-west-2 (Secondary)│
    │                     │    │                      │
    │  API Gateway        │    │  API Gateway         │
    │  Lambda Functions   │    │  Lambda Functions    │
    │  Kinesis Stream     │    │  Kinesis Stream      │
    │  Step Functions     │    │  Step Functions      │
    └──────────┬──────────┘    └─────────┬────────────┘
               │                          │
    ┌──────────▼──────────────────────────▼───────────┐
    │         DynamoDB Global Tables                   │
    │    (Automatic bi-directional replication)        │
    └──────────────────────────────────────────────────┘
               │                          │
    ┌──────────▼──────────┐    ┌─────────▼────────────┐
    │  S3 Bucket (Primary)│───▶│ S3 Bucket (Secondary)│
    │  us-east-1          │    │ us-west-2            │
    │                     │    │ (CRR enabled)        │
    └─────────────────────┘    └──────────────────────┘
```

---

## Deployment

### Deploy Primary Region (us-east-1)

```bash
cd infrastructure

# Deploy primary region stack
cdk deploy StreamForge-Primary \
  --context primaryRegion=us-east-1 \
  --context secondaryRegion=us-west-2 \
  --context domainName=streamforge.example.com
```

### Deploy Secondary Region (us-west-2)

```bash
# Deploy secondary region stack
cdk deploy StreamForge-Secondary \
  --context primaryRegion=us-east-1 \
  --context secondaryRegion=us-west-2 \
  --context domainName=streamforge.example.com
```

### Deploy Both Regions

```bash
# Deploy both regions in one command
cdk deploy StreamForge-Primary StreamForge-Secondary
```

---

## Route 53 Configuration

### Latency-Based Routing

Route 53 automatically routes users to the region with lowest latency.

**Example:** User in Europe → us-east-1 (30ms), User in Asia → us-west-2 (40ms)

**CDK Configuration:**
```typescript
// Primary region record
new route53.ARecord(this, 'PrimaryRegionRecord', {
  zone: hostedZone,
  recordName: 'api',
  target: route53.RecordTarget.fromAlias(new targets.ApiGateway(primaryApi)),
  region: 'us-east-1',
  setIdentifier: 'Primary'  // Latency-based routing
});

// Secondary region record
new route53.ARecord(this, 'SecondaryRegionRecord', {
  zone: hostedZone,
  recordName: 'api',
  target: route53.RecordTarget.fromAlias(new targets.ApiGateway(secondaryApi)),
  region: 'us-west-2',
  setIdentifier: 'Secondary'
});
```

---

### Health Checks

Route 53 health checks automatically fail over if a region becomes unhealthy.

**Health Check Configuration:**
- **Endpoint:** `https://api-id.execute-api.us-east-1.amazonaws.com/health`
- **Interval:** 30 seconds
- **Failure Threshold:** 3 consecutive failures (90 seconds)
- **Failover Time:** < 1 minute

**CDK Configuration:**
```typescript
const healthCheck = new route53.CfnHealthCheck(this, 'PrimaryHealthCheck', {
  healthCheckConfig: {
    type: 'HTTPS',
    resourcePath: '/health',
    fullyQualifiedDomainName: `${api.restApiId}.execute-api.us-east-1.amazonaws.com`,
    port: 443,
    requestInterval: 30,  // 30 seconds
    failureThreshold: 3   // 3 failures = unhealthy
  }
});
```

**Test Failover:**
```bash
# Simulate primary region failure
aws apigateway delete-deployment \
  --rest-api-id <primary-api-id> \
  --deployment-id <deployment-id> \
  --region us-east-1

# Route 53 will failover to us-west-2 within 90 seconds
dig api.streamforge.example.com  # Now points to us-west-2
```

---

## S3 Cross-Region Replication (CRR)

S3 Cross-Region Replication automatically replicates data from primary to secondary bucket.

**Replication Rules:**
- **Source:** `streamforge-lake-us-east-1`
- **Destination:** `streamforge-lake-us-west-2`
- **Replication Time:** < 15 minutes (99.99% of objects)
- **Versioning:** Required (both buckets must have versioning enabled)

**Enable CRR:**
```bash
# Create replication configuration
cat > replication.json <<EOF
{
  "Role": "arn:aws:iam::123456789012:role/StreamForge-S3-Replication",
  "Rules": [{
    "Status": "Enabled",
    "Priority": 1,
    "DeleteMarkerReplication": { "Status": "Enabled" },
    "Filter": { "Prefix": "" },
    "Destination": {
      "Bucket": "arn:aws:s3:::streamforge-lake-us-west-2",
      "ReplicationTime": {
        "Status": "Enabled",
        "Time": { "Minutes": 15 }
      },
      "Metrics": {
        "Status": "Enabled",
        "EventThreshold": { "Minutes": 15 }
      }
    }
  }]
}
EOF

# Apply replication configuration
aws s3api put-bucket-replication \
  --bucket streamforge-lake-us-east-1 \
  --replication-configuration file://replication.json
```

**Monitor Replication:**
```bash
# Check replication status
aws s3api get-bucket-replication \
  --bucket streamforge-lake-us-east-1

# View replication metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name ReplicationLatency \
  --dimensions Name=SourceBucket,Value=streamforge-lake-us-east-1 \
  --start-time 2026-09-27T00:00:00Z \
  --end-time 2026-09-28T00:00:00Z \
  --period 3600 \
  --statistics Average
```

---

## DynamoDB Global Tables

DynamoDB Global Tables provide automatic bi-directional replication between regions.

**Features:**
- **Automatic Replication:** Changes in any region replicated to all other regions
- **Conflict Resolution:** Last-writer-wins (LWW) based on timestamp
- **RPU:** 1 write in us-east-1 = 2 WCU (1 local + 1 replicated to us-west-2)
- **Latency:** < 1 second replication latency

**CDK Configuration:**
```typescript
const globalTable = new dynamodb.Table(this, 'GlobalPipelineTable', {
  tableName: 'streamforge-pipelines-global',
  partitionKey: { name: 'pipeline_id', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  replicationRegions: ['us-west-2'],  // Replicate to secondary region
  stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
  pointInTimeRecovery: true
});
```

**Test Replication:**
```python
import boto3
import time

# Write to primary region
dynamodb_east = boto3.client('dynamodb', region_name='us-east-1')
dynamodb_east.put_item(
    TableName='streamforge-pipelines-global',
    Item={'pipeline_id': {'S': 'test-123'}, 'name': {'S': 'Test Pipeline'}}
)

# Read from secondary region (should be replicated in < 1 second)
time.sleep(1)
dynamodb_west = boto3.client('dynamodb', region_name='us-west-2')
response = dynamodb_west.get_item(
    TableName='streamforge-pipelines-global',
    Key={'pipeline_id': {'S': 'test-123'}}
)

print(response['Item'])  # {'pipeline_id': 'test-123', 'name': 'Test Pipeline'}
```

---

## Failover Scenarios

### Scenario 1: API Gateway Failure (Primary Region)

**Detection:** Route 53 health check fails after 3 consecutive failures (90 seconds)  
**Action:** Route 53 automatically routes traffic to us-west-2  
**RTO:** < 1 minute  
**RPO:** 0 (DynamoDB Global Tables have automatic replication)

**Timeline:**
```
T+0s:    Primary API Gateway becomes unhealthy
T+30s:   First health check fails
T+60s:   Second health check fails
T+90s:   Third health check fails → Region marked unhealthy
T+90s:   Route 53 begins routing to us-west-2
T+120s:  100% of traffic on us-west-2
```

---

### Scenario 2: S3 Data Lake Failure (Primary Region)

**Detection:** S3 API returns 503 errors  
**Action:** Lambda reads from secondary bucket in us-west-2  
**RTO:** < 5 minutes (Lambda cold start + failover logic)  
**RPO:** < 15 minutes (CRR replication time)

**Failover Logic:**
```python
import boto3
from botocore.exceptions import ClientError

def read_from_data_lake(key: str) -> bytes:
    """Read from primary, failover to secondary on failure."""
    regions = ['us-east-1', 'us-west-2']
    
    for region in regions:
        try:
            s3 = boto3.client('s3', region_name=region)
            bucket = f'streamforge-lake-{region}'
            response = s3.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == '503':
                continue  # Try next region
            raise
    
    raise Exception('All regions unavailable')
```

---

### Scenario 3: Full Regional Outage (Primary Region)

**Detection:** All services in us-east-1 unavailable  
**Action:** Route 53 + Lambda failover to us-west-2  
**RTO:** < 5 minutes  
**RPO:** < 1 second (DynamoDB Global Tables), < 15 minutes (S3 CRR)

**Manual Failover:**
```bash
# Force failover by disabling primary health check
aws route53 update-health-check \
  --health-check-id <primary-health-check-id> \
  --disabled

# Verify traffic on secondary region
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Count \
  --dimensions Name=ApiName,Value=StreamForge-Secondary \
  --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Sum \
  --region us-west-2
```

---

## Cost Analysis

### Multi-Region Cost Breakdown (100K events/day)

| Service | Single Region | Multi-Region | Delta |
|---------|--------------|--------------|-------|
| Lambda | $30/month | $60/month | +$30 (2x regions) |
| API Gateway | $35/month | $70/month | +$35 (2x regions) |
| DynamoDB | $50/month | $100/month | +$50 (replication WCU) |
| S3 Storage | $25/month | $50/month | +$25 (2x storage) |
| S3 CRR | $0 | $10/month | +$10 (data transfer) |
| Route 53 | $0.50/month | $1/month | +$0.50 (health checks) |
| **Total** | **$140.50/month** | **$291/month** | **+$150.50 (2.07x)** |

**Cost Optimization:**
- Use S3 Intelligent-Tiering to reduce storage costs
- Enable DynamoDB auto-scaling to reduce idle capacity
- Sample CloudWatch metrics (10% of events) in secondary region

---

## Best Practices

### 1. Test Failover Regularly

Run monthly disaster recovery drills:
```bash
# Disable primary region
aws route53 update-health-check --health-check-id <id> --disabled

# Verify secondary region handles traffic
# Monitor CloudWatch metrics for 15 minutes

# Re-enable primary region
aws route53 update-health-check --health-check-id <id> --no-disabled
```

---

### 2. Monitor Cross-Region Replication Lag

Set CloudWatch alarms for replication delays:
```typescript
new cloudwatch.Alarm(this, 'S3ReplicationLag', {
  metric: new cloudwatch.Metric({
    namespace: 'AWS/S3',
    metricName: 'ReplicationLatency',
    dimensions: { SourceBucket: 'streamforge-lake-us-east-1' }
  }),
  threshold: 900000,  // 15 minutes in milliseconds
  evaluationPeriods: 2,
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
});
```

---

### 3. Use Regional Endpoints

Always use regional S3 endpoints (not `s3.amazonaws.com`):
```python
# BAD: Uses global endpoint (may be slow)
s3 = boto3.client('s3')

# GOOD: Uses regional endpoint (faster, more reliable)
s3 = boto3.client('s3', region_name='us-east-1')
```

---

### 4. Set TTL on Route 53 Records

Low TTL enables faster failover:
```typescript
new route53.ARecord(this, 'APIRecord', {
  zone: hostedZone,
  recordName: 'api',
  target: route53.RecordTarget.fromAlias(new targets.ApiGateway(api)),
  ttl: cdk.Duration.seconds(60)  // 60 seconds (default is 300)
});
```

---

## Roadmap

- **Three-region deployment** - Add us-west-1 for even higher availability
- **Active-passive mode** - Secondary region as cold standby (lower cost)
- **Global Accelerator** - Replace Route 53 with AWS Global Accelerator for lower latency
- **Multi-region Kinesis** - Cross-region Kinesis replication for real-time data

---

**Built by Nishit Patel** | MS Computer Science, Arizona State University
